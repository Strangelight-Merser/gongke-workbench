"""Persistent task receipts with cooperative cancellation, not pretend rollback."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import threading
from uuid import uuid4


def now():
    return datetime.now(timezone.utc).isoformat()


class Canceled(Exception):
    pass


class TaskContext:
    def __init__(self, manager, task_id, event):
        self.manager, self.task_id, self.event = manager, task_id, event

    def check(self):
        if self.event.is_set():
            raise Canceled("已停止后续操作；已完成的文件与原生修改保留")

    def stage(self, stage):
        self.manager.update(self.task_id, stage=stage)

    def receipt(self, command, params, result):
        self.manager.receipt(self.task_id, command, params, result)


class Tasks:
    def __init__(self, state_dir: Path, emit):
        state_dir.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(state_dir / "tasks.sqlite3", check_same_thread=False)
        self.db.execute("CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY, record TEXT NOT NULL)")
        self.db.execute("CREATE TABLE IF NOT EXISTS receipts (task_id TEXT, command TEXT, record TEXT)")
        self.emit = emit
        self.cancel_events = {}
        self.pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="gongke")
        for record in self.list():
            if record["status"] in {"queued", "running"}:
                self.update(record["task_id"], status="interrupted", finished_at=now(),
                            stage="应用已重启；原生写操作结果须读取宿主确认，未自动重试")

    def get(self, task_id):
        with self.lock:
            row = self.db.execute("SELECT record FROM tasks WHERE id=?", (task_id,)).fetchone()
            if row is None:
                raise ValueError("任务不存在")
            record = json.loads(row[0])
            record["receipts"] = [json.loads(item[0]) for item in self.db.execute(
                "SELECT record FROM receipts WHERE task_id=? ORDER BY rowid", (task_id,))]
            return record

    def list(self, project=None):
        with self.lock:
            rows = [json.loads(row[0]) for row in self.db.execute("SELECT record FROM tasks ORDER BY rowid DESC LIMIT 100")]
        return [row for row in rows if project is None or row["project"] == project]

    def update(self, task_id, **changes):
        with self.lock:
            row = self.db.execute("SELECT record FROM tasks WHERE id=?", (task_id,)).fetchone()
            record = json.loads(row[0])
            record.update(changes)
            self.db.execute("UPDATE tasks SET record=? WHERE id=?", (json.dumps(record, ensure_ascii=False, allow_nan=False), task_id))
            self.db.commit()
        self.emit({"event": "task.updated", "task": record})
        return record

    def receipt(self, task_id, command, params, result):
        record = {"command": command, "params": params, "result": result, "at": now()}
        with self.lock:
            self.db.execute("INSERT INTO receipts VALUES (?,?,?)", (task_id, command, json.dumps(record, ensure_ascii=False, allow_nan=False)))
            self.db.commit()
        self.emit({"event": "task.receipt", "task_id": task_id, "receipt": record})

    def start(self, kind, project, fn):
        task_id, event = uuid4().hex, threading.Event()
        record = {"task_id": task_id, "kind": kind, "project": str(project), "status": "queued",
                  "created_at": now(), "stage": "等待执行", "cancel_requested": False}
        with self.lock:
            self.cancel_events[task_id] = event
            self.db.execute("INSERT INTO tasks VALUES (?,?)", (task_id, json.dumps(record, ensure_ascii=False)))
            self.db.commit()
        self.emit({"event": "task.updated", "task": record})

        def run():
            ctx = TaskContext(self, task_id, event)
            try:
                ctx.check()
                self.update(task_id, status="running", started_at=now())
                result = fn(ctx)
                status = "complete"
                if kind == "generation" and result.get("status") == "failed":
                    status = "failed"
                elif kind == "generation" and not result.get("exports_complete"):
                    status = "partial"
                stage = {"complete": "执行完成", "partial": "部分文件未能导出，请查看结果中的失败原因", "failed": "生成未完成，请查看结果中的失败原因"}[status]
                if event.is_set():
                    stage += "；取消请求未中断正在执行的操作"
                self.update(task_id, status=status, result=result, finished_at=now(), stage=stage)
            except Canceled as exc:
                self.update(task_id, status="canceled", stage=str(exc), finished_at=now())
            except Exception as exc:
                self.update(task_id, status="failed", error=str(exc), stage="执行失败", finished_at=now())
            finally:
                with self.lock:
                    self.cancel_events.pop(task_id, None)
        self.pool.submit(run)
        return record

    def cancel(self, task_id):
        with self.lock:
            record = self.get(task_id)
            event = self.cancel_events.get(task_id)
            if event is None or record["status"] not in {"queued", "running"}:
                return record
            event.set()
        return self.update(task_id, cancel_requested=True, stage="已请求取消，等待当前操作安全结束；不会自动撤销")

    def close(self):
        with self.lock:
            pending = list(self.cancel_events)
        for task_id in pending:
            self.cancel(task_id)
        self.pool.shutdown(wait=True)
        self.db.close()

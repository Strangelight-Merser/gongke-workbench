"""真实 ccx 的运行期 GUI/MCP 验收；SIGSTOP/SIGKILL 均为显式测试注入。

只在本轮隔离 endpoint 下观察自己提交的任务。先核对 PID、FreeCAD 父进程、
启动时间和 ccx 命令，再暂停短时任务以形成操作窗口；不替换求解器或结果。
本地原生 API 模拟学生编辑及关闭文档，不代表可访问性点击验收。
"""

import json
import math
import os
from pathlib import Path
import shlex
import signal
import subprocess
import sys
import time
import traceback

sys.path.insert(0, str(Path(__file__).parent))
from native_session_flow import _MCP, _Session, _runs


TERMINAL = {"succeeded", "failed", "cancelled", "interrupted"}


def close_owned_gui(identity, document_names):
    """仅退出命令、PID、启动时间均匹配的专用测试 GUI，先关闭本轮测试文档。"""
    import FreeCAD as App
    import FreeCADGui as Gui

    current = JobLifecycleSession._ps(os.getpid())
    assert current is not None and all(current[k] == identity[k] for k in
                                      ("pid", "ppid", "started", "command")), "GUI 身份已改变，不执行退出"
    assert set(App.listDocuments()).issubset(document_names), "存在本轮之外的文档，不丢弃用户工程"
    for name in list(App.listDocuments()):
        App.closeDocument(name)
    assert Gui.getMainWindow().close(), "专用测试 GUI 未接受退出请求"


class JobLifecycleSession(_Session):
    def __init__(self, output, python, *, owned_gui, keep_open=False):
        import FreeCAD as App

        target = Path(output).resolve()
        endpoint = Path(os.environ["GONGKE_FREECAD_SESSION"]).resolve()
        assert endpoint == target / "freecad-session.json", "必须使用本轮输出目录内的隔离 endpoint"
        assert all(p == endpoint for p in target.iterdir()), "验收目录已有证据，请使用新目录"
        self.run_root = target / "runs"
        self.job_ids = []
        self.owned = {}
        self.process_handles = {}
        self.cases = {}
        self.owned_gui = owned_gui
        self.keep_open = keep_open
        self.gui_close_requested = False
        self.owned_documents = {App.ActiveDocument.Name}
        super().__init__(output, python)

    def _poll(self):
        super()._poll()
        if self.done and not self.keep_open and not self.gui_close_requested:
            self.gui_close_requested = True
            try:
                self._record("gui_exit_requested", {"process": self.owned_gui})
                close_owned_gui(self.owned_gui, self.owned_documents)
            except Exception:
                (self.output / "gui_cleanup_error.txt").write_text(traceback.format_exc(), encoding="utf-8")

    @staticmethod
    def _document_state(doc):
        """只取可读的原生状态，比较任务前后未改动的文档。"""
        from freecad.gongke import native_shaft

        objects = []
        for obj in doc.Objects:
            row = {"name": obj.Name, "label": obj.Label, "type": obj.TypeId}
            if hasattr(obj, "Placement"):
                row["placement"] = list(obj.Placement.toMatrix().A)
            if hasattr(obj, "Shape"):
                row["volume_mm3"] = obj.Shape.Volume
            if obj.TypeId == "Sketcher::SketchObject":
                row["constraints"] = native_shaft._constraint_signature(obj)
                row["geometry"] = [[list(g.StartPoint), list(g.EndPoint)] for g in obj.Geometry]
            if hasattr(obj, "GkMetadata"):
                row["metadata"] = obj.GkMetadata
            for name in ("Length", "Width", "Height"):
                if hasattr(obj, name):
                    row[name] = getattr(obj, name).Value
            objects.append(row)
        return {"name": doc.Name, "label": doc.Label, "objects": objects,
                "undo_names": list(doc.UndoNames)}

    def _perform(self, action, **arguments):
        import FreeCAD as App
        import FreeCADGui as Gui

        if action == "native_state":
            return self._document_state(self.doc)
        if action == "create_other_document":
            self.other_doc = App.newDocument("LifecycleOther" + self.run_id[:8])
            self.owned_documents.add(self.other_doc.Name)
            self.other_doc.UndoMode = 1
            box = self.other_doc.addObject("Part::Box", "StudentBox")
            box.Label = "其他文档原有零件（验收）"
            box.Length, box.Width, box.Height = 7, 11, 13
            box.Placement.Base = App.Vector(2, 3, 5)
            self.other_doc.recompute()
            App.setActiveDocument(self.doc.Name)
            Gui.Selection.clearSelection()
            Gui.Selection.addSelection(self._body())
            return self._document_state(self.other_doc)
        if action == "other_document_state":
            return self._document_state(self.other_doc)
        if action == "close_target":
            # 只关闭本宏新建的教学轴，其他打开文档保持原样。
            name = self.doc.Name
            assert name == arguments["document"]
            Gui.Selection.clearSelection()
            App.closeDocument(name)
            self.doc = None
            App.setActiveDocument(self.other_doc.Name)
            Gui.Selection.addSelection(self.other_doc.getObject("StudentBox"))
            assert name not in App.listDocuments()
            return {"closed_document": name, "active_document": App.ActiveDocument.Name,
                    "other_document": self._document_state(self.other_doc)}
        if action == "reopen_target":
            self.doc = App.openDocument(arguments["path"])
            self.owned_documents.add(self.doc.Name)
            self.doc.UndoMode = 1
            App.setActiveDocument(self.doc.Name)
            Gui.Selection.clearSelection()
            Gui.Selection.addSelection(self._body())
            return {"document": self.doc.Name, "entity_id": self.entity_id}
        return super()._perform(action, **arguments)

    @staticmethod
    def _ps(pid):
        """macOS 实际进程身份；不根据仅有的 PID 发送信号。"""
        result = subprocess.run(
            ["/bin/ps", "-ww", "-p", str(pid), "-o", "pid=", "-o", "ppid=",
             "-o", "stat=", "-o", "lstart=", "-o", "command="],
            capture_output=True, text=True, timeout=2,
        )
        if result.returncode == 1 and not result.stdout.strip():
            return None
        assert result.returncode == 0, result.stderr
        fields = result.stdout.strip().split(None, 8)
        assert len(fields) == 9, result.stdout
        return {"pid": int(fields[0]), "ppid": int(fields[1]), "state": fields[2],
                "started": " ".join(fields[3:8]), "command": fields[8]}

    def _matching_process(self, job_id):
        owned = self.owned[job_id]
        current = self._ps(owned["pid"])
        if current is None:
            return None
        keys = ("pid", "ppid", "started", "command")
        if any(current[key] != owned[key] for key in keys):
            # 原进程已退出且 PID 被复用时，绝不对新进程发送信号。
            return None
        return current

    def _signal(self, job_id, value):
        current = self._matching_process(job_id)
        if current is None:
            return False
        try:
            os.kill(current["pid"], value)
        except ProcessLookupError:
            return False
        self._record("test_signal_injection", {"job_id": job_id, "signal": signal.Signals(value).name,
                                               "process": current, "time": time.time()})
        return True

    def _wait_reaped(self, job_id):
        deadline = time.monotonic() + 5
        while self._matching_process(job_id) is not None:
            assert time.monotonic() < deadline, f"本轮求解器尚未回收：{job_id}"
            time.sleep(.01)
        self._record("solver_reaped", {"job_id": job_id, "pid": self.owned[job_id]["pid"]})

    def _pause_new_job(self, client, identity):
        job = client.tool("run_analysis", **identity)
        job_id = job["job_id"]
        self.job_ids.append(job_id)
        directory = self.run_root / job_id
        path = directory / "status.json"
        deadline = time.monotonic() + 5
        while True:
            record = json.loads(path.read_text(encoding="utf-8"))
            assert record["job_id"] == job_id and Path(record["directory"]).resolve() == directory
            assert all(record["source_context"][k] == v for k, v in identity.items())
            if "pid" in record:
                assert Path(record["solver"]).name == "ccx", "只能暂停实际 ccx，不能使用替身"
                assert record["status"] == "running", record
                # 同一 FreeCAD 进程中的本轮真实 Popen 句柄证明父子归属。
                # 先暂停再运行 ps，避免两次 ps 启动耗时错过约几十毫秒的求解窗口。
                with self.bridge.jobs._lock:
                    process = self.bridge.jobs._processes.get(job_id)
                    assert process is not None and process.pid == record["pid"], "本轮任务没有对应求解器句柄"
                    assert record["input_stem"] == f"shaft-{job_id}"
                    assert process.args == [record["solver"], "-i", record["input_stem"]], process.args
                    assert process.poll() is None, "真实 ccx 已退出，未捕获运行窗口；此项未验收"
                    self.process_handles[job_id] = process
                    process.send_signal(signal.SIGSTOP)
                pause_deadline = time.monotonic() + 1
                while True:
                    stopped = self._ps(record["pid"])
                    assert stopped is not None, "真实 ccx 已在暂停前退出"
                    command = shlex.split(stopped["command"])
                    assert stopped["ppid"] == os.getpid(), stopped
                    assert command == [record["solver"], "-i", record["input_stem"]], stopped
                    if "T" in stopped["state"]:
                        break
                    assert time.monotonic() < pause_deadline, "未确认 ccx 已暂停"
                    time.sleep(.002)
                self.owned[job_id] = stopped
                self._record("test_signal_injection", {"job_id": job_id, "signal": "SIGSTOP",
                                                       "process": stopped, "time": time.time(),
                                                       "ownership_basis": "same_process_job_manager_popen_handle"})
                self._record("verified_paused_solver", {"job_id": job_id, "process": stopped,
                                                        "status_path": str(path), "record": record})
                actual = client.tool("get_job", job_id=job_id)
                assert actual["status"] == "running" and actual["applicability"] == "current", actual
                return actual
            assert record["status"] not in TERMINAL, record
            assert time.monotonic() < deadline, "5 秒内未观察到真实 ccx PID"
            time.sleep(.002)

    @staticmethod
    def _terminal(client, job_id):
        deadline = time.monotonic() + 30
        while True:
            record = client.tool("get_job", job_id=job_id)
            if record["status"] in TERMINAL:
                return record
            assert time.monotonic() < deadline, "真实 ccx 任务 30 秒内未结束"
            time.sleep(.05)

    def _cleanup(self, client):
        errors = []
        # 先恢复所有仍由本轮拥有的暂停进程；不能被 MCP 超时阻挡在 SIGSTOP 状态。
        # 即使暂停后的 ps 核验失败，已保存的本轮 Popen 也必须恢复，避免遗漏清理。
        for job_id, handle in self.process_handles.items():
            try:
                if handle.poll() is None:
                    handle.send_signal(signal.SIGCONT)
                    self._record("cleanup_resume", {"job_id": job_id, "pid": handle.pid})
            except Exception:
                errors.append(traceback.format_exc())
        for job_id in self.job_ids:
            try:
                status = json.loads((self.run_root / job_id / "status.json").read_text())
                if status["status"] not in TERMINAL and client is not None:
                    client.tool("cancel_job", job_id=job_id)
            except Exception:
                errors.append(traceback.format_exc())
            finally:
                if job_id in self.owned:
                    try:
                        if self._matching_process(job_id) is not None:
                            self._signal(job_id, signal.SIGKILL)
                        self._wait_reaped(job_id)
                    except Exception:
                        errors.append(traceback.format_exc())
                elif job_id in self.process_handles:
                    # ps 身份核验未完成的异常路径，只回收自己持有的子进程句柄。
                    try:
                        handle = self.process_handles[job_id]
                        if handle.poll() is None:
                            handle.kill()
                        handle.wait(timeout=5)
                    except Exception:
                        errors.append(traceback.format_exc())
        return errors

    def _execute(self):
        client = None
        result = None
        error = None
        started = time.monotonic()
        try:
            assert self.bridge.endpoint.resolve() == self.output / "freecad-session.json"
            client = _MCP(self.python, self.bridge.endpoint, self.output, self._record)
            initialized = client.rpc("initialize", {"protocolVersion": "2025-11-25", "capabilities": {},
                                      "clientInfo": {"name": "gongke-job-lifecycle-test", "version": "1"}})
            client.rpc("notifications/initialized", notification=True)
            context = client.tool("get_project_context")
            assert self.entity_id in context["selection"]
            identity = {"session_id": context["session_id"], "entity_id": self.entity_id}
            baseline = client.tool("read_engineering_object", **identity)
            assert math.isclose(self._diameter(baseline), .04)

            # 真实任务先固定 40 mm 快照，暂停期间原生手改为 38 mm。
            running = self._pause_new_job(client, identity)
            self._local("manual_diameter", diameter_m=.038)
            changed = client.tool("read_engineering_object", **identity)
            assert changed["content_hash"] != baseline["content_hash"]
            during = client.tool("get_job", job_id=running["job_id"])
            assert during["status"] == "running" and during["applicability"] == "stale", during
            assert self._signal(running["job_id"], signal.SIGCONT)
            completed = self._terminal(client, running["job_id"])
            assert completed["status"] == "succeeded" and completed["applicability"] == "stale", completed
            assert completed["source_context"]["content_hash"] == baseline["content_hash"]
            frozen = json.loads((Path(completed["directory"]) / "snapshot.json").read_text())
            assert frozen == baseline["snapshot"]
            assert client.tool("read_engineering_object", **identity)["content_hash"] == changed["content_hash"]
            self._wait_reaped(running["job_id"])
            self.cases["edit_while_running"] = {"running": running, "after_edit": during, "completed": completed}
            self.checks.append("native_edit_while_real_solver_running_keeps_immutable_input_and_stale_result")
            self._local("native_undo", transaction="学生手动改径")
            assert client.tool("read_engineering_object", **identity)["content_hash"] == baseline["content_hash"]

            # 暂停中的真实 ccx 由产品取消路径终止；包括其已有的超时强制回收。
            native_before = self._local("native_state")
            running = self._pause_new_job(client, identity)
            cancelled = client.tool("cancel_job", job_id=running["job_id"])
            assert cancelled["status"] == "cancelled" and cancelled["applicability"] == "current", cancelled
            assert "result" not in cancelled
            self._wait_reaped(running["job_id"])
            assert client.tool("read_engineering_object", **identity)["content_hash"] == baseline["content_hash"]
            assert self._local("native_state") == native_before
            self.cases["cancel_running_solver"] = {"running": running, "cancelled": cancelled, "cad_unchanged": True}
            self.checks.append("mcp_cancel_reaps_verified_real_solver_and_preserves_native_document")

            project = self.output / "lifecycle_target.FCStd"
            client.tool("save_project", session_id=identity["session_id"], path=str(project))
            other_before = self._local("create_other_document")
            running = self._pause_new_job(client, identity)
            closed = self._local("close_target", document=context["document"])
            assert closed["other_document"] == other_before
            during = client.tool("get_job", job_id=running["job_id"])
            assert during["status"] == "running" and during["applicability"] == "missing", during
            assert self._signal(running["job_id"], signal.SIGCONT)
            completed = self._terminal(client, running["job_id"])
            assert completed["status"] == "succeeded" and completed["applicability"] == "missing", completed
            self._wait_reaped(running["job_id"])
            assert self._local("other_document_state") == other_before
            client.tool("read_engineering_object", expect_error=True, **identity)
            self.cases["close_target_while_running"] = {
                "running": running, "after_close": during, "completed": completed, "other_document_unchanged": True}
            self.checks.append("closing_target_during_real_solver_leaves_missing_result_and_other_document_unchanged")

            self._local("reopen_target", path=str(project))
            reopened = client.tool("get_project_context")
            assert reopened["session_id"] != identity["session_id"]
            identity = {"session_id": reopened["session_id"], "entity_id": self.entity_id}
            assert client.tool("read_engineering_object", **identity)["content_hash"] == baseline["content_hash"]
            native_before = self._local("native_state")
            running = self._pause_new_job(client, identity)
            assert self._signal(running["job_id"], signal.SIGKILL)
            failed = self._terminal(client, running["job_id"])
            assert failed["status"] == "failed" and failed["applicability"] == "current", failed
            assert "result" not in failed and "ccx 计算失败" in failed["error"], failed
            self._wait_reaped(running["job_id"])
            directory = Path(failed["directory"])
            log = directory / "stdout.log"
            assert log.is_file() and (directory / f"{failed['input_stem']}.inp").is_file()
            assert not (directory / "result.json").exists()
            assert client.tool("read_engineering_object", **identity)["content_hash"] == baseline["content_hash"]
            assert self._local("native_state") == native_before
            self.cases["terminated_real_solver"] = {
                "running": running, "failed": failed, "cad_unchanged": True,
                "stdout_path": str(log), "stdout_bytes": log.stat().st_size,
                "stdout_tail": log.read_text(errors="replace").splitlines()[-15:]}
            self.checks.append("terminated_real_ccx_returns_failed_with_retained_log_and_unchanged_native_document")

            client.tool("save_project", session_id=identity["session_id"])
            image = self._local("capture_view")
            result = {"ok": True, "run_id": self.run_id, "freecad_version": self.version,
                      "mcp_protocol": initialized["protocolVersion"], "checks": self.checks,
                      "cases": self.cases, "mcp_working_directory": str(client.root),
                      "endpoint": str(self.bridge.endpoint), "saved_project": str(project), "image": image,
                      "keep_open": self.keep_open,
                      "scope": "真实 FreeCAD、独立 stdio MCP 和 ccx；SIGSTOP 形成运行窗口，SIGKILL 注入求解器异常退出；本地原生 API 模拟学生动作；未覆盖 GUI 重启 interrupted。"}
        except Exception:
            error = traceback.format_exc()
        finally:
            cleanup_errors = self._cleanup(client)
            if client is not None:
                try:
                    client.close()
                except Exception:
                    cleanup_errors.append(traceback.format_exc())
            try:
                if error is not None or cleanup_errors:
                    failure = {"ok": False, "run_id": self.run_id, "checks": self.checks,
                               "cases": self.cases, "error": error, "cleanup_errors": cleanup_errors}
                    (self.output / "shaft_job_lifecycle_failed.json").write_text(
                        json.dumps(failure, ensure_ascii=False, indent=2), encoding="utf-8")
                    (self.output / "shaft_job_lifecycle_error.txt").write_text(
                        (error or "") + "\n" + "\n".join(cleanup_errors), encoding="utf-8")
                else:
                    result.update(cleanup_complete=True, elapsed_seconds=time.monotonic() - started)
                    (self.output / "shaft_job_lifecycle.json").write_text(
                        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            finally:
                self.done = True


def start(output_dir, external_python, *, owned_gui, keep_open=False):
    session = JobLifecycleSession(output_dir, external_python, owned_gui=owned_gui, keep_open=keep_open)
    _runs.append(session)
    return session

"""JSON-lines service. Standard output contains protocol messages only."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import sys
import threading

from gongke_app import __version__
from gongke_app.agent.provider import Provider
from gongke_app.commands import Commands, validate, schema, TEXT, BOOL, TASK
from gongke_app.hosts import Hosts
from gongke_app.project import Project
from gongke_app.tasks import Tasks


class Application:
    def __init__(self, state_dir: Path, emit=lambda event: None):
        self.emit, self.project, self.provider = emit, None, None
        self.tasks = Tasks(state_dir, emit)
        self.hosts = Hosts()
        self.commands = Commands(self.hosts)

    def current(self):
        if self.project is None:
            raise ValueError("请先创建或打开工程")
        return self.project

    def dispatch(self, method, params):
        if not isinstance(method, str) or not isinstance(params, dict):
            raise ValueError("请求需要 method 字符串和 params 对象")
        if method == "system.status":
            validate(params, schema())
            return {"version": __version__, "ready": True, "python": sys.version.split()[0],
                    "packaged": bool(getattr(sys, "frozen", False)),
                    "agent": self.provider.status() if self.provider else {"configured": False, "connection": "未连接模型服务"},
                    "project": str(self.project.path) if self.project else None}
        if method == "project.create":
            validate(params, schema({"path": TEXT, "name": TEXT, "teaching": BOOL}, ["path"]))
            self.project = Project.create(**params)
            return self.project.view()
        if method == "project.open":
            validate(params, schema({"path": TEXT}, ["path"]))
            self.project = Project.open(**params)
            return self.project.view()
        if method == "project.set_task":
            validate(params, schema({"task": TASK, "teaching": BOOL}, ["task"]))
            return self.current().set_task(**params)
        if method == "task.list":
            validate(params, schema())
            return self.tasks.list(str(self.project.path) if self.project else None)
        if method in {"task.get", "task.cancel"}:
            validate(params, schema({"task_id": TEXT}, ["task_id"]))
            return (self.tasks.get if method == "task.get" else self.tasks.cancel)(**params)
        if method == "agent.configure":
            validate(params, schema({"base_url": TEXT, "model": TEXT, "api_key": TEXT}, ["base_url", "model", "api_key"]))
            self.provider = Provider(**params)
            return self.provider.status()
        if method == "agent.disconnect":
            validate(params, schema())
            self.provider = None
            return {"configured": False}
        if method == "agent.run":
            validate(params, schema({"message": TEXT, "allow_writes": BOOL}, ["message"]))
            if self.provider is None:
                raise ValueError("未连接模型服务，请在设置中填写服务地址、模型名称和 API Key；手动工程操作仍可使用")
            if not params["message"].strip():
                raise ValueError("请输入工程任务")
            project, provider = self.current(), self.provider
            from gongke_app.agent.loop import run
            return self.tasks.start("agent", project.path, lambda ctx: run(
                provider, self.commands, project, params["message"], params.get("allow_writes", False), ctx, self.emit))
        if method == "design.generate":
            validate(params, self.commands.definitions[method][1])
            project = self.current()
            project.task(params.get("task"))
            return self.tasks.start("generation", project.path, lambda ctx: self.commands.call(method, params, project, ctx))
        if method == "hosts.list":
            validate(params, schema())
            return self.hosts.list()
        if method == "host.command":
            validate(params, schema({"host_id": TEXT, "method": TEXT, "params": TASK}, ["host_id", "method", "params"]))
            return self.hosts.command(**params, project=self.current())
        # These two commands need no project and can populate the welcome screen.
        if (method in {"design.example", "design.schema"} or
                (method.startswith("freecad.") and method in self.commands.definitions
                 and not self.commands.definitions[method][2])):
            return self.commands.call(method, params, self.project)
        return self.commands.call(method, params, self.current())

    def close(self):
        self.tasks.close()


class InstanceLock:
    def __init__(self, state_dir):
        state_dir.mkdir(parents=True, exist_ok=True)
        self.file = (state_dir / "service.lock").open("a+b")
        try:
            if os.name == "nt":
                import msvcrt
                self.file.seek(0)
                if not self.file.read(1):
                    self.file.write(b"0")
                    self.file.flush()
                self.file.seek(0)
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.file.close()
            raise ValueError("此应用状态目录已有服务运行，请关闭重复实例") from None

    def close(self):
        self.file.close()


def main():
    # Pipes use the Windows locale by default; the desktop protocol is always UTF-8.
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-dir", type=Path, default=Path.home() / ".local/share/gongke/app")
    args = parser.parse_args()
    # Legacy libraries may print; isolate their output from the protocol stream.
    protocol = sys.stdout
    sys.stdout = sys.stderr
    output_lock = threading.Lock()

    def emit(message):
        with output_lock:
            protocol.write(json.dumps(message, ensure_ascii=False, allow_nan=False) + "\n")
            protocol.flush()

    instance = None
    app = None
    diagnostic_file = None
    try:
        # Only the isolated desktop test enables stack-only diagnostics; no locals
        # or request contents are recorded, and normal application runs create no log.
        diagnostics = os.environ.get("GONGKE_TEST_DIAGNOSTICS_DIR")
        if diagnostics:
            import faulthandler
            directory = Path(diagnostics).resolve()
            directory.mkdir(parents=True, exist_ok=True)
            diagnostic_file = (directory / "python-threads.log").open("a", encoding="utf-8")
            faulthandler.enable(file=diagnostic_file, all_threads=True)
            faulthandler.dump_traceback_later(60, repeat=True, file=diagnostic_file)
        instance = InstanceLock(args.state_dir)
        # NumPy's Windows native initialization can deadlock against a concurrent
        # pipe-stdin read (numpy/numpy#24290). Load the installed drawing runtime
        # before starting workers and entering the protocol input loop.
        if importlib.util.find_spec("numpy") is not None:
            import numpy  # noqa: F401
        app = Application(args.state_dir, emit)
        for line in sys.stdin:
            request_id = None
            try:
                request = json.loads(line, parse_constant=lambda value: (_ for _ in ()).throw(ValueError("数值必须有限")))
                if not isinstance(request, dict) or "id" not in request:
                    raise ValueError("请求必须是包含 id 的 JSON 对象")
                request_id = request["id"]
                result = app.dispatch(request.get("method"), request.get("params", {}))
                emit({"id": request_id, "result": result})
            except Exception as exc:
                emit({"id": request_id, "error": {"message": str(exc)}})
    except Exception as exc:
        emit({"event": "service.error", "error": {"message": str(exc)}})
        return 1
    finally:
        if app:
            app.close()
        if instance:
            instance.close()
        if diagnostic_file:
            faulthandler.cancel_dump_traceback_later()
            faulthandler.disable()
            diagnostic_file.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

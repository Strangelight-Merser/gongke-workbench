"""JSON-lines service. Standard output contains protocol messages only."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import threading
from uuid import uuid4

from gongke_app import __version__
from gongke_app.commands import Commands
from gongke_app.tools import validate, schema, TEXT, BOOL, TASK
from gongke_app.hosts import Hosts, READ_METHODS
from gongke_app.project import Project
from gongke_app.tasks import Tasks


class Application:
    def __init__(self, state_dir: Path, emit=lambda event: None):
        self.state_dir = state_dir.resolve()
        self.lock = threading.RLock()
        self.project_epoch = uuid4().hex
        self.bindings = {}
        self.emit, self.project = emit, None
        self.tasks = Tasks(state_dir, emit)
        self.hosts = Hosts()
        self.commands = Commands(self.hosts)
        from gongke_app.freecad_lifecycle import FreeCADLifecycle
        self.freecad = FreeCADLifecycle()

    def current(self):
        if self.project is None:
            raise ValueError("请先创建或打开工程")
        return self.project

    def dispatch(self, method, params):
        with self.lock:
            return self._dispatch(method, params)

    def bind(self, project, allow_writes=False):
        with self.lock:
            validate({"project": project, "allow_writes": allow_writes}, schema({"project": TEXT, "allow_writes": BOOL}, ["project"]))
            current = self.current()
            if Path(project).expanduser().resolve() != current.path:
                raise ValueError("请求绑定的工程不是桌面当前工程；请先在桌面打开该工程")
            binding = {"binding_id": uuid4().hex, "project": str(current.path),
                       "epoch": self.project_epoch, "allow_writes": allow_writes}
            self.bindings[binding["binding_id"]] = binding
            return binding

    def bound(self, binding_id):
        binding = self.bindings.get(binding_id)
        if binding is None or binding["epoch"] != self.project_epoch:
            raise ValueError("工程绑定已失效；请在目标工程重新连接 MCP，旧连接不会跟随切换")
        return binding

    def bound_tools(self, binding_id):
        with self.lock:
            binding = self.bound(binding_id)
            return [{"name": name, "description": desc, "inputSchema": definition,
                     "annotations": {"readOnlyHint": not write, "openWorldHint": False}}
                    for name, (desc, definition, write) in self.commands.definitions.items()
                    if binding["allow_writes"] or not write]

    def bound_call(self, binding_id, method, params, task_id):
        with self.lock:
            binding = self.bound(binding_id)
            project = self.current()
            # 先登记任务再释放锁；切换工程与接收命令不能交错。
            fn = self.commands.submission(method, params, project, allow_writes=binding["allow_writes"])
            return self.tasks.start("generation" if method == "design.generate" else "mcp", project.path, fn, task_id=task_id)

    def bound_task(self, binding_id, task_id, *, cancel=False):
        with self.lock:
            binding = self.bindings.get(binding_id)
            record = self.tasks.get(task_id)
            if binding is None or record["project"] != binding["project"]:
                raise ValueError("任务不属于绑定工程")
            return self.tasks.cancel(task_id) if cancel else record

    def _dispatch(self, method, params):
        if not isinstance(method, str) or not isinstance(params, dict):
            raise ValueError("请求需要 method 字符串和 params 对象")
        if method == "freecad.connect":
            validate(params, schema({"executable": TEXT}))
            return self.freecad.connect(**params)
        if method == "system.prepare_close":
            validate(params, schema())
            if self.project and self.tasks.active(str(self.project.path)):
                raise ValueError("当前工程仍有任务执行中，请等待结束或取消后退出")
            return self.freecad.close()
        if method == "system.status":
            validate(params, schema())
            return {"version": __version__, "ready": True, "python": sys.version.split()[0],
                    "packaged": bool(getattr(sys, "frozen", False)),
                    "project": str(self.project.path) if self.project else None}
        if method in {"project.create", "project.open"} and self.project and self.tasks.active(str(self.project.path)):
            raise ValueError("当前工程仍有任务执行中，请等待结束或取消后切换工程")
        if method == "project.create":
            validate(params, schema({"path": TEXT, "name": TEXT, "teaching": BOOL}, ["path"]))
            self.project = Project.create(**params)
            self.project_epoch = uuid4().hex
            return self.project.view()
        if method == "project.open":
            validate(params, schema({"path": TEXT}, ["path"]))
            self.project = Project.open(**params)
            self.project_epoch = uuid4().hex
            for record in self.project.manifest["results"]:
                if record.get("status") == "running":
                    self.project.update_result(record["path"], {"status": "interrupted", "error": "上次生成中断；已保留实际文件，请生成新修订"})
            return self.project.view()
        if method == "tools.list":
            validate(params, schema())
            return [{"name": name, "description": desc, "inputSchema": definition, "write": write}
                    for name, (desc, definition, write) in self.commands.definitions.items()]
        if method == "mcp.configure":
            validate(params, schema({"allow_writes": BOOL, "confirm_user_config": BOOL}, ["allow_writes"]))
            from gongke_app.connection import write_workbuddy
            packaged = bool(getattr(sys, "frozen", False))
            return write_workbuddy(self.current(), self.state_dir, Path(sys.executable), params["allow_writes"],
                                  confirm_user_config=params.get("confirm_user_config", False),
                                  prefix=() if packaged else ("-m", "gongke_app"),
                                  env=None if packaged else {"PYTHONPATH": str(Path(__file__).resolve().parent.parent)})
        if method == "task.list":
            validate(params, schema())
            return self.tasks.list(str(self.project.path) if self.project else None)
        if method in {"task.get", "task.cancel"}:
            validate(params, schema({"task_id": TEXT}, ["task_id"]))
            return (self.tasks.get if method == "task.get" else self.tasks.cancel)(**params)
        if method == "design.generate":
            project = self.current()
            return self.tasks.start("generation", project.path, self.commands.submission(method, params, project))
        if method == "host.command":
            validate(params, schema({"host_id": TEXT, "method": TEXT, "params": TASK}, ["host_id", "method", "params"]))
            method = "host.read" if params["method"] in READ_METHODS else "host.write"
        # These two commands need no project and can populate the welcome screen.
        if (method in {"design.example", "design.schema", "hosts.list"} or
                (self.project is None and method.startswith("freecad.") and method in self.commands.definitions
                 and not self.commands.definitions[method][2])):
            return self.commands.call(method, params, self.project)
        project = self.current()
        definition = self.commands.definitions.get(method)
        if definition and (definition[2] or method in {"design.calculate", "revision.inspect", "freecad.review", "freecad.preview", "freecad.preview_fillet", "host.check"}):
            return self.tasks.start("command", project.path,
                                    lambda ctx: self.commands.call(method, params, project, ctx), inline=True)
        return self.commands.call(method, params, project)

    def close(self):
        self.tasks.close()
        self.freecad.close()


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


def _private_protocol_input():
    """在 Windows 上把协议输入移到私有句柄，标准输入改指 NUL。

    同步管道上有一个线程阻塞在 ReadFile 时，其他线程对同一句柄的 GetFileType
    等调用也会阻塞。后台任务首次加载的原生库（NumPy、SciPy、OCCT 等）在 CRT
    初始化时会查询标准句柄，因而与协议读取互锁（numpy/numpy#24290）。逐个预先
    import 无法覆盖全部库，所以不让任何库再看到正在读取的管道句柄。
    """
    if sys.platform != "win32":
        return sys.stdin
    import ctypes
    import msvcrt

    private = os.dup(sys.stdin.fileno())
    null = os.open(os.devnull, os.O_RDONLY)
    os.dup2(null, 0)
    os.close(null)
    STD_INPUT_HANDLE = -10
    ctypes.windll.kernel32.SetStdHandle(STD_INPUT_HANDLE, msvcrt.get_osfhandle(0))
    sys.stdin = open(os.devnull, encoding="utf-8")
    return open(private, encoding="utf-8", newline="\n")


def main():
    if len(sys.argv) > 1 and sys.argv[1] in {"mcp", "call", "workbuddy", "inspect-revision"}:
        from gongke_app.cli import main as client_main
        return client_main(sys.argv[1:])
    # Pipes use the Windows locale by default; the desktop protocol is always UTF-8.
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    protocol_input = _private_protocol_input()
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
    connection = None
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
        app = Application(args.state_dir, emit)
        from gongke_app.connection import ConnectionServer
        connection = ConnectionServer(app, args.state_dir)
        for line in protocol_input:
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
        if connection:
            connection.close()
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

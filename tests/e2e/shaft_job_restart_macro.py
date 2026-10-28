"""专用隔离 GUI 的真实任务崩溃/恢复两阶段；由 restart controller 启动。"""

import hashlib
import json
import os
from pathlib import Path
import sys
import time
import traceback

import FreeCAD as App
import FreeCADGui as Gui

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).parent))
from native_session_flow import _MCP, _Session, _runs
from shaft_job_lifecycle_flow import JobLifecycleSession


def write_json(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2), encoding="utf-8")
    temporary.replace(path)


class RestartSession(JobLifecycleSession):
    # 此路径由外部 controller 回收 GUI，不能继承 lifecycle 的进程内退出动作。
    _poll = _Session._poll

    def __init__(self, output, phase, python):
        self.shared = output
        self.phase = phase
        self.run_root = output / "runs"
        self.job_ids = []
        self.owned = {}
        self.process_handles = {}
        self.cases = {}
        _Session.__init__(self, output / phase, python)

    def _execute(self):
        client = None
        error = None
        try:
            client = _MCP(self.python, self.bridge.endpoint, self.output, self._record)
            client.rpc("initialize", {"protocolVersion": "2025-11-25", "capabilities": {},
                                      "clientInfo": {"name": "gongke-job-restart-test", "version": "1"}})
            client.rpc("notifications/initialized", notification=True)
            context = client.tool("get_project_context")
            identity = {"session_id": context["session_id"], "entity_id": self.entity_id}
            current = client.tool("read_engineering_object", **identity)
            assert current["supported"]
            project = self.shared / "restart_shaft.FCStd"
            if self.phase == "before_crash":
                client.tool("save_project", session_id=identity["session_id"], path=str(project))
                running = self._pause_new_job(client, identity)
                directory = Path(running["directory"])
                input_sha256 = {name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
                                for name in ("snapshot.json", "source_context.json", f"{running['input_stem']}.inp")}
                ready = {
                    "gui_pid": os.getpid(), "phase": self.phase, "job": running,
                    "solver_process": self.owned[running["job_id"]],
                    "saved_project": str(project), "project_sha256": hashlib.sha256(project.read_bytes()).hexdigest(),
                    "input_sha256": input_sha256,
                    "current_object": current, "freecad_version": self.version,
                    "user_data": App.getUserAppDataDir(), "mcp_root": str(client.root),
                    "scope": "真实 ccx 已由测试 Popen 句柄 SIGSTOP；等待专用 GUI 被 controller 非正常终止，未改写 status。",
                }
                write_json(self.shared / "ready_for_crash.json", ready)
                # controller 异常退出时仍会在有限时间内恢复和取消自己的 solver。
                deadline = time.monotonic() + 45
                while time.monotonic() < deadline:
                    time.sleep(.1)
                raise TimeoutError("controller 未在 45 秒内终止专用 GUI；恢复并回收测试求解器")
            else:
                ready = json.loads((self.shared / "ready_for_crash.json").read_text())
                assert os.getpid() != ready["gui_pid"]
                assert identity["session_id"] != ready["current_object"]["session_id"]
                assert current["content_hash"] == ready["current_object"]["content_hash"]
                assert current["snapshot"] == ready["current_object"]["snapshot"]
                assert hashlib.sha256(project.read_bytes()).hexdigest() == ready["project_sha256"]
                job = client.tool("get_job", job_id=ready["job"]["job_id"])
                assert job["status"] == "interrupted" and job["applicability"] == "current", job
                cleanup_status = job["recovery_cleanup"]["status"]
                assert cleanup_status in ("terminated", "already_exited"), job
                assert self._ps(ready["solver_process"]["pid"]) is None
                assert "result" not in job and not (Path(job["directory"]) / "result.json").exists()
                assert job["source_context"] == ready["job"]["source_context"]
                assert {name: hashlib.sha256((Path(job["directory"]) / name).read_bytes()).hexdigest()
                        for name in ready["input_sha256"]} == ready["input_sha256"]
                image = self._local("capture_view")
                write_json(self.shared / "restarted_session.json", {
                    "ok": True, "gui_pid": os.getpid(), "freecad_version": self.version,
                    "job": job, "current_object": current, "saved_project": str(project), "image": image,
                    "project_sha256": ready["project_sha256"], "input_sha256": ready["input_sha256"],
                    "model_unchanged": True, "inputs_unchanged": True,
                    "scope": ("新的 GUI/桥将旧任务标为 interrupted，原 PID 已消失且无成功结果，输入和原生工程保持一致。"
                              + ("产品按已保存身份终止了 ccx。" if cleanup_status == "terminated"
                                 else "产品恢复时 ccx 已退出；本次不证明产品主动终止了它，也未确定退出原因。")),
                })
        except Exception:
            error = traceback.format_exc()
        finally:
            cleanup_errors = self._cleanup(client)
            if client is not None:
                try:
                    client.close()
                except Exception:
                    cleanup_errors.append(traceback.format_exc())
            if error or cleanup_errors:
                write_json(self.output / "macro_failure.json", {"error": error, "cleanup_errors": cleanup_errors})
            self.done = True


output = Path(os.environ["GONGKE_RESTART_OUT"]).resolve()
phase = os.environ["GONGKE_RESTART_PHASE"]
assert phase in ("before_crash", "after_restart")
profile = output / "profile"
write_json(output / phase / "macro_started.json", {
    "pid": os.getpid(), "phase": phase, "user_data": App.getUserAppDataDir(),
    "user_parameter": App.ConfigGet("UserParameter"), "system_parameter": App.ConfigGet("SystemParameter"),
})
assert Path(App.getUserAppDataDir()).resolve() == profile, "必须使用已存在的隔离 FREECAD_USER_HOME"
endpoint = output / "freecad-session.json"
assert Path(os.environ["GONGKE_FREECAD_SESSION"]).resolve() == endpoint
from freecad.gongke import bridge, native_shaft
installed = profile / "Mod/GongKeWorkbench"
assert Path(native_shaft.__file__).is_relative_to(installed)
assert Path(bridge.__file__).is_relative_to(installed)
assert Path(os.environ["GONGKE_MCP_ROOT"]).resolve() == installed
if bridge._bridge is not None:
    assert bridge._bridge.endpoint.resolve() == endpoint
Gui.activateWorkbench("GongKeWorkbench")
assert bridge._bridge.endpoint.resolve() == endpoint
owner = json.loads(endpoint.read_text())
assert owner["pid"] == os.getpid() and owner["token"] == bridge._bridge.token
if phase == "before_crash":
    Gui.runCommand("GongKe_NativeShaft")
else:
    doc = App.openDocument(str(output / "restart_shaft.FCStd"))
    doc.UndoMode = 1
    body = next(obj for obj in doc.Objects if hasattr(obj, "GkEntityId") and native_shaft.supported(obj))
    App.setActiveDocument(doc.Name)
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(body)
session = RestartSession(output, phase, os.environ["GONGKE_EXTERNAL_PYTHON"])
_runs.append(session)

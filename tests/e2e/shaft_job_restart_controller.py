"""仅管理自己创建的两次后台 GUI，验证真实异常退出后的 interrupted 恢复。

运行：python tests/e2e/shaft_job_restart_controller.py --out <全新目录>
默认回收本轮 GUI；仅 --keep-open 显式保留成功后的第二个窗口。
保留原始 running 状态、输入、真实 solver 身份、崩溃动作及重启 MCP 记录。
SIGSTOP/SIGKILL 是验收注入，不是产品的日常退出路径。
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.install_freecad_workbench import install
from shaft_job_lifecycle_flow import JobLifecycleSession


APP = Path("/Applications/FreeCAD.app")
MACRO = ROOT / "tests/e2e/shaft_job_restart_macro.py"


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2), encoding="utf-8")


def current_owned(identity, allow_reparent=False):
    current = JobLifecycleSession._ps(identity["pid"])
    keys = ("pid", "started", "command") if allow_reparent else ("pid", "ppid", "started", "command")
    return current if current is not None and all(current[k] == identity[k] for k in keys) else None


def send(identity, value, events, allow_reparent=False):
    current = current_owned(identity, allow_reparent)
    if current is None:
        return False
    try:
        os.kill(current["pid"], value)
    except ProcessLookupError:
        return False
    events.append({"time": time.time(), "signal": signal.Signals(value).name, "process": current,
                   "allow_reparent": allow_reparent})
    return True


def wait_gone(identity, allow_reparent=False):
    deadline = time.monotonic() + 10
    while current_owned(identity, allow_reparent) is not None:
        if time.monotonic() >= deadline:
            raise TimeoutError(f"本轮进程未回收：{identity['pid']}")
        time.sleep(.05)


def wait_json(path, failure_path, timeout=45):
    deadline = time.monotonic() + timeout
    while not path.is_file():
        if failure_path.is_file():
            raise RuntimeError(failure_path.read_text())
        if time.monotonic() >= deadline:
            raise TimeoutError(f"未生成本轮证据：{path}")
        time.sleep(.1)
    return json.loads(path.read_text())


def find_launched_guis(command, existing_pids):
    """独有宏路径确定本轮启动；不依赖可能尚未执行的宏写出 PID。"""
    result = subprocess.run(["/bin/ps", "-ww", "-axo", "pid=,command="],
                            capture_output=True, text=True, check=True, timeout=2)
    identities = []
    for line in result.stdout.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) != 2 or parts[1] != command:
            continue
        pid = int(parts[0])
        if pid in existing_pids:
            continue
        identity = JobLifecycleSession._ps(pid)
        if identity is not None and identity["command"] == command:
            identities.append(identity)
    return identities


def stop_gui(identity, events, *, keep_open=False):
    """仅回收身份仍匹配的自建 GUI；异常退出不留后台窗口。"""
    if keep_open:
        return
    send(identity, signal.SIGTERM, events)
    wait_gone(identity)


def run(output, keep_open=False):
    output.mkdir(parents=True, exist_ok=False)
    profile = output / "profile"
    profile.mkdir()
    (profile / "temp").mkdir()
    installed = install(profile / "Mod")
    before_dir, after_dir = output / "before_crash", output / "after_restart"
    before_dir.mkdir()
    after_dir.mkdir()
    # 启动前的全部 PID 不属于 controller；即便并发有其他 GUI 也不能由本测试管理。
    existing_pids = {int(s) for s in subprocess.run(["/bin/ps", "-axo", "pid="],
                    capture_output=True, text=True, check=True).stdout.split()}
    events, guis, launches = [], [], []
    solver = None
    result = None
    error = None
    cleanup_errors = []

    def remember_launch(phase, command):
        found = find_launched_guis(command, existing_pids)
        for identity in found:
            if not any(all(old[k] == identity[k] for k in ("pid", "started", "command")) for old in guis):
                guis.append(identity)
                events.append({"phase": phase, "gui_discovered": identity, "time": time.time()})
        write_json(output / "controller_processes.json", {"guis": guis, "events": events})
        return found

    def launch(phase):
        directory = output / phase
        # 每阶段使用新输出目录中的独有路径；run_path 保留原宏的 __file__/ROOT。
        launch_macro = directory / "launch_restart.py"
        launch_macro.write_text(f"import runpy\nrunpy.run_path({str(MACRO)!r}, run_name='__main__')\n")
        command = f"{APP}/Contents/Resources/bin/freecad {launch_macro}"
        launches.append((phase, command))
        env = {
            "FREECAD_USER_HOME": str(profile), "FREECAD_USER_DATA": str(profile),
            "FREECAD_USER_TEMP": str(profile / "temp"),
            "GONGKE_RESTART_OUT": str(output), "GONGKE_RESTART_PHASE": phase,
            "GONGKE_FREECAD_SESSION": str(output / "freecad-session.json"),
            "GONGKE_EXTERNAL_PYTHON": sys.executable, "GONGKE_MCP_ROOT": str(installed),
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        args = ["/usr/bin/open", "-g", "-n", "-a", str(APP)]
        for key, value in env.items():
            args.extend(["--env", f"{key}={value}"])
        args.extend(["-o", str(directory / "gui_stdout.log"), "--stderr", str(directory / "gui_stderr.log"),
                     "--args", str(launch_macro)])
        subprocess.run(args, check=True, capture_output=True, text=True)
        deadline = time.monotonic() + 10
        while True:
            identities = remember_launch(phase, command)
            if identities:
                assert len(identities) == 1, "本轮独有宏对应多个进程；全部登记后停止验收"
                identity = identities[0]
                break
            if time.monotonic() >= deadline:
                raise TimeoutError(f"没有发现本轮宏对应的 GUI 进程：{launch_macro}")
            time.sleep(.05)
        started = wait_json(directory / "macro_started.json", directory / "macro_failure.json")
        assert started["pid"] == identity["pid"] and current_owned(identity) is not None
        assert Path(started["user_data"]).resolve() == profile
        assert Path(started["user_parameter"]).is_relative_to(profile)
        assert Path(started["system_parameter"]).is_relative_to(profile)
        events.append({"phase": phase, "gui": identity, "profile": started, "time": time.time()})
        write_json(output / "controller_processes.json", {"guis": guis, "events": events})
        print(json.dumps({"phase": phase, "pid": identity["pid"], "output": str(output)}), flush=True)
        return identity

    try:
        first = launch("before_crash")
        ready = wait_json(output / "ready_for_crash.json", before_dir / "macro_failure.json")
        assert ready["gui_pid"] == first["pid"] and current_owned(first) is not None
        solver = ready["solver_process"]
        active_solver = current_owned(solver)
        assert active_solver is not None and active_solver["ppid"] == first["pid"]
        assert "T" in active_solver["state"], "必须先确认本轮真实求解器已暂停"
        assert ready["job"]["input_stem"] == f"shaft-{ready['job']['job_id']}"
        assert active_solver["command"] == f"{ready['job']['solver']} -i {ready['job']['input_stem']}"
        assert Path(ready["saved_project"]) == output / "restart_shaft.FCStd"
        project = Path(ready["saved_project"])
        assert hashlib.sha256(project.read_bytes()).hexdigest() == ready["project_sha256"]
        job_dir = output / "runs" / ready["job"]["job_id"]
        assert Path(ready["job"]["directory"]) == job_dir
        status_before = json.loads((job_dir / "status.json").read_text())
        assert status_before["status"] == "running" and status_before["pid"] == solver["pid"]
        assert {name: hashlib.sha256((job_dir / name).read_bytes()).hexdigest()
                for name in ready["input_sha256"]} == ready["input_sha256"]
        assert "result" not in status_before and not (job_dir / "result.json").exists()
        write_json(output / "pre_crash_status.json", status_before)
        # 只崩溃新建且已核对 profile/命令/启动时间的专用 GUI，绕过正常 close 的 cancel。
        assert send(first, signal.SIGKILL, events)
        wait_gone(first)
        # GUI 崩溃后 solver 可能仍活着、成为僵尸或已经退出；如实记录，不指定其退出原因。
        observed_solver = JobLifecycleSession._ps(solver["pid"])
        if observed_solver is None:
            solver_state = "absent"
        elif observed_solver["started"] != solver["started"]:
            solver_state = "identity_mismatch"
        elif "Z" in observed_solver["state"]:
            solver_state = "zombie"
        elif observed_solver["command"] == solver["command"]:
            solver_state = "alive"
        else:
            solver_state = "identity_mismatch"
        solver_before_restart = {"time": time.time(), "classification": solver_state, "process": observed_solver}
        write_json(output / "solver_after_gui_crash.json", solver_before_restart)
        status_after = json.loads((job_dir / "status.json").read_text())
        assert status_after == status_before, "崩溃后旧状态应原样保留，不能伪造 interrupted"
        write_json(output / "post_crash_status.json", status_after)
        write_json(output / "crash_events.json", events)

        second = launch("after_restart")
        assert second["pid"] != first["pid"]
        recovered = wait_json(output / "restarted_session.json", after_dir / "macro_failure.json")
        assert recovered["ok"] and recovered["gui_pid"] == second["pid"]
        assert recovered["job"]["status"] == "interrupted" and recovered["job"]["applicability"] == "current"
        cleanup_status = recovered["job"]["recovery_cleanup"]["status"]
        assert cleanup_status in ("terminated", "already_exited")
        assert recovered["model_unchanged"] and recovered["inputs_unchanged"] and "result" not in recovered["job"]
        assert JobLifecycleSession._ps(solver["pid"]) is None
        assert hashlib.sha256(project.read_bytes()).hexdigest() == ready["project_sha256"]
        assert {name: hashlib.sha256((job_dir / name).read_bytes()).hexdigest()
                for name in ready["input_sha256"]} == ready["input_sha256"]
        result = {
            "ok": True, "crashed_gui": first, "restarted_gui": second, "solver": solver,
            "events": events, "recovered": recovered, "solver_reaped": True,
            "solver_before_restart": solver_before_restart, "input_sha256": ready["input_sha256"],
            "scope": ("专用后台 GUI 的 SIGKILL 崩溃及新的 GUI/MCP 恢复；SIGSTOP 为测试注入，controller 正常路径不清理 solver。"
                      + ("产品按已保存身份终止了 ccx。" if cleanup_status == "terminated"
                         else "产品恢复时 ccx 已退出；本次未证明主动回收或具体退出原因，主动回收证据须另见无 GUI 的真实 owner + ccx 验证。")),
        }
    except BaseException:
        error = traceback.format_exc()
    finally:
        # open 返回异常或宏标记前失败，也能找回本轮独有命令对应的实例。
        for phase, command in launches:
            try:
                remember_launch(phase, command)
            except Exception:
                cleanup_errors.append(traceback.format_exc())
        if error is not None and solver is None and (output / "ready_for_crash.json").exists():
            try:
                pending = json.loads((output / "ready_for_crash.json").read_text())
                candidate = pending["solver_process"]
                assert candidate["ppid"] in {p["pid"] for p in guis}
                assert pending["job"]["input_stem"] == f"shaft-{pending['job']['job_id']}"
                assert candidate["command"] == f"{pending['job']['solver']} -i {pending['job']['input_stem']}"
                solver = candidate
            except Exception:
                cleanup_errors.append(traceback.format_exc())
        if error is not None and solver is not None:
            try:
                send(solver, signal.SIGCONT, events, allow_reparent=True)
                send(solver, signal.SIGKILL, events, allow_reparent=True)
                wait_gone(solver, allow_reparent=True)
            except Exception:
                cleanup_errors.append(traceback.format_exc())
        # 无人值守默认回收两次自建 GUI；显式 keep-open 也不保留失败实例。
        for identity in guis:
            try:
                stop_gui(identity, events, keep_open=keep_open and error is None and not cleanup_errors)
            except Exception:
                cleanup_errors.append(traceback.format_exc())
        if error is not None or cleanup_errors:
            write_json(output / "restart_failed.json", {"ok": False, "error": error,
                       "cleanup_errors": cleanup_errors, "events": events})
        else:
            result["gui_retained"] = keep_open
            write_json(output / "restart_acceptance.json", result)
    if error is not None or cleanup_errors:
        raise RuntimeError(f"重启验收失败，证据保存在 {output / 'restart_failed.json'}")
    print(json.dumps({"ok": True, "output": str(output), "restarted_gui_pid": result["restarted_gui"]["pid"],
                      "gui_retained": keep_open}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--keep-open", action="store_true", help="仅在成功后保留本轮第二个 GUI")
    args = parser.parse_args()
    run(args.out.resolve(), keep_open=args.keep_open)

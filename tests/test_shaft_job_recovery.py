"""孤儿求解器恢复：真实 Python owner + ccx，无 FreeCAD GUI。

唯一实际崩溃用例由测试在 Popen 返回时暂停自己的 ccx，再终止自己的 owner。
产品 JobManager 负责正常恢复清理；finally 只回收测试失败时的残留。
其余用例隔离身份边界，不冒充实际 CAD 验收。
"""

from copy import deepcopy
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from uuid import uuid4

import pytest

from gongke_core import shaft_jobs
from gongke_core.fem import ccx


ROOT = Path(__file__).resolve().parents[1]


def record_fixture():
    job_id = str(uuid4())
    stem = f"shaft-{job_id}"
    owner = {"pid": 200001, "ppid": 1, "state": "S", "started": "old-owner", "command": "python owner.py"}
    solver = {"pid": 200002, "ppid": owner["pid"], "state": "T", "started": "old-solver",
              "command": f"/example/ccx -i {stem}"}
    return {"job_id": job_id, "status": "running", "input_stem": stem, "pid": solver["pid"],
            "owner_process": owner, "solver_process": solver}


def save_record(root, record):
    directory = root / record["job_id"]
    directory.mkdir(parents=True)
    path = directory / "status.json"
    path.write_text(json.dumps(record))
    return path


@pytest.mark.skipif(sys.platform != "darwin", reason="实际 OS 身份自动清理目前限定 macOS")
def test_real_ccx_orphan_is_stopped_by_product_restart(tmp_path):
    try:
        executable = ccx.find()
    except ccx.CcxNotFound:
        pytest.skip("没有真实 ccx")
    owner_script = tmp_path / "owner.py"
    owner_script.write_text('''import json, os, signal, subprocess, sys, time
from pathlib import Path
from gongke_core import shaft_jobs

root = Path(sys.argv[1])
original_popen = subprocess.Popen
owned = []
def pause_own_solver(args, **kwargs):
    process = original_popen(args, **kwargs)
    if args[0] == os.environ["GONGKE_CCX"] and args[1:2] == ["-i"]:
        owned.append(process)
        process.send_signal(signal.SIGSTOP)
    return process
def stop_owner(signum, frame):
    raise SystemExit("test cleanup")
signal.signal(signal.SIGTERM, stop_owner)
subprocess.Popen = pause_own_solver
try:
    manager = shaft_jobs.JobManager(root / "runs")
    snapshot = json.loads(Path(sys.argv[2]).read_text())
    job_id = manager.start(snapshot, {"fixture": "real_ccx_owner_crash", "revision": 1})["job_id"]
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        record = manager.get(job_id)
        if record.get("solver_process"):
            temporary = root / "ready.tmp"
            temporary.write_text(json.dumps(record, indent=2))
            temporary.replace(root / "ready.json")
            while True:
                time.sleep(.1)
        if record["status"] in shaft_jobs.TERMINAL:
            raise RuntimeError(record)
        time.sleep(.01)
    raise TimeoutError("没有获得本轮真实 ccx 身份")
finally:
    for process in owned:
        shaft_jobs._stop(process)
''')
    solver = None
    owner = subprocess.Popen([sys.executable, str(owner_script), str(tmp_path), str(ROOT / "examples/native_shaft.json")],
                             cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                             env=dict(os.environ, GONGKE_CCX=str(executable), PYTHONPATH=str(ROOT)))
    try:
        deadline = time.monotonic() + 20
        ready = tmp_path / "ready.json"
        while not ready.exists():
            assert owner.poll() is None, owner.communicate()
            assert time.monotonic() < deadline, "owner 未提交真实求解器"
            time.sleep(.02)
        record = json.loads(ready.read_text())
        solver = record["solver_process"]
        actual = shaft_jobs._process_identity(solver["pid"])
        assert shaft_jobs._same_process(actual, solver) and "T" in actual["state"]
        assert solver["ppid"] == owner.pid == record["owner_process"]["pid"]
        assert solver["command"] == f"{executable} -i shaft-{record['job_id']}"
        status_path = Path(record["directory"]) / "status.json"
        original = status_path.read_bytes()
        # 活 owner 时不允许另一个管理器把真实任务标为 interrupted。
        with pytest.raises(RuntimeError, match="仍在运行"):
            shaft_jobs.JobManager(tmp_path / "runs")
        assert status_path.read_bytes() == original
        owner.kill()
        owner.wait(timeout=5)
        assert shaft_jobs._process_identity(owner.pid) is None
        assert shaft_jobs._same_process(shaft_jobs._process_identity(solver["pid"]), solver)
        manager = shaft_jobs.JobManager(tmp_path / "runs")
        recovered = manager.get(record["job_id"])
        assert recovered["status"] == "interrupted"
        assert recovered["recovery_cleanup"]["status"] == "terminated"
        assert recovered["recovery_cleanup"]["signals"] in (["SIGTERM"], ["SIGTERM", "SIGKILL"])
        assert shaft_jobs._wait_process_exit(solver, 2)
        assert recovered["source_context"] == record["source_context"]
        assert "result" not in recovered and not (status_path.parent / "result.json").exists()
        assert (status_path.parent / f"shaft-{record['job_id']}.inp").is_file()
        assert not (status_path.parent / "shaft.inp").exists()
        assert json.loads((status_path.parent / "snapshot.json").read_text()) == json.loads((ROOT / "examples/native_shaft.json").read_text())
        (tmp_path / "recovery_evidence.json").write_text(json.dumps({
            "ok": True, "scope": "Python owner + real ccx; no FreeCAD GUI",
            "injection": ["SIGSTOP own solver", "SIGKILL own owner"],
            "original": record, "recovered": recovered,
            "solver_after_recovery": shaft_jobs._process_identity(solver["pid"]),
        }, indent=2))
    finally:
        if owner.poll() is None:
            # ready 前失败时，先让 owner 用其实际 Popen 句柄回收暂停的子进程。
            owner.terminate()
            try:
                owner.wait(timeout=6)
            except subprocess.TimeoutExpired:
                owner.kill()
        owner.wait(timeout=5)
        if solver is None and (tmp_path / "ready.json").exists():
            solver = json.loads((tmp_path / "ready.json").read_text())["solver_process"]
        if solver is not None and shaft_jobs._same_process(shaft_jobs._process_identity(solver["pid"]), solver):
            os.kill(solver["pid"], signal.SIGKILL)
            assert shaft_jobs._wait_process_exit(solver, 2)
        owner.communicate(timeout=5)


@pytest.mark.parametrize("field", ["started", "command", "ppid", "input_stem", "missing_solver"])
def test_incomplete_or_different_identity_never_signals(tmp_path, monkeypatch, field):
    record = record_fixture()
    current = deepcopy(record["solver_process"])
    if field in ("started", "command"):
        current[field] += "-different"
    elif field == "ppid":
        record["solver_process"]["ppid"] += 1
    elif field == "input_stem":
        record["input_stem"] = "shaft"
    else:
        record.pop("solver_process")
    monkeypatch.setattr(shaft_jobs, "_process_identity", lambda pid: current if pid == current["pid"] else None)
    signals = []
    monkeypatch.setattr(os, "kill", lambda *args: signals.append(args))
    save_record(tmp_path, record)
    recovered = shaft_jobs.JobManager(tmp_path).get(record["job_id"])
    assert recovered["status"] == "interrupted" and recovered["recovery_cleanup"]["status"] == "unverified"
    assert recovered["recovery_cleanup"]["reason"] and not signals


def test_live_owner_preflight_does_not_partially_change_other_records(tmp_path, monkeypatch):
    older, active = record_fixture(), record_fixture()
    older.pop("owner_process")
    paths = [save_record(tmp_path, r) for r in (older, active)]
    before = [p.read_bytes() for p in paths]
    monkeypatch.setattr(shaft_jobs, "_process_identity", lambda pid: active["owner_process"])
    with pytest.raises(RuntimeError, match="仍在运行"):
        shaft_jobs.JobManager(tmp_path)
    assert [p.read_bytes() for p in paths] == before


def test_os_query_failure_is_not_owner_exit(tmp_path, monkeypatch):
    record = record_fixture()
    save_record(tmp_path, record)
    def unavailable(pid):
        raise RuntimeError("ps unavailable")
    monkeypatch.setattr(shaft_jobs, "_process_identity", unavailable)
    signals = []
    monkeypatch.setattr(os, "kill", lambda *args: signals.append(args))
    recovered = shaft_jobs.JobManager(tmp_path).get(record["job_id"])
    assert recovered["recovery_cleanup"] == {"status": "unverified", "signals": [], "reason": "ps unavailable"}
    assert not signals


def test_each_signal_rechecks_identity(monkeypatch):
    record = record_fixture()
    old = record["solver_process"]
    replaced = dict(old, started="new process")
    identities = iter([old, replaced])
    monkeypatch.setattr(shaft_jobs, "_process_identity", lambda pid: next(identities))
    monkeypatch.setattr(shaft_jobs, "_wait_process_exit", lambda *args: False)
    signals = []
    monkeypatch.setattr(os, "kill", lambda pid, sig: signals.append(sig))
    result = shaft_jobs._recover_solver(record, True, None)
    assert result["status"] == "unverified" and signals == [signal.SIGTERM]


def test_signal_permission_failure_never_claims_cleanup(monkeypatch):
    record = record_fixture()
    monkeypatch.setattr(shaft_jobs, "_process_identity", lambda pid: record["solver_process"])
    def denied(pid, sig):
        raise PermissionError("permission denied")
    monkeypatch.setattr(os, "kill", denied)
    result = shaft_jobs._recover_solver(record, True, None)
    assert result["status"] == "unverified" and result["signals"] == []
    assert "permission denied" in result["reason"]


def test_unsupported_platform_does_not_run_ps(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("unsupported platform must not inspect/kill"))
    with pytest.raises(RuntimeError, match="当前平台"):
        shaft_jobs._process_identity(os.getpid())

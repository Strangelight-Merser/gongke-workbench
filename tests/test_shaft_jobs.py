"""任务管理及实际梁求解测试。

临时子进程只验证失败、超时和取消；FEM 成功由可选的真实 ccx 检查。
课程快照的 CAD 状态在测试中显式声明，只验证核心求解链路，不构成原生 CAD 验收。
"""

import json
import os
from pathlib import Path
import sys
import time
from uuid import uuid4

import pytest

from gongke_core import api, shaft_jobs
from gongke_core.calc import shaft_stiffness
from gongke_core.course_shaft import from_design
from gongke_core.fem import ccx, shaft_beam


@pytest.fixture
def snapshot():
    return json.loads((Path(__file__).parents[1] / "examples/native_shaft.json").read_text())


def wait_for(manager, job_id, condition, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        record = manager.get(job_id)
        if condition(record):
            return record
        time.sleep(0.01)
    pytest.fail(f"任务未达到预期状态：{manager.get(job_id)}")


def executable(tmp_path, monkeypatch, code):
    path = tmp_path / "solver-test-process"
    path.write_text(f"#!{sys.executable}\n{code}\n")
    path.chmod(0o755)
    monkeypatch.setattr(ccx, "find", lambda: path)
    monkeypatch.setattr(ccx, "check_version", lambda path: None)
    return path


def test_missing_solver_is_failed_and_input_is_immutable(tmp_path, monkeypatch, snapshot):
    def missing():
        raise ccx.CcxNotFound("测试环境无 ccx")
    monkeypatch.setattr(ccx, "find", missing)
    manager = shaft_jobs.JobManager(tmp_path)
    context = {"session_id": "session-a", "revision": 7, "content_hash": "original"}
    job = manager.start(snapshot, context)
    snapshot["segments"][1]["diameter_m"] = 0.05
    context["revision"] = 8
    record = wait_for(manager, job["job_id"], lambda r: r["status"] == "failed")
    directory = Path(record["directory"])
    assert json.loads((directory / "snapshot.json").read_text())["segments"][1]["diameter_m"] == 0.04
    assert record["source_context"]["revision"] == 7
    assert "无 ccx" in record["error"]
    assert (directory / "stdout.log").exists()
    assert "result" not in record


def test_process_failure_is_not_success(tmp_path, monkeypatch, snapshot):
    executable(tmp_path, monkeypatch, "import sys\nprint('unit-test failure', flush=True)\nsys.exit(3)")
    manager = shaft_jobs.JobManager(tmp_path / "jobs")
    job = manager.start(snapshot, {})
    record = wait_for(manager, job["job_id"], lambda r: r["status"] in shaft_jobs.TERMINAL)
    assert record["status"] == "failed"
    assert "返回码 3" in record["error"]
    assert "unit-test failure" in record["error"]


def test_cancel_stops_real_process(tmp_path, monkeypatch, snapshot):
    executable(tmp_path, monkeypatch, "import time\ntime.sleep(30)")
    manager = shaft_jobs.JobManager(tmp_path / "jobs")
    job = manager.start(snapshot, {"revision": 4})
    running = wait_for(manager, job["job_id"], lambda r: "pid" in r)
    cancelled = manager.cancel(job["job_id"])
    assert cancelled["status"] == "cancelled"
    with pytest.raises(ProcessLookupError):
        os.kill(running["pid"], 0)
    assert manager.cancel(job["job_id"])["status"] == "cancelled"
    assert "result" not in cancelled


def test_timeout_terminates_real_process(tmp_path, monkeypatch, snapshot):
    executable(tmp_path, monkeypatch, "import time\ntime.sleep(30)")
    monkeypatch.setattr(shaft_jobs, "TIMEOUT_SECONDS", 0.05)
    manager = shaft_jobs.JobManager(tmp_path / "jobs")
    job = manager.start(snapshot, {})
    record = wait_for(manager, job["job_id"], lambda r: r["status"] == "failed")
    assert "超过" in record["error"]
    with pytest.raises(ProcessLookupError):
        os.kill(record["pid"], 0)


def test_restart_marks_running_interrupted(tmp_path):
    job_id = str(uuid4())
    directory = tmp_path / job_id
    directory.mkdir()
    (directory / "status.json").write_text(json.dumps({"job_id": job_id, "status": "running"}))
    manager = shaft_jobs.JobManager(tmp_path)
    assert manager.get(job_id)["status"] == "interrupted"
    assert json.loads((directory / "status.json").read_text())["status"] == "interrupted"


def test_invalid_input_never_starts_job(tmp_path, snapshot):
    del snapshot["loads"]
    manager = shaft_jobs.JobManager(tmp_path)
    with pytest.raises(ValueError, match="loads"):
        manager.start(snapshot, {})
    assert not list(tmp_path.iterdir())
    with pytest.raises(ValueError, match="不存在"):
        manager.get("../../other")


@pytest.fixture
def course_snapshot():
    snapshot = from_design(api._run(api.example_task("coupling")))
    # 本测试没有读取 CAD。状态仅用于隔离测试当前轴到梁求解器的契约。
    snapshot["cad_geometry_state"] = {"parameters_current": True, "load_binding_current": True,
                                      "keyways_current": True, "fillets_current": False,
                                      "unsupported_features": []}
    return snapshot


@pytest.mark.parametrize("flag", ["load_binding_current", "parameters_current"])
def test_course_stale_binding_is_rejected_before_start(tmp_path, course_snapshot, flag):
    course_snapshot["cad_geometry_state"][flag] = False
    manager = shaft_jobs.JobManager(tmp_path)
    with pytest.raises(ValueError, match="未绑定"):
        manager.start(course_snapshot, {"evidence_scope": "unit_test_declared_geometry"})
    assert not list(tmp_path.iterdir())


def test_course_deck_keeps_axial_load_offset_couple_and_fixed_dimensions(tmp_path, course_snapshot, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("固定轴快照不应调用设计选型")
    monkeypatch.setattr(api.design_mod, "run", forbidden)
    segments, case, _ = shaft_jobs._beam_inputs(course_snapshot)
    assert [s.d for s in segments] == [s["diameter_m"] for s in course_snapshot["segments"]]
    inp = tmp_path / "course.inp"
    shaft_beam.write_inp(inp, segments, case, E=course_snapshot["material"]["young_modulus_pa"])
    text = inp.read_text()
    lines = text.split("*CLOAD\n", 1)[1].split("*NODE PRINT", 1)[0].strip().splitlines()
    values = {int(parts[1]): (int(parts[0]), float(parts[2])) for parts in (line.split(",") for line in lines)}
    p = course_snapshot["loads"][0]
    assert values[1][1] == pytest.approx(p["fx_n"], rel=1e-6)
    assert values[2][1] == pytest.approx(p["fy_n"], rel=1e-6)
    assert values[3][1] == pytest.approx(p["fz_n"], rel=1e-6)
    assert values[5][1] == pytest.approx(-p["x0_m"] * p["fz_n"] / shaft_beam.MM, rel=1e-6)
    assert 6 not in values  # 这一模型明确不施加扭矩，不提供扭转结论。
    nodes = text.split("*NODE, NSET=NALL\n", 1)[1].split("*USER ELEMENT", 1)[0].strip().splitlines()
    positions = {int(parts[0]): float(parts[3]) for parts in (line.split(",") for line in nodes)}
    assert positions[values[3][0]] == pytest.approx(p["z_m"] / shaft_beam.MM)
    assert positions[1] == pytest.approx(course_snapshot["z_origin_m"] / shaft_beam.MM)


@pytest.mark.parametrize("index,unit", [(0, "mm"), (1, "deg")])
def test_course_stiffness_units_must_match_si_kind(tmp_path, course_snapshot, index, unit):
    course_snapshot["stiffness_limits"][index]["unit"] = unit
    with pytest.raises(ValueError):
        shaft_jobs.JobManager(tmp_path).start(course_snapshot, {})


@pytest.mark.parametrize("field", ["limit", "young_modulus_pa"])
def test_course_boolean_is_not_an_engineering_number(tmp_path, course_snapshot, field):
    if field == "limit":
        course_snapshot["stiffness_limits"][0][field] = True
    else:
        course_snapshot["material"][field] = True
    with pytest.raises(ValueError):
        shaft_jobs.JobManager(tmp_path).start(course_snapshot, {})


def test_course_real_ccx_matches_timoshenko_at_declared_control_points(tmp_path, course_snapshot, monkeypatch):
    try:
        executable_path = ccx.find()
        ccx.check_version(executable_path)
    except ccx.CcxNotFound as exc:
        pytest.skip(str(exc))
    segments, case, _ = shaft_jobs._beam_inputs(course_snapshot)
    def forbidden(*args, **kwargs):
        raise AssertionError("求解过程中不得重新设计或选径")
    monkeypatch.setattr(api.design_mod, "run", forbidden)
    manager = shaft_jobs.JobManager(tmp_path)
    job = manager.start(course_snapshot, {"evidence_scope": "core_solver_declared_geometry", "revision": 1})
    record = wait_for(manager, job["job_id"], lambda r: r["status"] in shaft_jobs.TERMINAL, timeout=60)
    assert record["status"] == "succeeded", record.get("error")
    assert record["solver"] == str(executable_path)
    result = record["result"]
    assert result["engineering_conclusion"] == "not_established"
    assert result["source_scope"] == "course_shaft_review"
    assert result["normalized_max_difference"] < 0.01
    analytic = shaft_stiffness.solve(segments, case, E=course_snapshot["material"]["young_modulus_pa"], shear=True, nu=shaft_jobs.POISSON_RATIO)
    assert len(result["checks"]) == len(course_snapshot["stiffness_limits"])
    for actual, declared in zip(result["checks"], course_snapshot["stiffness_limits"]):
        assert actual["z_m"] == declared["z_m"]
        assert actual["limit"] == declared["limit"]
        assert actual["source"] == declared["source"]
        assert actual["unit"] == ("m" if actual["kind"] == "y" else "rad")
        expected = analytic.deflection(actual["z_m"]) if actual["kind"] == "y" else analytic.slope(actual["z_m"])
        assert actual["value"] == pytest.approx(expected, rel=0.01, abs=1e-10)
    assert json.loads((Path(record["directory"]) / "snapshot.json").read_text()) == course_snapshot

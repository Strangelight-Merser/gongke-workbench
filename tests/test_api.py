"""面向 agent 的接口（gongke_core.api）：输入输出都是普通 dict，与命令行、工作台结果一致。"""

import json

import pytest

from gongke_core import api


@pytest.mark.parametrize("scheme", list(api.SCHEMES))
def test_examples_are_valid_and_design(scheme):
    task = api.example_task(scheme)
    assert api.validate(task) == []
    s = api.design(task)
    assert s["ok"] and s["failed"] == [] and s["scheme"] == scheme
    json.dumps(s, ensure_ascii=False)  # 可序列化


def test_validate_reports_each_problem():
    errs = api.validate({"conveyor": {"belt_pull_N": -1}, "scheme": "x", "gears": {"high": {"z1": 10, "foo": 1}}})
    text = "\n".join(errs)
    for frag in ("belt_speed_m_s：必填", "belt_pull_N：应大于 0", "z1：10 小于下限 17", "foo：未知字段", "'x' 不是可选值"):
        assert frag in text
    assert api.validate({"conveyor": {"belt_pull_N": 1, "belt_speed_m_s": 1, "drum_diameter_mm": 300},
                         "scheme": "worm", "gears": {"high": {}}})
    with pytest.raises(api.TaskError):
        api.design({"conveyor": {}})


def test_minimal_task_uses_defaults():
    s = api.design({"conveyor": {"belt_pull_N": 3000, "belt_speed_m_s": 1.2, "drum_diameter_mm": 350}})
    assert s["scheme"] == "coupling" and set(s["gears"]) == {"high", "low"}


def test_explore_changes_one_parameter():
    task = api.example_task()
    r = api.explore(task, "motor_sync_speed_rpm", [1000, 1500, 7])
    rows = r["results"]
    assert rows[0]["motor"].startswith("Y") and rows[0]["motor"] != rows[1]["motor"]
    assert rows[0]["total_ratio"] < rows[1]["total_ratio"]  # 转速低，总传动比小
    assert "error" in rows[2]  # 不可选的值单独报错，不影响其他方案
    assert task["motor_sync_speed_rpm"] == 1500  # 不修改传入的任务书


def test_report_chapter():
    r = api.report(api.example_task(), "轴承")
    assert any("轴承" in c for c in r["chapters"]) and r["markdown"].startswith("## ")
    assert "L10h" in r["markdown"]
    with pytest.raises(api.TaskError):
        api.report(api.example_task(), "不存在的章")


def test_lookup():
    assert api.lookup("bearing", bore_mm=40)["bearings"][0]["designation"] == "6208"
    assert api.lookup("bearing", bore_mm=40, type="tapered")["bearings"][0]["designation"].startswith("3")
    assert api.lookup("key", shaft_d_mm=45)["b_mm"] == 14.0  # GB/T 1095：d > 44～50 时 b = 14
    assert api.lookup("motor", power_kw=4.0, sync_rpm=1500)["model"] == "Y112M-4"
    assert 2 in api.lookup("modules")["modules_mm"]
    assert {m["key"] for m in api.lookup("gear_materials")["materials"]} == set(api.GEAR_MATERIALS)
    with pytest.raises(api.TaskError):
        api.lookup("nothing")


def test_generate_files(tmp_path):
    r = api.generate(api.example_task("worm"), tmp_path, report_docx=False, drawings=True)
    assert r["ok"] and "report.md" in r["files"] and "drawings/drawings.pdf" in r["files"]
    assert {d["number"] for d in r["drawings"]} >= {"GK-00", "GK-04-01"}
    assert json.loads((tmp_path / "task.json").read_text(encoding="utf-8"))["scheme"] == "worm"

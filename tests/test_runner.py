"""FreeCAD 工作台的进程调用部分（不需要 FreeCAD）。"""

import json
import subprocess
import sys

from freecad.gongke import runner


def test_task_dict_roundtrip(tmp_path):
    from gongke_core.design import ReducerTask

    v = runner.FormValues(belt_pull_N=3000, belt_speed_m_s=1.2, drum_diameter_mm=350, shifts=1)
    path = runner.write_task(v, tmp_path)
    t = ReducerTask.from_yaml(path)  # JSON 是 YAML 的子集
    assert t.conveyor.belt_pull == 3000
    assert abs(t.conveyor.drum_diameter - 0.35) < 1e-12
    assert t.conveyor.life_hours == 10 * 300 * 8


def test_cli_without_geometry(tmp_path):
    path = runner.write_task(runner.FormValues(), tmp_path)
    prog, args, cwd = runner.command(sys.executable, path, tmp_path, step=False)
    p = subprocess.run([prog] + args, cwd=cwd, env=runner.environment(), capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    out = runner.read_outputs(tmp_path)
    assert out["summary"]["ok"]
    assert "report.md" in out["files"]
    json.dumps(out["summary"])


def test_cli_drawings_index(tmp_path):
    path = runner.write_task(runner.FormValues(), tmp_path)
    prog, args, cwd = runner.command(sys.executable, path, tmp_path, step=False, drawings=True)
    p = subprocess.run([prog] + args, cwd=cwd, env=runner.environment(), capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    out = runner.read_outputs(tmp_path)
    assert out["drawings"][0]["number"] == "GK-00"
    assert all(d["dxf"].exists() for d in out["drawings"])

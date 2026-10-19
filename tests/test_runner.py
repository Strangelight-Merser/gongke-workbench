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


def test_cli_bevel_scheme(tmp_path):
    # 圆锥-圆柱方案：三维模型、锥齿轮零件图和装配图都生成，面板能显示锥齿轮参数
    path = runner.write_task(runner.FormValues(scheme="bevel", belt_pull_N=2200, belt_speed_m_s=1.5,
                                               drum_diameter_mm=300), tmp_path)
    prog, args, cwd = runner.command(sys.executable, path, tmp_path, step=True, drawings=True)
    p = subprocess.run([prog] + args, cwd=cwd, env=runner.environment(), capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    out = runner.read_outputs(tmp_path)
    assert "reducer_assembly.step" in out["files"]
    numbers = {d["number"]: d["name"] for d in out["drawings"]}
    assert "GK-00" in numbers and any("锥齿轮" in n for n in numbers.values())
    g = out["summary"]["gears"]
    assert runner.gear_line(g["high"]).startswith("直齿锥齿轮")
    assert runner.gear_line(g["low"]).startswith("mn=")
    assert "直齿锥齿轮传动设计" in (tmp_path / "report.md").read_text(encoding="utf-8")


def test_cli_worm_scheme(tmp_path):
    # 蜗杆方案：说明书有蜗杆传动、热平衡章节；面板显示蜗杆参数
    path = runner.write_task(runner.FormValues(scheme="worm", belt_pull_N=2300, belt_speed_m_s=0.9,
                                               drum_diameter_mm=320), tmp_path)
    prog, args, cwd = runner.command(sys.executable, path, tmp_path, step=False, drawings=False)
    p = subprocess.run([prog] + args, cwd=cwd, env=runner.environment(), capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    out = runner.read_outputs(tmp_path)
    assert runner.gears_html(out["summary"]["gears"]).startswith("<b>蜗杆传动</b> m=")
    text = (tmp_path / "report.md").read_text(encoding="utf-8")
    assert "蜗杆传动设计" in text and "热平衡计算" in text and "蜗杆刚度校核" in text

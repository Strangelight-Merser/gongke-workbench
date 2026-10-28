"""真实故障回归：重复目录、导出失败、CLI 校验与最终传动关系。"""
import json
import math
import subprocess
import sys

import pytest

from gongke_core import api, design
from gongke_core.task_input import TaskError


def test_failed_step_is_not_complete_and_partial_file_is_not_delivered(tmp_path, monkeypatch):
    from gongke_core.geometry import assembly

    def fail(res, path, **kwargs):
        path.write_text('incomplete STEP')
        raise RuntimeError('模拟 STEP 写入中断')

    monkeypatch.setattr(assembly, 'export', fail)
    r = api.generate(api.example_task(), tmp_path, drawings=False, report_docx=False, step=True)
    assert r['calculation_ok'] and not r['ok'] and not r['exports_complete']
    assert r['artifacts']['step']['status'] == 'failed'
    assert 'reducer_assembly.step' not in r['files']
    assert 'report.md' in r['files']
    assert json.loads((tmp_path / 'manifest.json').read_text()) == r


def test_reuse_rejected_without_touching_old_files(tmp_path):
    old = tmp_path / 'reducer_assembly.step'
    old.write_text('previous run')
    with pytest.raises(TaskError, match='输出目录非空'):
        api.generate(api.example_task(), tmp_path, step=False)
    assert old.read_text() == 'previous run'
    assert not (tmp_path / 'manifest.json').exists()


def test_separate_runs_have_separate_ids(tmp_path):
    task = api.example_task()
    first = api.generate(task, tmp_path / 'first', drawings=False, report_docx=False)
    task['conveyor']['belt_pull_N'] += 100
    second = api.generate(task, tmp_path / 'second', drawings=False, report_docx=False)
    assert first['ok'] and second['ok']
    assert first['run_id'] != second['run_id']
    assert (tmp_path / 'first/task.json').read_text() != (tmp_path / 'second/task.json').read_text()


@pytest.mark.parametrize('change', [
    {'gears': {'high': {'beta_deg': 0}}},
    {'life': {'years': 0}},
    {'gears': {'high': {'s_h': -1}}},
    {'gears': 1},
    {'gears': {'high': None}},
    {'conveyor': {'belt_pull_N': float('nan'), 'belt_speed_m_s': 1, 'drum_diameter_mm': 400}},
])
def test_all_task_parsers_reject_invalid_values(change, tmp_path):
    task = api.example_task()
    task.update(change)
    assert api.validate(task)
    with pytest.raises(TaskError):
        design.ReducerTask.from_dict(task)
    source = tmp_path / 'task.json'
    source.write_text(json.dumps(task))
    r = subprocess.run([sys.executable, '-m', 'gongke_core', 'design', str(source),
                        '-o', str(tmp_path / 'out'), '--no-step'], capture_output=True, text=True)
    assert r.returncode == 2 and 'task.' in r.stderr
    assert not (tmp_path / 'out').exists()


@pytest.mark.parametrize('scheme', ['coupling', 'vbelt', 'single', 'bevel', 'worm'])
def test_actual_shaft_speed_and_torque_follow_selected_teeth(scheme):
    # 独立关系：n后=n前*z主动/z从动，T=P/ω；不得用初选比分配冒充最终结果。
    res = design.run(design.ReducerTask.from_dict(api.example_task(scheme)))
    pairs = [res.high] + ([res.low] if getattr(res, 'low', None) is not None else [])
    n = res.kin.motor.speed_rpm / res.kin.i_belt
    for idx, pair in enumerate(pairs, start=1):
        assert pair.inp.speed1_rpm == pytest.approx(n)
        assert pair.inp.torque1 == pytest.approx(res.kin.shafts[idx].torque)
        n *= pair.z1 / pair.z2
        state = res.kin.shafts[idx + 1]
        assert state.speed_rpm == pytest.approx(n)
        assert state.torque == pytest.approx(state.power / (2 * math.pi * n / 60))
    assert res.kin.shafts[-1].speed_rpm == pytest.approx(n)


def test_empty_drawing_folder_cannot_pass(tmp_path):
    with pytest.raises(TaskError, match='未找到'):
        api.check_drawings(tmp_path)


def test_workbench_preserves_previous_run_on_repeat(tmp_path):
    from freecad.gongke import runner
    out = tmp_path / 'project'
    source = runner.write_task(runner.FormValues(), out)
    from gongke_core.delivery import generate
    first = generate(json.loads(source.read_text()), out, drawings=False, report_docx=False, source_task=source)
    source = runner.write_task(runner.FormValues(belt_pull_N=3000), out)
    archives = list(tmp_path.glob('project-*'))
    assert len(archives) == 1
    assert json.loads((archives[0] / 'manifest.json').read_text())['run_id'] == first['run_id']
    assert not (out / 'report.md').exists()
    second = generate(json.loads(source.read_text()), out, drawings=False, report_docx=False, source_task=source)
    assert runner.read_outputs(out)['delivery']['run_id'] == second['run_id']


def test_final_gear_life_uses_actual_teeth_ratio():
    res = design.run(design.ReducerTask.from_dict(api.example_task()))
    for pair in res.stages:
        assert pair.cycles[0] == pytest.approx(60 * pair.inp.speed1_rpm * pair.inp.life_hours)
        assert pair.cycles[1] == pytest.approx(pair.cycles[0] * pair.z1 / pair.z2)


def test_oversize_drawings_report_component_and_keep_calculation(tmp_path):
    task = api.example_task('single')
    task['conveyor'].update(belt_pull_N=4000, belt_speed_m_s=1.0, drum_diameter_mm=400)
    task['motor_sync_speed_rpm'] = 1500
    r = api.generate(task, tmp_path, report_docx=False)
    assert r['calculation_ok'] and not r['exports_complete'] and not r['ok']
    assert '大齿轮齿顶圆 h11' in r['artifacts']['drawings']['error']
    assert not (tmp_path / 'drawings').exists()


def test_assembly_balloons_stay_clear_of_continued_parts_list(tmp_path):
    from gongke_core import drawing
    from gongke_core.drawing import lint
    task = api.example_task()
    task['conveyor'].update(belt_pull_N=6000, belt_speed_m_s=1.0, drum_diameter_mm=500)
    res = design.run(design.ReducerTask.from_dict(task))
    files = drawing.build_all(res, tmp_path, svg=False, pdf=False)
    assert not [(f.dxf.name, i.as_dict()) for f in files for i in lint.check(f.dxf).issues]

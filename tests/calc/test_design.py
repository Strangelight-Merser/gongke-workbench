"""减速器设计全流程（纯 Python）：用示例任务书跑通，并检查力学自洽性。"""

from pathlib import Path

import pytest

from gongke_core import design

EXAMPLE = Path(__file__).resolve().parents[2] / "examples" / "conveyor_basic.yaml"


@pytest.fixture(scope="module")
def result():
    return design.run(design.ReducerTask.from_yaml(EXAMPLE))


def test_all_checks_pass(result):
    failed = [c for c in result.checks if not c[1]]
    assert not failed, failed


def test_force_equilibrium_on_every_shaft(result):
    for s in result.shafts:
        r = s.strength.reactions
        fx = sum(p.fx for p in s.load_case.loads) + r.ax + r.bx
        fy = sum(p.fy for p in s.load_case.loads) + r.ay + r.by
        assert abs(fx) < 1e-6 and abs(fy) < 1e-6


def test_torque_balanced(result):
    for s in result.shafts:
        assert sum(t for _, t in s.load_case.torque_points) == pytest.approx(0)


def test_intermediate_shaft_axial_forces_partly_cancel(result):
    loads = result.shafts[1].load_case.loads
    assert loads[0].fz * loads[1].fz < 0


def test_segments_contiguous_and_bearings_seated(result):
    for s in result.shafts:
        segs = s.layout.segments
        for a, b in zip(segs, segs[1:]):
            assert b.z0 == pytest.approx(a.z1)
        for zc in s.layout.bearing_z:
            seat = next(x for x in segs if x.z0 - 1e-9 <= zc <= x.z1 + 1e-9)
            assert seat.role == "轴承" and seat.d == pytest.approx(s.layout.bearing.d)


def test_gears_lie_inside_housing(result):
    w = result.housing.inner_width
    for s in result.shafts:
        for g in s.layout.gears:
            assert g.z - g.width / 2 >= result.housing.gap_axial - 1e-9
            assert g.z + g.width / 2 <= w - result.housing.gap_axial + 1e-9


def test_task_dict_units():
    t = design.ReducerTask.from_dict({"conveyor": {"belt_pull_N": 3000, "belt_speed_m_s": 1.2, "drum_diameter_mm": 350}})
    assert t.conveyor.drum_diameter == pytest.approx(0.35)
    assert t.conveyor.life_hours == pytest.approx(10 * 300 * 16)


@pytest.mark.parametrize("pull,speed,drum", [(1800, 1.1, 300), (3500, 1.6, 450), (4500, 1.0, 400), (2200, 0.9, 320)])
def test_other_tasks_converge(pull, speed, drum):
    r = design.run(design.ReducerTask.from_dict(
        {"conveyor": {"belt_pull_N": pull, "belt_speed_m_s": speed, "drum_diameter_mm": drum}}))
    failed = [c for c in r.checks if not c[1]]
    assert not failed, failed


VBELT = Path(__file__).resolve().parents[2] / "examples" / "conveyor_vbelt.yaml"


def test_vbelt_scheme():
    d = design.run(design.ReducerTask.from_yaml(VBELT))
    assert d.ok, [c for c in d.checks if not c[1]]
    assert d.belt is not None and len(d.couplings) == 1
    assert d.actual_ratio == pytest.approx(d.belt.ratio * d.high.u * d.low.u)
    s1 = d.shafts[0]
    fp = next(p for p in s1.load_case.loads if p.label == "带轮压轴力")
    assert fp.fx == pytest.approx(-d.belt.fp)
    # 带轮轮毂不短于轮缘宽度，压轴力作用在轴伸中点
    assert s1.layout.coupling_hub >= d.belt.width - 1e-9
    end = s1.layout.segment("端部")
    assert fp.z == pytest.approx(end.z0 + end.length / 2)

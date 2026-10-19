"""V 带轮结构：轮槽位置和尺寸（GB/T 10412 的 e、f、bd、φ）以及结构型式的选择规则（濮良贵《机械设计》§8-3）。"""

import math

import pytest

from gongke_core.calc import vbelt
from gongke_core.layout import pulley

MM = 1e-3


def _area_centroid(pts):
    a = cx = 0.0
    for (r0, z0), (r1, z1) in zip(pts, pts[1:] + pts[:1]):
        c = r0 * z1 - r1 * z0
        a += c
        cx += (r0 + r1) * c
    return a / 2, cx / (3 * a)  # 形心 = Σ(r0 + r1)c / (6A)，A = a/2


def test_groove_geometry():
    sec = vbelt.section("A")
    p = pulley.blank(sec, 280 * MM, 4, 24 * MM, 63 * MM)
    zs = p.groove_centers()
    assert len(zs) == 4
    assert zs[1] - zs[0] == pytest.approx(sec.e)
    assert zs[0] - (p.z_center - p.width / 2) == pytest.approx(sec.f)
    assert p.angle == 38  # dd = 280 > 118 mm
    assert p.groove_half_width(p.dd / 2) == pytest.approx(sec.bp / 2)
    assert p.da == pytest.approx(p.dd + 2 * sec.ha)


def test_kind_rules():
    a = vbelt.section("A")
    assert pulley.blank(a, 100 * MM, 3, 38 * MM, 60 * MM).kind == "实心式"
    assert pulley.blank(a, 180 * MM, 3, 30 * MM, 50 * MM).kind == "腹板式"
    big = pulley.blank(a, 280 * MM, 4, 24 * MM, 63 * MM)
    assert big.kind == "孔板式" and big.holes > 0
    assert big.hole_d == pytest.approx(math.floor(0.25 * (big.rim_inner_d - big.hub_d) / MM) * MM)


def test_profile_closed_and_volume_reasonable():
    # 帕普斯定理：回转体体积 = 截面积 × 2π × 形心半径，应介于轮毂实心柱体和整个外圆柱体之间
    p = pulley.blank(vbelt.section("B"), 315 * MM, 3, 30 * MM, 60 * MM)
    pts = p.profile()
    area, rc = _area_centroid(pts)
    assert area > 0
    vol = area * 2 * math.pi * rc
    assert vol < math.pi * (p.da / 2) ** 2 * p.hub_length
    assert vol > math.pi * ((p.hub_d / 2) ** 2 - (p.bore / 2) ** 2) * p.hub_length

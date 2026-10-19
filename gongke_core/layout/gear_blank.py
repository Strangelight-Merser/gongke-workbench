"""齿轮结构尺寸（实心式 / 腹板式），三维建模和二维出图共用。

经验公式按课程设计指导书："齿顶圆直径 da ≤ 160 mm 做成实心式，160–500 mm 做成腹板式"；
腹板式：轮毂外径 D1 = 1.6d，轮缘厚度 δ0 = (2.5–4)mn ≥ 10 mm，腹板厚度 C = 0.3b ≥ 10 mm，
减重孔直径 d0 = 0.25(D2 − D1)，孔中心圆 D0 = 0.5(D1 + D2)。单位 m。
"""

from __future__ import annotations

from dataclasses import dataclass

from gongke_core import standards
from gongke_core.calc.gear import GearPair

MM = 1e-3


@dataclass
class GearBlank:
    z: int
    da: float
    d: float
    df: float
    b: float
    bore: float | None  # None 表示齿轮轴
    key_b: float | None
    key_t2: float | None
    web: bool
    hub_d: float = 0.0  # D1
    rim_inner_d: float = 0.0  # D2
    web_thickness: float = 0.0  # C
    hole_d: float = 0.0  # d0
    hole_pcd: float = 0.0  # D0
    holes: int = 0
    hand: str = "右旋"


def blank(pair: GearPair, member: int, bore: float | None) -> GearBlank:
    z = pair.z1 if member == 1 else pair.z2
    da = pair.da1 if member == 1 else pair.da2
    d = pair.d1 if member == 1 else pair.d2
    df = pair.df1 if member == 1 else pair.df2
    b = pair.b1 if member == 1 else pair.b2
    hand = "右旋" if member == 1 else "左旋"
    if bore is None:
        return GearBlank(z, da, d, df, b, None, None, None, False, hand=hand)
    ks = standards.key_size(bore)
    g = GearBlank(z, da, d, df, b, bore, ks.b, ks.t2, False, hand=hand)
    rim = max(3 * pair.mn, 10 * MM)
    d2 = df - 2 * rim
    d1 = 1.6 * bore
    c = max(0.3 * b, 10 * MM)
    if da > 160 * MM and d2 > d1 + 10 * MM and (b - c) / 2 > 1 * MM:
        g.web = True
        g.hub_d, g.rim_inner_d, g.web_thickness = d1, d2, c
        g.hole_d = 0.25 * (d2 - d1)
        g.hole_pcd = 0.5 * (d1 + d2)
        g.holes = 6
    return g

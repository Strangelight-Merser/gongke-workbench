"""单级蜗杆减速器（蜗杆下置）的结构布置。

坐标与展开式减速器一致：y 向上，剖分面 y = 0 通过蜗轮轴线；Ⅱ轴（蜗轮轴）轴线沿 z、在 x = 0，
箱体内壁在 z = 0 和 z = W，蜗轮中间平面在 z = W/2，输出端从 z = W 一侧伸出。
Ⅰ轴（蜗杆轴）在剖分面下方 y = −a 处，轴线沿 x、在 z = W/2，两端轴承装在箱座左右端壁的轴承座孔中，
输入端从 −x 一侧伸出。蜗杆轴的结构用沿轴线的坐标（= 总体 x）描述，蜗杆螺纹中点在 x = 0。

蜗杆下置时蜗杆浸在油中，油面到蜗杆中心线附近；蜗杆轴承靠近油池，内侧装挡油盘。
蜗杆轴两端用圆锥滚子轴承正装（两端单向固定），便于调整轴向游隙。为缩短跨距、保证蜗杆刚度，
蜗杆轴承座从端壁向箱内伸出（内凸台），伸到不碰蜗轮（离蜗轮外圆不小于 Δ1）、不碰蜗杆螺纹为止。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from gongke_core import standards
from gongke_core.calc import shaft as shaft_calc
from gongke_core.calc.worm import WormPair
from gongke_core.layout.reducer import (SPANNER_CLEARANCE_MM, Housing, bolt, ceil_to)

MM = 1e-3
OIL_BELOW_WORM = 40 * MM  # 蜗杆齿顶到箱底的距离（油池深度），指导书推荐 30～50 mm


def boss_radius(D: float) -> float:
    return D / 2 + max(0.25 * D, 12 * MM)


def wheel_hub(worm: WormPair, seat_d: float) -> float:
    """蜗轮轮毂长度 L = (1.2～1.8)d，且不小于齿宽 b2。"""
    return ceil_to(max(1.2 * seat_d, worm.b2), MM)


def housing(worm: WormPair, hub: float, worm_bearing_D: float) -> Housing:
    """箱体尺寸。壁厚按蜗杆减速器的经验式 δ = 0.04a + 3 ≥ 8（蜗杆下置），δ1 = 0.85δ ≥ 8。

    内壁宽度（沿蜗轮轴线）W 取以下三者的大值：蜗轮轮毂长 + 2Δ2；蜗杆齿顶圆直径 + 2Δ1；
    蜗杆轴承座外径减去两侧壁厚（轴承座不超出箱体侧面）。
    """
    a = worm.a / MM
    delta = ceil_to(max(0.04 * a + 3, 8) * MM, 0.5 * MM)
    delta1 = ceil_to(max(0.85 * delta, 8 * MM), 0.5 * MM)
    df = bolt((0.036 * a + 12) * MM)
    d1 = bolt(0.75 * df)
    d2 = bolt(0.5 * df)
    c1, c2 = (v * MM for v in SPANNER_CLEARANCE_MM[round(d1 / MM)])
    l1 = delta + c1 + c2 + 6 * MM
    gap_ax = ceil_to(max(delta, 10 * MM), MM)
    gap_rad = ceil_to(1.2 * delta, MM)
    gap_brg = 10 * MM  # 轴承内侧装挡油盘
    width = ceil_to(max(hub + 2 * gap_ax, worm.da1 + 2 * gap_rad, 2 * boss_radius(worm_bearing_D) - 2 * delta), MM)
    x_in = ceil_to(max(worm.de2 / 2 + gap_rad, worm.b1 / 2 + 5 * MM), MM)
    y_rng = (-(worm.a + worm.da1 / 2 + OIL_BELOW_WORM), worm.de2 / 2 + gap_rad)
    return Housing(delta, delta1, 1.5 * delta, 1.5 * delta1, 2.5 * delta, df, d1, d2, c1, c2, l1,
                   gap_ax, gap_rad, gap_brg, 10 * MM, width, (-x_in, x_in), y_rng, 10 * MM, 15 * MM)


@dataclass
class WormShaft:
    """Ⅰ轴（蜗杆轴）的结构，轴向坐标 = 总体 x。"""

    segments: list[shaft_calc.Segment]
    bearing: standards.TaperedBearing
    bearing_x: tuple[float, float]  # 两轴承压力中心（A 在 −x 一侧）
    bodies: tuple[float, float]  # 两轴承中面
    seat_inner: float  # 轴承座内凸台端面的 |x|
    hub: float
    diameters: dict[str, float]

    @property
    def span(self) -> float:
        return self.bearing_x[1] - self.bearing_x[0]


def worm_shaft(h: Housing, worm: WormPair, brg: standards.TaperedBearing, d_end: float, d_seal: float,
               d_b: float, hub: float) -> WormShaft:
    S = shaft_calc.Segment
    T = brg.T
    x_in = h.x_range[1]
    shoulder = ceil_to(max(d_b + 0.2 * (brg.D - d_b), d_b + 3 * MM), MM)
    # 轴承与螺纹之间的轴段：不超过齿根圆（便于车削、铣削螺纹退刀）
    mid = max(min(shoulder, math.floor(worm.df1 / MM - 1) * MM), d_b + 2 * MM)
    b1 = worm.b1
    # 轴承座内凸台：顶部（y = −a + R凸台）离蜗轮外圆不小于 Δ1，端面离螺纹不小于 10 mm
    r_clear = worm.de2 / 2 + h.gap_radial
    dy = worm.a - boss_radius(brg.D)
    x_b = b1 / 2 + 10 * MM
    if dy < r_clear:
        x_b = max(x_b, math.sqrt(r_clear**2 - dy**2))
    x_b = min(ceil_to(x_b, MM), x_in)
    ca, cb = -x_b - h.gap_bearing - T / 2, x_b + h.gap_bearing + T / 2
    off = brg.a - T / 2  # 正装：压力中心在两轴承内侧
    outer = h.bearing_seat_length + h.cap_thickness + h.coupling_gap
    segs: list[S] = []

    def add(x0, x1, d, role, **kw):
        if x1 - x0 > 1e-9:
            segs.append(S(x0, x1 - x0, d, role, **kw))

    add(-x_in - outer - (hub - 2 * MM), -x_in - outer, d_end, "端部")
    add(-x_in - outer, ca - T / 2, d_seal, "密封")
    add(ca - T / 2, ca + T / 2, d_b, "轴承")
    add(ca + T / 2, -b1 / 2, mid, "轴肩")
    add(-b1 / 2, b1 / 2, worm.da1, "齿轮轴", root_d=worm.df1)
    add(b1 / 2, cb - T / 2, mid, "轴肩")
    add(cb - T / 2, cb + T / 2, d_b, "轴承")
    return WormShaft(segs, brg, (ca + off, cb - off), (ca, cb), x_b, hub,
                     {"端部": d_end, "密封": d_seal, "轴承": d_b, "轴肩": mid})

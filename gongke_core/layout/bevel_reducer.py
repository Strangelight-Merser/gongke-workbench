"""圆锥-圆柱齿轮减速器的结构布置。

坐标与展开式一致：Ⅱ轴（中间轴）在 x = 0、Ⅲ轴在 x = a（圆柱齿轮中心距），z 沿Ⅱ、Ⅲ轴轴线，
内壁在 z = 0 和 z = W，y 向上，剖分面 y = 0。Ⅰ轴（锥齿轮轴）水平放在剖分面上、沿 −x 方向伸出箱体，
轴线与Ⅱ轴轴线相交于锥顶 (0, 0, z_apex)。

大锥齿轮靠近 z = 0 一侧内壁，大端朝向内壁，使它的轴向力（指向大端，−z）与Ⅱ轴上圆柱小齿轮的
轴向力（+z）部分抵消；圆柱齿轮在 z = W 一侧，Ⅲ轴从 z = W 一侧伸出。
Ⅰ轴为悬臂支承：小锥齿轮在内端，一对圆锥滚子轴承反装（背对背）在套杯中，两轴承支点距离
不小于悬臂长度的 2 倍（课程设计指导书推荐 L1 ≈ (2～2.5) L2）。

Ⅰ轴的结构单独用沿轴线向外的坐标 u（u = −x，自锥顶量起）描述。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from gongke_core import standards
from gongke_core.calc import shaft as shaft_calc
from gongke_core.calc.bevel import BevelPair
from gongke_core.calc.gear import GearPair
from gongke_core.layout import bevel_blank
from gongke_core.layout.reducer import (SPANNER_CLEARANCE_MM, Housing, bolt, ceil_to, std_diameter)

MM = 1e-3


def housing(bevel: BevelPair, low: GearPair, bevel_hub: float) -> Housing:
    """箱体尺寸。壁厚等按圆锥-圆柱减速器的经验式：δ = 0.025a + 3 ≥ 8（a 取低速级中心距）。"""
    a = low.a / MM
    delta = max(0.025 * a + 3, 8) * MM
    delta1 = max(0.02 * a + 3, 8) * MM
    df = bolt((0.036 * a + 12) * MM)
    d1 = bolt(0.75 * df)
    d2 = bolt(0.5 * df)
    c1, c2 = (v * MM for v in SPANNER_CLEARANCE_MM[round(d1 / MM)])
    l1 = delta + c1 + c2 + 6 * MM
    gap_ax = ceil_to(max(delta, 10 * MM), MM)
    gap_rad = ceil_to(1.2 * delta, MM)
    v_max = max(bevel.pitch_velocity, low.pitch_velocity)
    gap_brg = 5 * MM if v_max >= 2 else 10 * MM
    c = 10 * MM
    width = gap_ax + bevel_hub + c + low.b1 + gap_ax
    x_min = -(max(bevel.da2 / 2, low.da1 / 2) + gap_rad)
    x_max = low.a + low.da2 / 2 + gap_rad
    r_max = max(bevel.da2, low.da2) / 2
    y_rng = (-(r_max + 40 * MM), r_max + gap_rad)
    return Housing(delta, delta1, 1.5 * delta, 1.5 * delta1, 2.5 * delta, df, d1, d2, c1, c2, l1,
                   gap_ax, gap_rad, gap_brg, c, width, (x_min, x_max), y_rng, 10 * MM, 15 * MM)


def bevel_gear_hub(bevel: BevelPair, seat_d: float) -> float:
    """大锥齿轮轮毂长度，见 `bevel_blank.blank`。"""
    return bevel_blank.hub_length(bevel, 2, seat_d)


@dataclass
class BevelPositions:
    z_back: float  # 大锥齿轮背面（轮毂端面）
    z_large: float  # 大端分度圆所在平面
    z_apex: float  # 锥顶，Ⅰ轴轴线所在的 z
    z_mean: float  # 大锥齿轮齿宽中点（受力点）
    hub: float


def bevel_positions(h: Housing, bevel: BevelPair, hub: float, seat_d: float) -> BevelPositions:
    """大锥齿轮背面贴近 z = 0 一侧内壁（留轴向间隙），沿Ⅱ轴 z = z_apex − t。"""
    g = bevel_blank.blank(bevel, 2, seat_d, hub)
    z_back = h.gap_axial
    z_apex = z_back + g.t_back
    c2 = math.cos(bevel.delta2)
    z_large = z_apex - bevel.cone_distance * c2  # = z_apex − d1/2
    z_mean = z_apex - (bevel.cone_distance - bevel.b / 2) * c2
    return BevelPositions(z_back, z_large, z_apex, z_mean, g.hub_length)


@dataclass
class PinionShaft:
    """Ⅰ轴（小锥齿轮轴）的结构，坐标 u 自锥顶沿轴线向外。"""

    segments: list[shaft_calc.Segment]
    bearing: standards.TaperedBearing
    bearing_u: tuple[float, float]  # 两轴承压力中心（A 靠近锥齿轮）
    u_mean: float  # 小锥齿轮齿宽中点
    u_wall: float  # 箱体内壁（套杯内端）
    integral: bool
    seat_d: float | None
    hub: float  # 联轴器轮毂长度
    diameters: dict[str, float]
    pinion_length: float

    @property
    def overhang(self) -> float:
        return self.bearing_u[0] - self.u_mean

    @property
    def span(self) -> float:
        return self.bearing_u[1] - self.bearing_u[0]


def pinion_needs_integral(bevel: BevelPair, seat_d: float) -> bool:
    """小锥齿轮小端齿根圆到键槽底的距离 e < 1.6m 时做成齿轮轴（濮良贵《机械设计》§10-10）。"""
    df_small = bevel.df1 * (1 - bevel.b / bevel.cone_distance)
    t2 = standards.key_size(seat_d).t2
    return df_small / 2 - (seat_d / 2 + t2) < 1.6 * bevel.m


def pinion_shaft(h: Housing, bevel: BevelPair, brg: standards.TaperedBearing, d_end: float, d_seal: float,
                 d_b: float, hub: float, ratio_span: float = 2.0) -> PinionShaft:
    S = shaft_calc.Segment
    T = brg.T
    shoulder = ceil_to(max(d_b + 0.2 * (brg.D - d_b), d_b + 3 * MM), MM)
    seat = std_diameter(d_b - 3 * MM)  # 小锥齿轮孔径略小于轴承内径，由轴肩定位
    integral = pinion_needs_integral(bevel, seat)
    g = bevel_blank.blank(bevel, 1, seat)
    u_small = g.t_front  # 小端端面
    u_mean = (bevel.cone_distance - bevel.b / 2) * math.cos(bevel.delta1)
    lp = g.hub_length
    u_end = u_small + (0 if integral else 2 * MM)  # 轴端比轮毂缩进 2 mm，用轴端挡圈压紧
    u_wall = -h.x_range[0]
    segs: list[S] = []

    def add(u0, u1, d, role, **kw):
        if u1 - u0 > 1e-9:
            segs.append(S(u0, u1 - u0, d, role, **kw))

    if integral:
        add(u_small, u_small + lp, bevel.df1 * (1 - 0.5 * bevel.b / bevel.cone_distance), "齿轮轴",
            root_d=bevel.df1 * (1 - 0.5 * bevel.b / bevel.cone_distance))
        u_pin_end = u_small + lp
    else:
        add(u_end, u_small + lp, seat, "齿轮")
        u_pin_end = u_small + lp
    # 轴承 A 内侧端面：让开小锥齿轮背面，并位于箱壁外的套杯中
    u_a0 = max(u_pin_end + 8 * MM, u_wall + h.gap_bearing)
    add(u_pin_end, u_a0, shoulder, "轴肩")
    off = brg.a - T / 2  # 反装：压力中心在两轴承外侧
    ua_load = u_a0 + T / 2 - off
    span = max(ratio_span * (ua_load - u_mean), 2 * T + 10 * MM)
    ub_load = ua_load + span
    u_b0 = ub_load - off - T / 2
    add(u_a0, u_a0 + T, d_b, "轴承")
    add(u_a0 + T, u_b0, d_b - 1 * MM, "套筒")  # 两轴承之间，轴径略小便于装拆
    add(u_b0, u_b0 + T, d_b, "轴承")
    outer = 8 * MM + h.cap_thickness + h.coupling_gap  # 套杯凸缘 + 轴承盖 + 联轴器间距
    add(u_b0 + T, u_b0 + T + outer, d_seal, "密封")
    add(u_b0 + T + outer, u_b0 + T + outer + hub - 2 * MM, d_end, "端部")
    return PinionShaft(segs, brg, (ua_load, ub_load), u_mean, u_wall, integral, None if integral else seat, hub,
                       {"端部": d_end, "密封": d_seal, "轴承": d_b, "齿轮": seat, "轴肩": shoulder}, lp)


@dataclass
class Cup:
    """Ⅰ轴轴承套杯（坐标 u）：穿过 −x 端壁的座孔，外端凸缘与轴承座端面贴合并用螺钉固定，
    两轴承外圈靠在中间的挡肩上（反装）。壁厚 δ3 取 8 mm（指导书 7～12 mm）。"""

    D: float  # 内孔（轴承外径）
    D_out: float  # 外径 = 座孔直径
    u0: float  # 内端面（与箱体内壁齐平）
    u_flange: float  # 凸缘内侧端面（= 轴承座外端面）
    flange_t: float
    flange_D: float
    rib: tuple[float, float]  # 挡肩沿 u 的范围
    rib_d: float  # 挡肩孔径
    screw_d: float
    screws: int


CUP_WALL = 8 * MM
CUP_FLANGE = 8 * MM  # 与 pinion_shaft 中密封段长度的取值一致


def cup(ps: PinionShaft) -> Cup:
    from gongke_core.layout.housing_detail import cap_screw

    brg = ps.bearing
    D = brg.D
    D_out = D + 2 * CUP_WALL
    d3, n = cap_screw(D_out)
    b = [s for s in ps.segments if s.role == "轴承"]
    rib = (b[0].z1, b[1].z0)
    w = (D - brg.d) / 2
    return Cup(D, D_out, ps.u_wall, b[1].z1, CUP_FLANGE, D_out + 5 * d3, rib, D - 0.6 * w, d3, n)

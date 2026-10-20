"""展开式二级圆柱齿轮减速器的结构布置：箱体主要尺寸、各零件轴向位置、阶梯轴结构。

尺寸关系按《机械设计课程设计》指导书中"减速器装配草图设计"的经验公式。坐标原点取在输入端
（左侧）箱体内壁与高速轴轴线的交点：z 沿轴线向右，x 沿三根轴的中心连线，y 向上。

为使齿轮远离转矩输入、输出端（减小载荷沿齿宽分布不均），高速级齿轮布置在右侧（远离左侧
输入联轴器），低速级齿轮布置在左侧（远离右侧输出联轴器）。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from gongke_core import standards
from gongke_core.calc import shaft as shaft_calc
from gongke_core.calc.gear import GearPair

MM = 1e-3

# 常用轴径（GB/T 2822 优先数系中常用于轴的尺寸），mm
STANDARD_DIAMETERS_MM = [
    16, 17, 18, 19, 20, 22, 24, 25, 26, 28, 30, 32, 34, 35, 36, 38, 40, 42, 45, 48, 50, 52, 53, 55, 56,
    58, 60, 63, 65, 67, 70, 71, 75, 80, 85, 90, 95, 100, 105, 110, 120,
]
METRIC_BOLTS_MM = [6, 8, 10, 12, 16, 20, 24, 30]
# 螺栓扳手空间 c1、c2（mm），按指导书常用值
SPANNER_CLEARANCE_MM = {8: (13, 11), 10: (16, 14), 12: (18, 16), 16: (22, 20), 20: (26, 24), 24: (34, 28), 30: (40, 34)}


def std_diameter(min_d: float) -> float:
    for v in STANDARD_DIAMETERS_MM:
        if v * MM >= min_d - 1e-9:
            return v * MM
    raise standards.SelectionError(f"轴径 {min_d/MM:.1f} mm 超出常用尺寸范围")


def ceil_to(x: float, step: float) -> float:
    return round(math.ceil(x / step - 1e-9) * step, 9)


def bolt(min_d: float) -> float:
    for v in METRIC_BOLTS_MM:
        if v * MM >= min_d - 1e-9:
            return v * MM
    return METRIC_BOLTS_MM[-1] * MM


@dataclass
class Housing:
    """铸铁箱体主要尺寸（单位 m）。"""

    delta: float  # 箱座壁厚 δ = 0.025a + 3 ≥ 8 mm（a 为低速级中心距）
    delta1: float  # 箱盖壁厚 δ1 = 0.02a + 3 ≥ 8 mm
    flange_base: float  # 箱座凸缘厚度 b = 1.5δ
    flange_cover: float  # 箱盖凸缘厚度 b1 = 1.5δ1
    flange_foot: float  # 箱座底凸缘厚度 b2 = 2.5δ
    bolt_foot: float  # 地脚螺栓直径 df = 0.036a + 12
    bolt_bearing: float  # 轴承旁连接螺栓 d1 = 0.75df
    bolt_flange: float  # 箱盖与箱座连接螺栓 d2 = (0.5–0.6)df
    c1: float
    c2: float
    bearing_seat_length: float  # 轴承座孔长度 L1 = δ + c1 + c2 + (5–8)
    gap_axial: float  # 齿轮端面与内壁距离 Δ2 ≥ δ
    gap_radial: float  # 大齿轮齿顶圆与内壁距离 Δ1 ≥ 1.2δ
    gap_bearing: float  # 轴承内侧端面与内壁距离 Δ3
    gap_gears: float  # 中间轴两齿轮端面间距 c
    inner_width: float  # 箱体内壁间宽度（沿 z）
    x_range: tuple[float, float]  # 内腔沿 x 的范围
    y_range: tuple[float, float]  # 内腔沿 y 的范围（下方含油池）
    cap_thickness: float  # 凸缘式轴承盖厚度 e
    coupling_gap: float  # 轴承盖外端面到联轴器轮毂的距离 K


@dataclass
class GearOnShaft:
    pair: str  # "high" / "low"
    member: int  # 1 小齿轮、2 大齿轮
    z: float  # 齿宽中点
    width: float
    integral: bool  # 是否做成齿轮轴
    seat_d: float | None  # 齿轮孔（轴段）直径，齿轮轴为 None
    mount: str  # 装配方向 "left" / "right"
    root_d: float = 0.0  # 齿根圆直径
    tip_d: float = 0.0  # 齿顶圆直径


@dataclass
class ShaftLayout:
    index: int  # 1、2、3
    name: str
    x: float  # 轴线在 x 方向的位置
    d_min: float
    bearing: standards.Bearing
    bearing_z: tuple[float, float]
    gears: list[GearOnShaft]
    segments: list[shaft_calc.Segment]
    extension: str | None  # 伸出端 "left" / "right"
    coupling_hub: float | None  # 联轴器轮毂长度
    diameters: dict[str, float] = field(default_factory=dict)

    def segment(self, role: str) -> shaft_calc.Segment:
        return next(s for s in self.segments if s.role == role)


def housing(high: GearPair, low: GearPair | None) -> Housing:
    """low 为 None 时是一级减速器：壁厚 δ = 0.025a + 1、δ1 = 0.02a + 1（二级为 + 3），a 为该级中心距。"""
    single = low is None
    last = high if single else low
    a = last.a / MM
    k = 1 if single else 3
    delta = max(0.025 * a + k, 8) * MM
    delta1 = max(0.02 * a + k, 8) * MM
    df = bolt((0.036 * a + 12) * MM)
    d1 = bolt(0.75 * df)
    d2 = bolt(0.5 * df)
    c1, c2 = (v * MM for v in SPANNER_CLEARANCE_MM[round(d1 / MM)])
    l1 = delta + c1 + c2 + 6 * MM
    gap_ax = ceil_to(max(delta, 10 * MM), MM)
    gap_rad = ceil_to(1.2 * delta, MM)
    stages = [high] if single else [high, low]
    v_max = max(p.pitch_velocity for p in stages)
    gap_brg = 5 * MM if v_max >= 2 else 10 * MM  # 油润滑轴承靠近内壁，脂润滑留出挡油环位置
    c = 10 * MM
    width = gap_ax + high.b1 + gap_ax if single else gap_ax + low.b1 + c + high.b1 + gap_ax
    x2 = high.a
    x_min = min(-high.da1 / 2, x2 - high.da2 / 2) - gap_rad
    x_max = (x2 + high.da2 / 2 if single else x2 + low.a + low.da2 / 2) + gap_rad
    r_max = max(p.da2 for p in stages) / 2
    y_rng = (-(r_max + 40 * MM), r_max + gap_rad)
    return Housing(
        delta, delta1, 1.5 * delta, 1.5 * delta1, 2.5 * delta, df, d1, d2, c1, c2, l1,
        gap_ax, gap_rad, gap_brg, c, width, (x_min, x_max), y_rng, 10 * MM, 15 * MM,
    )


def coupling_hub_length(d: float) -> float:
    """联轴器 Y 型轴孔长度的近似（≈ 1.6d + 20 mm），用于确定轴伸长度。选型时应按 GB/T 5014 核对。"""
    return ceil_to(1.6 * d + 20 * MM, MM)


def gear_shaft_needed(df: float, seat_d: float, mn: float) -> bool:
    """齿根圆到键槽底部的距离 e < 2.5 mn 时，小齿轮应与轴做成一体（齿轮轴）。"""
    t2 = standards.key_size(seat_d).t2
    e = df / 2 - (seat_d / 2 + t2)
    return e < 2.5 * mn


@dataclass
class ShaftDiameters:
    end: float | None
    seal: float | None
    bearing: float
    seat: float
    collar: float
    shoulder: float


def diameters(d_bearing: float, bearing_D: float, d_end: float | None, d_seal: float | None) -> ShaftDiameters:
    seat = std_diameter(d_bearing + 3 * MM)  # 非定位轴肩 2–3 mm
    collar = std_diameter(seat * 1.16)  # 定位轴肩 h = (0.07–0.1)d
    # 轴承定位轴肩不低于内圈安装尺寸 da_min ≈ d + 0.2(D − d)
    shoulder = ceil_to(max(d_bearing + 0.2 * (bearing_D - d_bearing), d_bearing + 2 * MM), MM)
    shoulder = min(shoulder, collar)
    return ShaftDiameters(d_end, d_seal, d_bearing, seat, collar, shoulder)


def build_segments(h: Housing, brg: standards.Bearing, dia: ShaftDiameters, gears: list[GearOnShaft],
                   extension: str | None, hub: float | None) -> list[shaft_calc.Segment]:
    """按装配关系从左到右生成阶梯轴各段。

    非整体齿轮：装配一侧用套筒顶住齿轮（轴段比轮毂短 2 mm），另一侧靠轴环定位；
    整体齿轮（齿轮轴）：两侧用轴肩直接定位轴承。
    """
    S = shaft_calc.Segment
    segs: list[S] = []
    B = brg.B
    za = -h.gap_bearing - B / 2
    zb = h.inner_width + h.gap_bearing + B / 2
    zl, zr = za - B / 2, zb + B / 2
    outer = h.bearing_seat_length + h.cap_thickness + h.coupling_gap
    lend = hub - 2 * MM if hub else None

    def add(z0, z1, d, role, **kw):
        if z1 - z0 > 1e-9:
            segs.append(S(z0, z1 - z0, d, role, **kw))

    def shoulder_to_teeth(z0, z1, g, bearing_on_left):
        """齿轮轴：轴承旁留一段定位轴肩，其余部分直径不超过齿根圆，便于滚齿退刀。"""
        relief = max(min(dia.shoulder, math.floor(g.root_d / MM - 1) * MM), dia.bearing)
        if relief >= dia.shoulder - 1e-9 or z1 - z0 < 12 * MM:
            add(z0, z1, dia.shoulder, "轴肩")
        elif bearing_on_left:
            add(z0, z0 + 8 * MM, dia.shoulder, "轴肩")
            add(z0 + 8 * MM, z1, relief, "退刀")
        else:
            add(z0, z1 - 8 * MM, relief, "退刀")
            add(z1 - 8 * MM, z1, dia.shoulder, "轴肩")

    if extension == "left":
        add(-outer - lend, -outer, dia.end, "端部")
        add(-outer, zl, dia.seal, "密封")

    gs = sorted(gears, key=lambda g: g.z)
    cw = None
    first = gs[0]
    f0, f1 = first.z - first.width / 2, first.z + first.width / 2
    if first.integral:
        add(zl, za + B / 2, dia.bearing, "轴承")
        shoulder_to_teeth(za + B / 2, f0, first, True)
        add(f0, f1, first.root_d, "齿轮轴", root_d=first.root_d)
    elif first.mount == "left":
        add(zl, f0 + 2 * MM, dia.bearing, "轴承")  # 轴承 + 套筒
        add(f0 + 2 * MM, f1, dia.seat, "齿轮")
    else:  # 单个齿轮从右侧装入
        cw = max(1.4 * (dia.collar - dia.seat) / 2, 8 * MM)
        add(zl, za + B / 2, dia.bearing, "轴承")
        add(za + B / 2, f0 - cw, dia.shoulder, "轴肩")
        add(f0 - cw, f0, dia.collar, "轴环")
        add(f0, f1 - 2 * MM, dia.seat, "齿轮")
        add(f1 - 2 * MM, zr, dia.bearing, "轴承")
    if len(gs) == 2:
        sec = gs[1]
        s0, s1 = sec.z - sec.width / 2, sec.z + sec.width / 2
        between = "轴环" if not first.integral else "轴肩"
        add(f1, s0, dia.collar if between == "轴环" else dia.shoulder, between)
        if sec.integral:
            add(s0, s1, sec.root_d, "齿轮轴", root_d=sec.root_d)
            shoulder_to_teeth(s1, zb - B / 2, sec, False)
            add(zb - B / 2, zr, dia.bearing, "轴承")
        else:
            add(s0, s1 - 2 * MM, dia.seat, "齿轮")
            add(s1 - 2 * MM, zr, dia.bearing, "轴承")
    elif first.integral:
        shoulder_to_teeth(f1, zb - B / 2, first, False)
        add(zb - B / 2, zr, dia.bearing, "轴承")
    elif first.mount == "left":
        cw = max(1.4 * (dia.collar - dia.seat) / 2, 8 * MM)
        add(f1, f1 + cw, dia.collar, "轴环")
        add(f1 + cw, zb - B / 2, dia.shoulder, "轴肩")
        add(zb - B / 2, zr, dia.bearing, "轴承")

    if extension == "right":
        x_out = h.inner_width + outer
        add(zr, x_out, dia.seal, "密封")
        add(x_out, x_out + lend, dia.end, "端部")
    return segs


def shaft_extension_z(segments: list[shaft_calc.Segment]) -> float | None:
    end = next((s for s in segments if s.role == "端部"), None)
    return None if end is None else end.z0 + end.length / 2

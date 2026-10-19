"""V 带轮结构尺寸，三维建模和二维出图共用。

按濮良贵《机械设计》（第八版）§8-3 带轮结构：
- 基准直径 dd ≤ (2.5～3)d（d 为轴孔直径）时用实心式；dd ≤ 300 mm 时用腹板式，
  轮缘内径与轮毂外径之差 ≥ 100 mm 时在腹板上开孔（孔板式）；dd > 300 mm 时教材推荐轮辐式，
  这里以孔板式代替（说明书和图纸注明）。
- 轮毂外径 d1 = (1.8～2)d，取 2d；轮毂长 L = (1.5～2)d 且不小于轮缘宽 B；腹板厚 C = (1/7～1/4)B，取 B/4 ≥ 10 mm；
  减重孔直径 d0 = (0.2～0.3)(dr − d1)，孔中心圆 D0 = (dr + d1)/2。
轮槽尺寸按 GB/T 10412。单位 m，z 沿轴线，轮毂左端面 z = 0。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from gongke_core import standards
from gongke_core.calc.vbelt import Section

MM = 1e-3


@dataclass
class PulleyBlank:
    sec: Section
    dd: float  # 基准直径
    grooves: int
    bore: float
    hub_length: float
    kind: str  # 实心式 / 腹板式 / 孔板式
    key_b: float
    key_t2: float
    note: str = ""
    hole_d: float = 0.0
    hole_pcd: float = 0.0
    holes: int = 0

    @property
    def da(self) -> float:
        """外径 da = dd + 2ha。"""
        return self.dd + 2 * self.sec.ha

    @property
    def width(self) -> float:
        return self.sec.pulley_width(self.grooves)

    @property
    def angle(self) -> float:
        return self.sec.groove_angle(self.dd)

    @property
    def rim_inner_d(self) -> float:
        """轮缘内径 dr = dd − 2(hf + δ)。"""
        return self.dd - 2 * (self.sec.hf + self.sec.delta)

    @property
    def hub_d(self) -> float:
        return 2 * self.bore

    @property
    def web_thickness(self) -> float:
        return min(max(self.width / 4, 10 * MM), self.width)

    @property
    def z_center(self) -> float:
        return self.hub_length / 2

    def groove_centers(self) -> list[float]:
        z0 = self.z_center - self.width / 2
        return [z0 + self.sec.f + k * self.sec.e for k in range(self.grooves)]

    def groove_half_width(self, r: float) -> float:
        """半径 r 处的轮槽半宽：基准直径处为 bp/2，向外按 φ/2 张开。"""
        return self.sec.bp / 2 + (r - self.dd / 2) * math.tan(math.radians(self.angle / 2))

    def profile(self) -> list[tuple[float, float]]:
        """半剖面轮廓 (r, z)，逆时针，含轮槽，用于回转成实体或画剖视图。"""
        sec = self.sec
        L, zc = self.hub_length, self.z_center
        zr0, zr1 = zc - self.width / 2, zc + self.width / 2
        ro, rb = self.da / 2, self.dd / 2 - sec.hf
        wt, wb = self.groove_half_width(ro), self.groove_half_width(rb)
        rd, rh = self.bore / 2, self.hub_d / 2
        pts: list[tuple[float, float]] = [(rd, 0.0)]
        if self.kind == "实心式":
            rin = min(rh, self.rim_inner_d / 2)
            pts += [(rin, 0.0), (rin, zr0)]
        else:
            c = self.web_thickness
            ri = self.rim_inner_d / 2
            pts += [(rh, 0.0), (rh, zc - c / 2), (ri, zc - c / 2), (ri, zr0)]
        pts.append((ro, zr0))
        for zk in self.groove_centers():
            pts += [(ro, zk - wt), (rb, zk - wb), (rb, zk + wb), (ro, zk + wt)]
        pts.append((ro, zr1))
        if self.kind == "实心式":
            rin = min(rh, self.rim_inner_d / 2)
            pts += [(rin, zr1), (rin, L)]
        else:
            c = self.web_thickness
            ri = self.rim_inner_d / 2
            pts += [(ri, zr1), (ri, zc + c / 2), (rh, zc + c / 2), (rh, L)]
        pts.append((rd, L))
        out = []
        for p in pts:
            if not out or math.hypot(p[0] - out[-1][0], p[1] - out[-1][1]) > 1e-9:
                out.append(p)
        if math.hypot(out[0][0] - out[-1][0], out[0][1] - out[-1][1]) < 1e-9:
            out.pop()
        return out


def blank(sec: Section, dd: float, grooves: int, bore: float, hub_length: float) -> PulleyBlank:
    ks = standards.key_size(bore)
    if dd <= 3 * bore or dd - 2 * (sec.hf + sec.delta) < 2 * bore + 20 * MM:
        kind, note = "实心式", ""
    else:
        dr = dd - 2 * (sec.hf + sec.delta)
        kind = "孔板式" if dr - 2 * bore >= 100 * MM or dd > 300 * MM else "腹板式"
        note = "教材推荐 dd > 300 mm 用轮辐式，此处以孔板式代替" if dd > 300 * MM else ""
    p = PulleyBlank(sec, dd, grooves, bore, hub_length, kind, ks.b, ks.t2, note)
    if kind == "孔板式":
        dr, d1 = p.rim_inner_d, p.hub_d
        p.hole_d = math.floor(0.25 * (dr - d1) / MM) * MM
        p.hole_pcd = (dr + d1) / 2
        p.holes = 6 if dd > 200 * MM else 4
    return p


def large_pulley(design) -> PulleyBlank | None:
    """V 带方案中装在Ⅰ轴轴伸上的大带轮。"""
    b = design.belt
    if b is None:
        return None
    lay = design.shafts[0].layout
    return blank(b.sec, b.dd2, b.z, lay.diameters["端部"], lay.coupling_hub)

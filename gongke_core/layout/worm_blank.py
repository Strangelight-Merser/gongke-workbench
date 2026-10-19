"""蜗轮结构尺寸（齿圈压配式），三维建模和二维出图共用。

坐标：z 沿蜗轮轴线、中间平面 z = 0，r 为半径，单位 m。
- 齿圈用青铜，轮芯用灰铸铁，齿圈压配在轮芯上，接缝处沿轴向装 4～6 个紧定螺钉（直径 (1.2～1.5)m，
  拧入深度 (0.3～0.4)b2），螺钉孔中心向材料较硬的轮芯一侧偏 2～3 mm。
- 齿圈在齿根以下的厚度 max(2m, 10 mm)；轮芯轮缘厚度 max(1.6m, 10 mm)，轮缘一端做出挡肩给齿圈轴向定位。
- 齿顶：中间平面内为喉圆，r = a − √(rg2² − z²)（rg2 = a − da2/2，以蜗杆轴线为圆心的圆弧），外径不超过 de2。
- 轮毂外径 1.6d，长度按 `layout.worm_reducer.wheel_hub`；腹板厚 C = max(0.3b2, 10 mm)，开减重孔。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from gongke_core import standards
from gongke_core.calc.worm import WormPair

MM = 1e-3


@dataclass
class WheelBlank:
    a: float
    z2: int
    m: float
    d2: float
    da2: float
    df2: float
    de2: float
    rg2: float  # 喉圆半径
    b2: float
    bore: float
    hub_length: float
    hub_d: float
    key_b: float
    key_t2: float
    ring_inner_d: float  # 齿圈内径（= 轮芯外径）
    core_inner_d: float  # 轮芯轮缘内径
    shoulder: float  # 轮芯挡肩的轴向厚度
    shoulder_d: float  # 挡肩外径
    web_thickness: float
    holes: int
    hole_d: float
    hole_pcd: float
    screws: int
    screw_d: float
    screw_depth: float
    screw_r: float  # 紧定螺钉中心所在半径

    def tip_r(self, z: float) -> float:
        """齿顶在 z 处的半径：喉圆与外径 de2/2 的较小者。"""
        if abs(z) >= self.rg2:
            return self.de2 / 2
        return min(self.de2 / 2, self.a - math.sqrt(self.rg2**2 - z**2))

    @property
    def throat_z(self) -> float:
        """喉圆与外圆柱 de2 的交点 |z|。"""
        dr = self.a - self.de2 / 2
        return math.sqrt(max(self.rg2**2 - dr**2, 0.0))

    def ring_profile(self, n: int = 16) -> list[tuple[float, float]]:
        """齿圈半剖面 (z, r)：内孔 → 一侧端面 → 齿顶（喉圆） → 另一侧端面。"""
        h = self.b2 / 2
        ri = self.ring_inner_d / 2
        top = []
        zt = min(self.throat_z, h)
        top.append((-h, self.tip_r(-h)))
        for k in range(n + 1):
            z = -zt + 2 * zt * k / n
            top.append((z, self.tip_r(z)))
        top.append((h, self.tip_r(h)))
        pts = [(-h, ri)] + top + [(h, ri)]
        out = [pts[0]]
        for p in pts[1:]:
            if math.dist(p, out[-1]) > 1e-7:
                out.append(p)
        return out

    def core_profile(self) -> list[tuple[float, float]]:
        """轮芯半剖面 (z, r)：轮毂 + 腹板 + 轮缘，轮缘在 −z 一端有挡肩。"""
        h = self.b2 / 2
        L = self.hub_length / 2
        rb, rh = self.bore / 2, self.hub_d / 2
        ro, rc = self.ring_inner_d / 2, self.core_inner_d / 2
        c = self.web_thickness / 2
        z0 = -h - self.shoulder
        return [(-L, rb), (-L, rh), (-c, rh), (-c, rc), (z0, rc), (z0, self.shoulder_d / 2), (-h, self.shoulder_d / 2),
                (-h, ro), (h, ro), (h, rc), (c, rc), (c, rh), (L, rh), (L, rb)]


def blank(w: WormPair, bore: float, hub_length: float) -> WheelBlank:
    m = w.m
    ks = standards.key_size(bore)
    ring = max(2 * m, 10 * MM)
    core = max(1.6 * m, 10 * MM)
    ring_in = w.df2 - 2 * ring
    core_in = ring_in - 2 * core
    hub_d = 1.6 * bore
    c = max(0.3 * w.b2, 10 * MM)
    if core_in < hub_d + 10 * MM:  # 尺寸小时轮芯做成实心（腹板一直到轮毂）
        core_in = hub_d
    screw_d = max(round(1.3 * m / MM), 6) * MM
    holes = 6 if core_in - hub_d > 40 * MM else 0
    return WheelBlank(
        w.a, w.z2, m, w.d2, w.da2, w.df2, w.de2, w.throat_radius, w.b2, bore, hub_length, hub_d, ks.b, ks.t2,
        ring_in, core_in, max(0.1 * w.b2, 5 * MM), ring_in + ring, c,
        holes, 0.25 * (core_in - hub_d) if holes else 0.0, 0.5 * (core_in + hub_d) if holes else 0.0,
        6, screw_d, math.ceil(0.35 * w.b2 / MM) * MM, ring_in / 2 - 2 * MM,
    )

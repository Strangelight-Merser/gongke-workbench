"""直齿锥齿轮的结构尺寸（轴向半剖面），三维建模、二维出图和结构布置共用。

坐标：t 沿齿轮轴线自锥顶向外（大端方向为正），r 为半径，单位 m。按正常收缩齿（齿顶圆锥、齿根圆锥的
锥顶都与分度圆锥的锥顶重合），ha = m，hf = 1.2m。
- 大端：分度点 P_L = (R cos δ, R sin δ)，背锥垂直于分度圆锥母线，齿顶 T_L = P_L + m n，齿根 F_L = P_L − 1.2m n，
  n = (−sin δ, cos δ)；小端各点按 (R − b)/R 缩小。
- 轮缘：背锥在齿根以下再延长轮缘厚度 δ0 = max(3m, 10 mm) 到 K 点，过 K 作垂直于轴线的背面。
- 轮毂外径 1.6d。小锥齿轮（member 1）的轮毂从小端端面向外（背面一侧）伸出；大锥齿轮（member 2）的
  轮毂从背面向锥顶方向伸出，长度不小于齿宽在轴线上的投影。大锥齿轮的轮缘内径与轮毂外径相差
  较大时，在锥顶一侧挖出凹槽，留下厚 C = max(0.3b, 10 mm) 的腹板。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from gongke_core import standards
from gongke_core.calc.bevel import BevelPair

MM = 1e-3


@dataclass
class BevelBlank:
    member: int
    z: int
    m: float
    delta: float
    R: float
    b: float
    d: float
    da: float
    bore: float | None
    hub_length: float  # 轮毂总长
    key_b: float | None
    key_t2: float | None
    rim: float  # δ0
    web: bool = False
    web_thickness: float = 0.0

    def _pt(self, rho: float, h: float) -> tuple[float, float]:
        """母线上距锥顶 rho 处、沿背锥方向偏 h（向外为正）的点。"""
        c, s = math.cos(self.delta), math.sin(self.delta)
        return (rho * c - h * s, rho * s + h * c)

    @property
    def tip_large(self):
        return self._pt(self.R, self.m)

    @property
    def root_large(self):
        return self._pt(self.R, -1.2 * self.m)

    @property
    def tip_small(self):
        k = (self.R - self.b) / self.R
        t, r = self.tip_large
        return (k * t, k * r)

    @property
    def root_small(self):
        k = (self.R - self.b) / self.R
        t, r = self.root_large
        return (k * t, k * r)

    @property
    def back_point(self):
        """背锥上轮缘最低点 K。"""
        return self._pt(self.R, -1.2 * self.m - self.rim)

    @property
    def t_back(self) -> float:
        return self.back_point[0]

    @property
    def t_front(self) -> float:
        """小端端面（垂直于轴线，过小端齿根点）。"""
        return self.root_small[0]

    @property
    def hub_r(self) -> float:
        return min(0.8 * self.bore, self.back_point[1]) if self.bore else 0.0

    @property
    def hub_span(self) -> tuple[float, float]:
        """轮毂（孔）沿 t 的范围 (前端, 后端)。"""
        if self.member == 1:
            return self.t_front, self.t_front + self.hub_length
        return self.t_back - self.hub_length, self.t_back

    @property
    def rim_inner_r(self) -> float:
        return self.root_small[1] - self.rim

    def profile(self) -> list[tuple[float, float]]:
        """轴向半剖面轮廓 (t, r)，不含键槽；齿部按齿顶圆锥画实体。"""
        rb = self.bore / 2
        rh = self.hub_r
        t0, t1 = self.hub_span
        tk, rk = self.back_point
        tf = self.t_front
        pts = [self.tip_small, self.tip_large, self.root_large, (tk, rk)]
        if self.member == 1:
            pts += [(tk, rh), (t1, rh), (t1, rb), (tf, rb)]
        else:
            pts += [(tk, rb), (t0, rb), (t0, rh)]
            if self.web:
                c = self.web_thickness
                pts += [(tk - c, rh), (tk - c, self.rim_inner_r), (tf, self.rim_inner_r)]
            else:
                pts += [(tf, rh)]
        pts.append(self.root_small)
        out = []
        for p in pts:
            if not out or math.dist(p, out[-1]) > 1e-9:
                out.append(p)
        return out


def blank(pair: BevelPair, member: int, bore: float, hub_length: float | None = None) -> BevelBlank:
    m = pair.m
    delta = pair.delta1 if member == 1 else pair.delta2
    z = pair.z1 if member == 1 else pair.z2
    d = pair.d1 if member == 1 else pair.d2
    da = pair.da1 if member == 1 else pair.da2
    ks = standards.key_size(bore)
    rim = max(3 * m, 10 * MM)
    g = BevelBlank(member, z, m, delta, pair.cone_distance, pair.b, d, da, bore, 0.0, ks.b, ks.t2, rim)
    span = g.t_back - g.t_front  # 齿部和轮缘在轴线上的投影
    min_len = span + (5 * MM if member == 1 else 0.0)
    g.hub_length = math.ceil(max(hub_length or 0.0, min_len, 1.2 * bore) / MM - 1e-9) * MM
    if member == 2:
        c = max(0.3 * pair.b, 10 * MM)
        if g.rim_inner_r - g.hub_r >= 15 * MM and span - c >= 5 * MM:
            g.web, g.web_thickness = True, c
    return g


def hub_length(pair: BevelPair, member: int, bore: float) -> float:
    return blank(pair, member, bore).hub_length

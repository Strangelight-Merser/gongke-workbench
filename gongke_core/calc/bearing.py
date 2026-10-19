"""深沟球轴承的当量动载荷与寿命计算。"""

from __future__ import annotations

from dataclasses import dataclass

from gongke_core import standards


def equivalent_load(fr: float, fa: float, c0r: float, f_p: float = 1.1) -> tuple[float, float, float, float]:
    """当量动载荷 P = fp (X Fr + Y Fa)。返回 (P, e, X, Y)。

    fp 为载荷系数，轻微冲击取 1.0–1.2。X、Y 按 GB/T 6391 由 Fa/C0r 插值。
    """
    if fa <= 0:
        return f_p * fr, 0.0, 1.0, 0.0
    e, x2, y2 = standards.radial_load_factors(fa / c0r)
    if fr > 0 and fa / fr <= e:
        x, y = 1.0, 0.0
    else:
        x, y = x2, y2
    return f_p * (x * fr + y * fa), e, x, y


def life_hours(c: float, p: float, speed_rpm: float, exponent: float = 3.0) -> float:
    """基本额定寿命 L10h = 10⁶ / (60 n) · (C/P)^ε，球轴承 ε = 3。"""
    return 1e6 / (60 * speed_rpm) * (c / p) ** exponent


@dataclass
class BearingCheck:
    bearing: standards.Bearing
    fr: tuple[float, float]  # 两端径向载荷 A、B
    fa: tuple[float, float]  # 两端轴向载荷
    p: tuple[float, float]
    e: tuple[float, float]
    x: tuple[float, float]
    y: tuple[float, float]
    life: tuple[float, float]  # h
    required: float  # h

    @property
    def ok(self) -> bool:
        return min(self.life) >= self.required


def check_pair(bearing: standards.Bearing, fr_a: float, fr_b: float, axial: float,
               speed_rpm: float, required_hours: float, f_p: float = 1.1) -> BearingCheck:
    """两端固定支承：轴向合力沿 +z 时由 B 端轴承承受，沿 −z 时由 A 端承受。"""
    fa = (0.0, axial) if axial >= 0 else (-axial, 0.0)
    res = [equivalent_load(fr, f, bearing.C0r, f_p) for fr, f in zip((fr_a, fr_b), fa)]
    lives = tuple(life_hours(bearing.Cr, r[0], speed_rpm) for r in res)
    return BearingCheck(
        bearing, (fr_a, fr_b), fa,
        tuple(r[0] for r in res), tuple(r[1] for r in res),
        tuple(r[2] for r in res), tuple(r[3] for r in res), lives, required_hours,
    )

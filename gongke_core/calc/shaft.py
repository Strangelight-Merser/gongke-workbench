"""轴的强度计算：按扭转强度估算最小直径，两平面受力分析，按弯扭合成应力校核。

坐标约定：z 为轴线方向；x 为三根轴中心连线方向（水平）；y 垂直于 x、z。
啮合点都在中心连线上，所以径向力沿 x、圆周力沿 y，轴向力对轴线的偏距只产生 x–z 平面内的力偶。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


def min_diameter(power: float, speed_rpm: float, a0: float = 112) -> float:
    """按扭转强度估算轴的最小直径 d ≥ A0 ∛(P/n)。

    教材公式中 P 用 kW、n 用 r/min、d 得 mm；A0 对 45 钢取 103–126。返回值单位 m。
    """
    return a0 * (power / 1e3 / speed_rpm) ** (1 / 3) * 1e-3


@dataclass
class Segment:
    """阶梯轴的一段。z0 为起点，length 为长度，单位 m。"""

    z0: float
    length: float
    d: float
    role: str  # 端部 / 密封 / 轴承 / 齿轮 / 轴环 / 轴肩 / 套筒 / 齿轮轴
    keyway: tuple[float, float, float] | None = None  # (键宽 b, 轴槽深 t1, 键长 L)
    root_d: float | None = None  # 齿轮轴的齿根圆直径，校核时用它代替 d

    @property
    def z1(self) -> float:
        return self.z0 + self.length


@dataclass
class PointLoad:
    """作用在轴上的集中力。偏距 (x0, y0) 是力作用点到轴线的位置，用于计算轴向力的力偶。"""

    z: float
    fx: float = 0.0
    fy: float = 0.0
    fz: float = 0.0
    x0: float = 0.0
    y0: float = 0.0
    label: str = ""

    @property
    def couple_xz(self) -> float:
        """x–z 平面内的力偶（以 (z, x) 平面逆时针为正）：M = −x0·Fz。"""
        return -self.x0 * self.fz

    @property
    def couple_yz(self) -> float:
        """y–z 平面内的力偶：M = −y0·Fz。"""
        return -self.y0 * self.fz


@dataclass
class ShaftLoadCase:
    supports: tuple[float, float]  # 两轴承中心的 z
    loads: list[PointLoad]
    torque_points: list[tuple[float, float]]  # (z, 输入转矩)，正值输入、负值输出，合计应为 0


@dataclass
class Reactions:
    ax: float
    ay: float
    bx: float
    by: float
    axial: float  # 轴向力合力（沿 +z 为正）

    @property
    def radial_a(self) -> float:
        return math.hypot(self.ax, self.ay)

    @property
    def radial_b(self) -> float:
        return math.hypot(self.bx, self.by)


def reactions(case: ShaftLoadCase) -> Reactions:
    za, zb = case.supports
    span = zb - za
    out = []
    for f_attr, c_attr in (("fx", "couple_xz"), ("fy", "couple_yz")):
        sf = sum(getattr(p, f_attr) for p in case.loads)
        sm = sum((p.z - za) * getattr(p, f_attr) + getattr(p, c_attr) for p in case.loads)
        rb = -sm / span
        ra = -sf - rb
        out.append((ra, rb))
    (ax, bx), (ay, by) = out
    return Reactions(ax, ay, bx, by, sum(p.fz for p in case.loads))


def _moment(z: float, forces: list[tuple[float, float, float]]) -> float:
    """截面 z 处的弯矩，取左侧隔离体：M = Σ F(z − zi) − ΣC。forces 为 (zi, F, C)。"""
    return sum(f * (z - zi) - c for zi, f, c in forces if zi < z)


def bending_moments(case: ShaftLoadCase, z: float) -> tuple[float, float]:
    r = reactions(case)
    za, zb = case.supports
    fx = [(za, r.ax, 0.0), (zb, r.bx, 0.0)] + [(p.z, p.fx, p.couple_xz) for p in case.loads]
    fy = [(za, r.ay, 0.0), (zb, r.by, 0.0)] + [(p.z, p.fy, p.couple_yz) for p in case.loads]
    return _moment(z, fx), _moment(z, fy)


def torque_at(case: ShaftLoadCase, z: float) -> float:
    return sum(t for zt, t in case.torque_points if zt < z)


def section_modulus(d: float, keyway: tuple[float, float, float] | None = None) -> float:
    """抗弯截面系数 W = πd³/32，有单键槽时 W = πd³/32 − b t (d − t)² / (2d)。"""
    w = math.pi * d**3 / 32
    if keyway:
        b, t, _ = keyway
        w -= b * t * (d - t) ** 2 / (2 * d)
    return w


@dataclass
class CriticalSection:
    z: float
    d: float
    m_x: float
    m_y: float
    torque: float
    sigma_ca: float
    role: str

    @property
    def m(self) -> float:
        return math.hypot(self.m_x, self.m_y)


@dataclass
class ShaftCheck:
    reactions: Reactions
    critical: CriticalSection
    sigma_allow: float
    alpha: float
    samples: list[CriticalSection] = field(repr=False)

    @property
    def ok(self) -> bool:
        return self.critical.sigma_ca <= self.sigma_allow


def check(segments: list[Segment], case: ShaftLoadCase, sigma_allow: float = 60e6,
          alpha: float = 0.6, n: int = 1200) -> ShaftCheck:
    """按弯扭合成应力校核：σca = √(M² + (αT)²) / W ≤ [σ−1b]。

    α 为折合系数：单向转动、扭转切应力按脉动循环取 0.6。[σ−1b] 对 45 钢调质取 60 MPa。
    沿轴均匀取样，并覆盖各段和转矩事件的左右侧，取 σca 最大处为危险截面。
    """
    z_start, z_end = segments[0].z0, segments[-1].z1
    zs = {z_start + (z_end - z_start) * i / n for i in range(n + 1)}
    eps = 1e-6
    for s in segments:
        zs.update((s.z0 + eps, s.z1 - eps))
    for p in case.loads:
        zs.update((p.z - eps, p.z + eps))
    # 转矩在施加位置跳变；固定 eps 可能跨过整个窄区间，必须取事件的相邻浮点位置。
    # 同时覆盖直径突变两侧，不能把小直径侧的转矩误配到大直径截面。
    boundaries = {z for s in segments for z in (s.z0, s.z1)}
    boundaries.update(z for z, _ in case.torque_points)
    for z in boundaries:
        zs.update((z, math.nextafter(z, -math.inf), math.nextafter(z, math.inf)))
    samples = []
    for z in sorted(zs):
        seg = next((s for s in segments if s.z0 <= z <= s.z1), None)
        if seg is None:
            continue
        d = seg.root_d or seg.d
        mx, my = bending_moments(case, z)
        t = torque_at(case, z)
        kw = seg.keyway if seg.keyway and (seg.z0 + seg.length / 2 - seg.keyway[2] / 2 <= z <= seg.z0 + seg.length / 2 + seg.keyway[2] / 2) else None
        sigma = math.sqrt(mx**2 + my**2 + (alpha * t) ** 2) / section_modulus(d, kw)
        samples.append(CriticalSection(z, d, mx, my, t, sigma, seg.role))
    crit = max(samples, key=lambda s: s.sigma_ca)
    return ShaftCheck(reactions(case), crit, sigma_allow, alpha, samples)

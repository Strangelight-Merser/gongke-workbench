"""轴的弯曲刚度计算：阶梯轴在两平面内的挠度和偏转角。

把轴看成支承在两轴承中心的简支梁（静定），弯矩 M(z) 由 `shaft.bending_moments` 给出，
曲率 y'' = M / (E I(z))，沿轴向数值积分两次，再按两支点挠度为零确定积分常数。
各段截面惯性矩 I = π d⁴ / 64；齿轮轴的轮齿段偏安全地按齿根圆直径计算，键槽对刚度的影响忽略。

许用值按《机械设计》（濮良贵、纪名刚主编，第 9 版，高等教育出版社）表 15-5：
安装齿轮的轴 [y] = (0.01～0.03) mn，本程序取中值 0.02 mn；
偏转角：安装齿轮处 [θ] = 0.001～0.002 rad（取 0.002），深沟球轴承处 0.005 rad，圆锥滚子轴承处 0.0016 rad。
"""

from __future__ import annotations

import bisect
import math
from dataclasses import dataclass, field

from gongke_core.calc.shaft import Segment, ShaftLoadCase, bending_moments

E_STEEL = 2.06e11  # 钢的弹性模量，Pa

THETA_ALLOW = {"深沟球轴承": 0.005, "圆锥滚子轴承": 0.0016, "齿轮": 0.002}
Y_ALLOW_FACTOR = 0.02  # [y] = 0.02 mn


@dataclass
class Deflection:
    """沿轴各点的挠度和偏转角（两平面），z 单调递增，单位 m、rad。"""

    z: list[float]
    yx: list[float]
    yy: list[float]
    tx: list[float]
    ty: list[float]

    def _interp(self, arr: list[float], z: float) -> float:
        i = min(max(bisect.bisect_left(self.z, z), 1), len(self.z) - 1)
        z0, z1 = self.z[i - 1], self.z[i]
        w = 0.0 if z1 == z0 else (z - z0) / (z1 - z0)
        return arr[i - 1] + w * (arr[i] - arr[i - 1])

    def deflection(self, z: float) -> float:
        """合成挠度 √(yx² + yy²)。"""
        return math.hypot(self._interp(self.yx, z), self._interp(self.yy, z))

    def slope(self, z: float) -> float:
        """合成偏转角 √(θx² + θy²)。"""
        return math.hypot(self._interp(self.tx, z), self._interp(self.ty, z))

    def components(self, z: float) -> tuple[float, float, float, float]:
        """(yx, yy, θx, θy)。"""
        return tuple(self._interp(a, z) for a in (self.yx, self.yy, self.tx, self.ty))  # type: ignore[return-value]


def _diameter(segments: list[Segment], z: float) -> float:
    seg = next((s for s in segments if s.z0 <= z <= s.z1), segments[0] if z < segments[0].z0 else segments[-1])
    return seg.root_d or seg.d


def _second_moment(segments: list[Segment], z: float) -> float:
    return math.pi * _diameter(segments, z) ** 4 / 64


def _shear_force(case: ShaftLoadCase, z: float) -> tuple[float, float]:
    """截面 z 处的剪力（左侧隔离体上外力之和），两平面。"""
    from gongke_core.calc.shaft import reactions

    r = reactions(case)
    za, zb = case.supports
    fx = [(za, r.ax), (zb, r.bx)] + [(p.z, p.fx) for p in case.loads]
    fy = [(za, r.ay), (zb, r.by)] + [(p.z, p.fy) for p in case.loads]
    return sum(f for zi, f in fx if zi < z), sum(f for zi, f in fy if zi < z)


def solve(segments: list[Segment], case: ShaftLoadCase, E: float = E_STEEL, step: float = 0.25e-3,
          shear: bool = False, nu: float = 0.3) -> Deflection:
    """数值积分求两平面的挠度曲线。在截面突变、载荷作用点处加密，梯形公式积分。

    shear=True 时按 Timoshenko 梁计入剪切变形：y' = θ + V/(κGA)，实心圆截面 κ = 6(1+ν)/(7+6ν)（Cowper）；
    教材的刚度校核不计剪切变形，此项只用于和有限元结果对照。"""
    z0, z1 = segments[0].z0, segments[-1].z1
    za, zb = case.supports
    pts = {z0, z1, za, zb}
    for s in segments:
        pts.update((s.z0, s.z1))
    for p in case.loads:
        pts.add(p.z)
    n = max(int((z1 - z0) / step), 1)
    pts.update(z0 + (z1 - z0) * k / n for k in range(n + 1))
    zs = sorted(p for p in pts if z0 <= p <= z1)
    # 曲率：在每个小区间中点取值（避开截面突变点和集中力偶处的跳变）
    out = {}
    for plane in (0, 1):
        theta = [0.0]
        y = [0.0]
        kappa_s = 6 * (1 + nu) / (7 + 6 * nu)
        G = E / (2 * (1 + nu))
        for a, b in zip(zs, zs[1:]):
            m = 0.5 * (a + b)
            k = bending_moments(case, m)[plane] / (E * _second_moment(segments, m))
            theta.append(theta[-1] + k * (b - a))
            gamma = 0.0
            if shear:  # 剪切变形使挠度沿载荷方向增大：y_s' = −V/(κGA)（本文件弯矩、剪力的符号约定下）
                area = math.pi * _diameter(segments, m) ** 2 / 4
                gamma = -_shear_force(case, m)[plane] / (kappa_s * G * area)
            y.append(y[-1] + (0.5 * (theta[-2] + theta[-1]) + gamma) * (b - a))
        # 加上刚体位移 c0 + c1 (z − z0)，使两支点挠度为零
        tmp = Deflection(zs, y, y, theta, theta)
        ya, yb_ = tmp._interp(y, za), tmp._interp(y, zb)
        c1 = -(yb_ - ya) / (zb - za)
        c0 = -ya - c1 * (za - z0)
        out[plane] = ([v + c0 + c1 * (z - z0) for v, z in zip(y, zs)], [t + c1 for t in theta])
    (yx, tx), (yy, ty) = out[0], out[1]
    return Deflection(zs, yx, yy, tx, ty)


@dataclass
class StiffnessItem:
    label: str
    kind: str  # "y" 挠度 / "θ" 偏转角
    z: float
    value: float
    allow: float

    @property
    def ok(self) -> bool:
        return self.value <= self.allow


@dataclass
class StiffnessCheck:
    items: list[StiffnessItem]
    curve: Deflection = field(repr=False)

    @property
    def ok(self) -> bool:
        return all(i.ok for i in self.items)


def check(segments: list[Segment], case: ShaftLoadCase, gears: list[tuple[str, float, float]], bearing_kind: str,
          E: float = E_STEEL) -> StiffnessCheck:
    """刚度校核。gears 为 (名称, 齿宽中点 z, 法面模数 mn)；bearing_kind 为 THETA_ALLOW 的键。"""
    curve = solve(segments, case, E)
    items = []
    for name, z, mn in gears:
        items.append(StiffnessItem(f"{name}处挠度", "y", z, curve.deflection(z), Y_ALLOW_FACTOR * mn))
        items.append(StiffnessItem(f"{name}处偏转角", "θ", z, curve.slope(z), THETA_ALLOW["齿轮"]))
    for side, z in zip(("左", "右"), case.supports):
        items.append(StiffnessItem(f"{side}轴承处偏转角", "θ", z, curve.slope(z), THETA_ALLOW[bearing_kind]))
    return StiffnessCheck(items, curve)

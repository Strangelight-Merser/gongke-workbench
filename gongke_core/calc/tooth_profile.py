"""齿条型刀具展成的直齿轮端面齿廓：渐开线齿廓 + 齿根过渡曲线（刀具齿顶圆角展成的延伸渐开线等距线）。

基本齿条按 GB/T 1356-2001 的参数取值：齿顶高系数 ha* = 1、顶隙系数 c* = 0.25、齿根圆角半径系数 ρf* = 0.38，
压力角 20°（只录入这几个数值）。展成计算用啮合基本定律：刀具上一点与齿轮接触时，该点的法线通过节点。

坐标：齿轮中心为原点，齿的对称线为 +y 轴；长度单位与模数相同（通常取 m = 1 无量纲化）。
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class ToothProfile:
    """一个齿右半边的轮廓，从齿根圆（齿槽中线处）到齿顶，点为 (x, y)。

    fillet：齿根过渡曲线上的点（含与齿根圆、渐开线的连接点）；involute：渐开线部分；
    tip：齿顶圆弧（从齿顶角点到对称线）。"""

    z: float
    m: float
    alpha: float
    root: list[tuple[float, float]]
    fillet: list[tuple[float, float]]
    involute: list[tuple[float, float]]
    tip: list[tuple[float, float]]

    @property
    def r(self) -> float:
        return self.z * self.m / 2

    @property
    def ra(self) -> float:
        return self.r + self.m

    @property
    def rf(self) -> float:
        return self.r - 1.25 * self.m

    def half(self) -> list[tuple[float, float]]:
        """右半边完整轮廓（齿槽中线 → 齿顶对称线），首尾相接无重复点。"""
        out = []
        for part in (self.root, self.fillet, self.involute, self.tip):
            for p in part:
                if not out or math.dist(out[-1], p) > 1e-9 * self.m:
                    out.append(p)
        return out


def _rotate(p, a):
    c, s = math.cos(a), math.sin(a)
    return (p[0] * c - p[1] * s, p[0] * s + p[1] * c)


def generate(z: float, m: float = 1.0, alpha: float = math.radians(20), ha: float = 1.0, c: float = 0.25,
             rho: float = 0.38, n_fillet: int = 24, n_involute: int = 24) -> ToothProfile:
    """标准齿轮（不变位）的单齿轮廓。z 可以是非整数（斜齿轮、锥齿轮的当量齿数）。"""
    r = z * m / 2
    hf = (ha + c) * m  # 刀具齿顶高 = 齿轮齿根高
    rho = rho * m
    # 刀具齿条坐标（固定坐标系，节点 (0, r)）：u 沿节线，v 自节线向外（远离齿轮中心）为正。
    # 刀具齿位于齿轮的齿槽中，槽中线在 u = 0；刀具齿右侧齿廓：u = πm/4 + v·tanα（v ≤ 0 向齿轮内伸入）。
    t_a = math.tan(alpha)
    vc = -hf + rho  # 刀尖圆角圆心
    uc = math.pi * m / 4 + vc * t_a - rho / math.cos(alpha)

    def envelope(u, v, nu, nv):
        """刀具点 (u, v)、外法线 (nu, nv) 生成的齿轮齿廓点（齿轮坐标）。"""
        if abs(nv) < 1e-12:
            return None
        up = u - v * nu / nv  # 法线与节线的交点
        s = -up  # 刀具平移 s 使该交点到达节点；齿轮相应转过 φ = s/r
        phi = s / r
        p = (u + s, r + v)
        return _rotate(p, phi)  # 齿轮反转回原位（刀具右移时齿轮顺时针转）

    # 过渡曲线：刀尖圆角，法线从 (0, −1) 转到 (cosα, −sinα)
    fillet = []
    t_end = math.pi / 2 - alpha
    for i in range(n_fillet + 1):
        t = t_end * i / n_fillet
        nu, nv = math.sin(t), -math.cos(t)
        u, v = uc + rho * nu, vc + rho * nv
        pt = envelope(u, v, nu, nv) if i > 0 else None
        if pt is None:  # t = 0：刀尖平顶上的点平移到节点正下方时切出齿根圆
            pt = _rotate((0.0, r + v), -u / r)
        fillet.append(pt)
    # 渐开线：刀具直线齿廓从圆角切点到 v = ha·m（生成到齿顶以外，再截到齿顶圆）
    v0 = vc - rho * math.sin(alpha)
    ra = r + ha * m
    inv = []
    for i in range(1, 4 * n_involute + 1):
        v = v0 + (ha * m * 1.2 - v0) * i / (4 * n_involute)
        u = math.pi * m / 4 + v * t_a
        pt = envelope(u, v, math.cos(alpha), -math.sin(alpha))
        inv.append(pt)
        if math.hypot(*pt) >= ra:
            break
    # 截到齿顶圆：直线齿廓生成的是渐开线，齿顶点直接按渐开线方程求（与 to_tooth 变换后的坐标一致，见下）
    a_ra = math.acos(r * math.cos(alpha) / ra)
    half_a = math.pi / (2 * z) + (math.tan(alpha) - alpha) - (math.tan(a_ra) - a_ra)
    inv = inv[:-1]
    # 以上齿廓属于齿槽（中线 u = 0，即 +y 轴）右侧的齿的左齿廓；把它转到“齿对称线为 +y、轮廓在右半边”的位置：
    # 该齿的对称线在 −π/z（顺时针半个齿距），关于它镜像后再转到 +y。
    def to_tooth(p):
        q = _rotate(p, math.pi / z)  # 齿对称线转到 +y
        return (-q[0], q[1])  # 镜像到右半边

    fillet = [to_tooth(p) for p in fillet]
    inv = [to_tooth(p) for p in inv] + [(ra * math.sin(half_a), ra * math.cos(half_a))]
    # 齿根圆：从齿槽中线（角度 π/z 处，右侧）到过渡曲线起点
    a_space = math.pi / 2 - math.pi / z
    rf = r - hf
    a_f = math.atan2(fillet[0][1], fillet[0][0])
    root = [(rf * math.cos(a_space + (a_f - a_space) * k / 4), rf * math.sin(a_space + (a_f - a_space) * k / 4))
            for k in range(4)] + [fillet[0]] if a_f > a_space + 1e-9 else []
    a_t = math.atan2(inv[-1][1], inv[-1][0])
    tip = [(ra * math.cos(a_t + (math.pi / 2 - a_t) * k / 6), ra * math.sin(a_t + (math.pi / 2 - a_t) * k / 6))
           for k in range(7)]
    return ToothProfile(z, m, alpha, root, fillet, [fillet[-1]] + inv, tip)

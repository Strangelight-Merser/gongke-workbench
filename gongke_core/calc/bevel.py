"""闭式软齿面直齿锥齿轮传动（轴交角 Σ = 90°）的设计与校核。

方法按濮良贵《机械设计》第八版 §10-8：
- 按齿面接触疲劳强度：d1 ≥ ∛{ 4 K T1 / [φR (1 − 0.5φR)² u] · (ZH ZE / [σH])² }，ZH = 2.5；
- 按齿根弯曲疲劳强度：m ≥ ∛{ 4 K T1 / [φR (1 − 0.5φR)² z1² √(u² + 1)] · YFa YSa / [σF] }，
  YFa、YSa 按当量齿数 zv = z / cos δ 查取；
- 载荷系数 K = KA Kv KHα KHβ：Kv 按平均分度圆处圆周速度、精度降低一级取；KHβ = 1.5 KHβbe，
  KHβbe 为轴承系数（小齿轮悬臂、大齿轮两端支承时取 1.1）。
几何尺寸按大端计算：d = mz，δ1 = arctan(z1/z2)，R = d1/(2 sin δ1)，b = φR R，dm = d(1 − 0.5φR)，
da = d + 2m cos δ，df = d − 2.4m cos δ（ha* = 1，c* = 0.2）。
受力（平均分度圆处）：Ft = 2T1/dm1，Fr1 = Ft tan α cos δ1 = Fa2，Fa1 = Ft tan α sin δ1 = Fr2。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from gongke_core import standards
from gongke_core.calc.gear import (Z_E_STEEL, _allowables, _pick_teeth, dynamic_factor, load_sharing_factor)

Z_H = 2.5  # 标准直齿轮的区域系数


@dataclass
class BevelPairInput:
    name: str
    torque1: float  # 小锥齿轮转矩，N·m
    speed1_rpm: float
    ratio: float
    life_hours: float
    material1: str = "40Cr_QT"
    material2: str = "45_QT"
    grade: int = 8  # GB/T 11365 精度等级
    z1: int = 24
    phi_r: float = 0.3  # 齿宽系数 φR = b/R，常取 0.25～0.35
    alpha_deg: float = 20.0
    k_a: float = 1.0
    k_hbeta_be: float = 1.1  # 轴承系数：小齿轮悬臂、大齿轮两端支承
    s_h: float = 1.0
    s_f: float = 1.4
    min_module: float = 1.5e-3
    min_d1: float = 0.0  # 结构要求的小锥齿轮最小大端分度圆直径（如为使大锥齿轮浸油而加大）
    overrides: dict = field(default_factory=dict)


@dataclass
class BevelCheck:
    k_v: float
    k_alpha: float
    k_hbeta: float
    k_h: float
    k_f: float
    sigma_h: float
    sigma_h_allow: float
    zv: tuple[float, float]
    y_fa: tuple[float, float]
    y_sa: tuple[float, float]
    sigma_f: tuple[float, float]
    sigma_f_allow: tuple[float, float]

    @property
    def ok(self) -> bool:
        return self.sigma_h <= self.sigma_h_allow * (1 + 1e-9) and all(
            s <= a * (1 + 1e-9) for s, a in zip(self.sigma_f, self.sigma_f_allow))


@dataclass
class BevelPair:
    inp: BevelPairInput
    cycles: tuple[float, float]
    k_hn: tuple[float, float]
    k_fn: tuple[float, float]
    sigma_h_allow: float
    sigma_f_allow: tuple[float, float]
    d1_trial: float
    d1_design: float
    m_trial: float
    m_design: float
    m: float  # 大端模数
    z1: int
    z2: int
    b: float  # 齿宽（两轮相同）
    check: BevelCheck
    iterations: int

    @property
    def u(self) -> float:
        return self.z2 / self.z1

    @property
    def alpha(self) -> float:
        return math.radians(self.inp.alpha_deg)

    @property
    def delta1(self) -> float:
        return math.atan2(self.z1, self.z2)

    @property
    def delta2(self) -> float:
        return math.pi / 2 - self.delta1

    @property
    def d1(self) -> float:
        return self.m * self.z1

    @property
    def d2(self) -> float:
        return self.m * self.z2

    @property
    def cone_distance(self) -> float:
        return self.d1 / (2 * math.sin(self.delta1))

    @property
    def dm1(self) -> float:
        return self.d1 * (1 - 0.5 * self.inp.phi_r)

    @property
    def dm2(self) -> float:
        return self.d2 * (1 - 0.5 * self.inp.phi_r)

    @property
    def da1(self) -> float:
        return self.d1 + 2 * self.m * math.cos(self.delta1)

    @property
    def da2(self) -> float:
        return self.d2 + 2 * self.m * math.cos(self.delta2)

    @property
    def df1(self) -> float:
        return self.d1 - 2.4 * self.m * math.cos(self.delta1)

    @property
    def df2(self) -> float:
        return self.d2 - 2.4 * self.m * math.cos(self.delta2)

    @property
    def tangential_force(self) -> float:
        return 2 * self.inp.torque1 / self.dm1

    @property
    def radial_force1(self) -> float:
        return self.tangential_force * math.tan(self.alpha) * math.cos(self.delta1)

    @property
    def axial_force1(self) -> float:
        return self.tangential_force * math.tan(self.alpha) * math.sin(self.delta1)

    @property
    def pitch_velocity(self) -> float:
        """平均分度圆处的圆周速度。"""
        return math.pi * self.dm1 * self.inp.speed1_rpm / 60


def _factor(phi_r: float) -> float:
    return phi_r * (1 - 0.5 * phi_r) ** 2


def _load_factors(inp: BevelPairInput, d1: float, b: float) -> tuple[float, float, float, float]:
    ov = inp.overrides
    dm1 = d1 * (1 - 0.5 * inp.phi_r)
    vm = math.pi * dm1 * inp.speed1_rpm / 60
    k_v = ov.get("k_v", dynamic_factor(vm, min(inp.grade + 1, 12)))
    ft = 2 * inp.torque1 / dm1
    k_al = ov.get("k_alpha", load_sharing_factor(inp.grade, False, inp.k_a * ft / b))
    k_hb = ov.get("k_hbeta", 1.5 * inp.k_hbeta_be)
    return k_v, k_al, k_hb, inp.k_a * k_v * k_al * k_hb


def check_strength(inp: BevelPairInput, z1: int, z2: int, m: float, b: float,
                   sigma_h_allow: float, sigma_f_allow: tuple[float, float]) -> BevelCheck:
    u = z2 / z1
    d1 = m * z1
    k_v, k_al, k_hb, k = _load_factors(inp, d1, b)
    phi = b / (d1 * math.sqrt(u * u + 1) / 2)  # 实际 φR
    t1 = inp.torque1
    sigma_h = Z_H * Z_E_STEEL * math.sqrt(4 * k * t1 / (_factor(phi) * d1**3 * u))
    d1_ = math.atan2(z1, z2)
    zv = (z1 / math.cos(d1_), z2 / math.cos(math.pi / 2 - d1_))
    ff = [standards.form_factors(v) for v in zv]
    ft = 2 * t1 / (d1 * (1 - 0.5 * phi))
    sigma_f = tuple(k * ft * yfa * ysa / (b * m * (1 - 0.5 * phi)) for yfa, ysa in ff)
    return BevelCheck(k_v, k_al, k_hb, k, k, sigma_h, sigma_h_allow, zv,
                      (ff[0][0], ff[1][0]), (ff[0][1], ff[1][1]), sigma_f, sigma_f_allow)


def design(inp: BevelPairInput) -> BevelPair:
    u = inp.ratio
    z1 = inp.z1
    z2 = _pick_teeth(z1, u)
    cycles, khn, kfn, sh_allow, sf_allow = _allowables(inp, u)
    t1, phi = inp.torque1, inp.phi_r
    kt = 1.3

    # 1. 按接触疲劳强度试算 d1t，再按实际载荷系数修正
    d1t = (4 * kt * t1 / (_factor(phi) * u) * (Z_H * Z_E_STEEL / sh_allow) ** 2) ** (1 / 3)
    b_t = phi * d1t * math.sqrt(u * u + 1) / 2
    *_, k_h = _load_factors(inp, d1t, b_t)
    d1 = max(d1t * (k_h / kt) ** (1 / 3), inp.min_d1)

    # 2. 按弯曲疲劳强度试算 mt，再修正
    dl1 = math.atan2(z1, z2)
    ratios = []
    for z, dl, sf in ((z1, dl1, sf_allow[0]), (z2, math.pi / 2 - dl1, sf_allow[1])):
        yfa, ysa = standards.form_factors(z / math.cos(dl))
        ratios.append(yfa * ysa / sf)
    mt = (4 * kt * t1 / (_factor(phi) * z1**2 * math.sqrt(u * u + 1)) * max(ratios)) ** (1 / 3)
    d1f = mt * z1
    *_, k_f = _load_factors(inp, d1f, phi * d1f * math.sqrt(u * u + 1) / 2)
    m_design = mt * (k_f / kt) ** (1 / 3)

    # 3. 取标准模数（GB/T 12368），按 d1 定齿数，校核
    m = next(v for v in standards.bevel_modules() if v >= max(m_design, inp.min_module) - 1e-12)
    z1 = max(math.ceil(d1 / m - 1e-9), 17)
    for it in range(1, 40):
        z2 = _pick_teeth(z1, u)
        r = m * z1 * math.sqrt((z2 / z1) ** 2 + 1) / 2
        b = math.ceil(phi * r / 1e-3 - 1e-9) * 1e-3
        chk = check_strength(inp, z1, z2, m, b, sh_allow, sf_allow)
        if chk.ok:
            break
        z1 += 1
    else:
        raise RuntimeError(f"{inp.name}：迭代未收敛，请检查材料或输入参数")
    return BevelPair(inp, cycles, khn, kfn, sh_allow, sf_allow, d1t, d1, mt, m_design, m, z1, z2, b, chk, it)

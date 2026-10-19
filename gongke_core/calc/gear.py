"""闭式软齿面斜齿圆柱齿轮传动的设计与校核。

方法按濮良贵《机械设计》第八版第 10 章：先按齿面接触疲劳强度求小齿轮分度圆直径，再按齿根弯曲
疲劳强度求法向模数，取标准模数后圆整中心距、反算螺旋角，最后用实际几何尺寸校核两种强度。
教材中靠查图得到的系数（动载系数 Kv、寿命系数 KN）用解析近似，均可通过 ``overrides`` 覆盖。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from gongke_core import standards

Z_E_STEEL = 189.8e3  # 钢对钢的弹性影响系数，√Pa（189.8 √MPa）


# ---------------------------------------------------------------- 基本几何与系数


def transverse_pressure_angle(alpha_n: float, beta: float) -> float:
    """端面压力角 αt = arctan(tan αn / cos β)。"""
    return math.atan(math.tan(alpha_n) / math.cos(beta))


def base_helix_angle(beta: float, alpha_t: float) -> float:
    """基圆螺旋角 βb = arctan(tan β · cos αt)。"""
    return math.atan(math.tan(beta) * math.cos(alpha_t))


def transverse_contact_ratio(z1: int, z2: int, alpha_n: float, beta: float, ha_star: float = 1.0) -> float:
    """端面重合度 εα = [z1(tan αat1 − tan αt) + z2(tan αat2 − tan αt)] / 2π（标准齿轮、标准中心距）。

    与模数无关：分度圆、齿顶圆都与 mn 成正比。
    """
    at = transverse_pressure_angle(alpha_n, beta)
    eps = 0.0
    for z in (z1, z2):
        d = z / math.cos(beta)  # 以 mn = 1 计
        da = d + 2 * ha_star
        aat = math.acos(d * math.cos(at) / da)
        eps += z * (math.tan(aat) - math.tan(at))
    return eps / (2 * math.pi)


def overlap_ratio(phi_d: float, z1: int, beta: float) -> float:
    """纵向重合度 εβ = φd z1 tan β / π。"""
    return phi_d * z1 * math.tan(beta) / math.pi


def zone_factor(alpha_n: float, beta: float) -> float:
    """区域系数 ZH = √(2 cos βb / (cos² αt tan αt))（标准齿轮）。"""
    at = transverse_pressure_angle(alpha_n, beta)
    bb = base_helix_angle(beta, at)
    return math.sqrt(2 * math.cos(bb) / (math.cos(at) ** 2 * math.tan(at)))


def contact_ratio_factor(eps_a: float, eps_b: float) -> float:
    """接触疲劳强度重合度系数 Zε = √((4−εα)/3·(1−εβ) + εβ/εα)，εβ ≥ 1 时 Zε = √(1/εα)。"""
    if eps_b >= 1:
        return math.sqrt(1 / eps_a)
    return math.sqrt((4 - eps_a) / 3 * (1 - eps_b) + eps_b / eps_a)


def helix_factor_contact(beta: float) -> float:
    """螺旋角系数 Zβ = √cos β。"""
    return math.sqrt(math.cos(beta))


def bending_contact_ratio_factor(eps_a: float, beta: float, alpha_n: float) -> float:
    """弯曲疲劳强度重合度系数 Yε = 0.25 + 0.75/εαv，εαv = εα / cos² βb。"""
    bb = base_helix_angle(beta, transverse_pressure_angle(alpha_n, beta))
    return 0.25 + 0.75 / (eps_a / math.cos(bb) ** 2)


def helix_factor_bending(eps_b: float, beta: float) -> float:
    """螺旋角系数 Yβ = 1 − εβ·β/120°（εβ > 1 时按 1 计），且不小于 0.75。"""
    return max(1 - min(eps_b, 1.0) * math.degrees(beta) / 120, 0.75)


def virtual_teeth(z: int, beta: float) -> float:
    """当量齿数 zv = z / cos³ β。"""
    return z / math.cos(beta) ** 3


def dynamic_factor(v: float, grade: int) -> float:
    """动载系数 Kv 的解析近似（教材为查图）。

    采用 AGMA 2001 的形式 Kv = ((A + √(200 v)) / A)^B，B = 0.25(12 − Qv)^(2/3)，A = 50 + 56(1 − B)，
    GB/T 10095 精度等级按 Qv ≈ 16 − 等级 对应。v 为分度圆圆周速度，m/s。
    """
    qv = 16 - grade
    b = 0.25 * (12 - qv) ** (2 / 3)
    a = 50 + 56 * (1 - b)
    return ((a + math.sqrt(200 * v)) / a) ** b


def load_sharing_factor(grade: int, helical: bool, ka_ft_per_b: float) -> float:
    """齿间载荷分配系数 KHα = KFα，按教材表 10-3 软齿面取值（ka_ft_per_b 单位 N/m）。"""
    if helical:
        table = {6: 1.0, 7: 1.1, 8: 1.2, 9: 1.4}
        low = 1.4
    else:
        table = {6: 1.0, 7: 1.0, 8: 1.1, 9: 1.2}
        low = 1.2
    k = table[min(max(grade, 6), 9)]
    if ka_ft_per_b < 100e3:  # < 100 N/mm
        k = max(k, low)
    return k


def face_load_factor_contact(phi_d: float, b: float, grade: int) -> float:
    """齿向载荷分布系数 KHβ，教材表 10-4 软齿面、小齿轮相对支承非对称布置的经验式（b 单位 m）。

    7 级：KHβ = 1.12 + 0.18(1 + 0.6 φd²) φd² + 0.23×10⁻³ b(mm)
    8 级：KHβ = 1.15 + 0.18(1 + 0.6 φd²) φd² + 0.31×10⁻³ b(mm)
    """
    bm = b * 1e3
    base = 0.18 * (1 + 0.6 * phi_d**2) * phi_d**2
    if grade <= 7:
        return 1.12 + base + 0.23e-3 * bm
    return 1.15 + base + 0.31e-3 * bm


def face_load_factor_bending(k_hbeta: float, b: float, h: float) -> float:
    """KFβ = KHβ^N，N = (b/h)² / (1 + b/h + (b/h)²)（ISO 6336-3）。"""
    r = b / h
    n = r * r / (1 + r + r * r)
    return k_hbeta**n


def life_factor_contact(cycles: float) -> float:
    """接触疲劳寿命系数 KHN 的近似（ISO 6336-2，调质钢、允许少量点蚀）。

    10⁵ 次 → 1.6，5×10⁷ 次 → 1.0，10¹⁰ 次 → 0.85，之间按双对数线性。
    """
    if cycles <= 1e5:
        return 1.6
    if cycles <= 5e7:
        return (5e7 / cycles) ** (math.log(1.6) / math.log(5e7 / 1e5))
    return max((5e7 / cycles) ** (math.log(1 / 0.85) / math.log(1e10 / 5e7)), 0.85)


def life_factor_bending(cycles: float) -> float:
    """弯曲疲劳寿命系数 KFN 的近似（ISO 6336-3，调质钢）。

    10⁴ 次 → 2.5，3×10⁶ 次 → 1.0，10¹⁰ 次 → 0.85，之间按双对数线性。
    """
    if cycles <= 1e4:
        return 2.5
    if cycles <= 3e6:
        return (3e6 / cycles) ** (math.log(2.5) / math.log(3e6 / 1e4))
    return max((3e6 / cycles) ** (math.log(1 / 0.85) / math.log(1e10 / 3e6)), 0.85)


# ---------------------------------------------------------------- 设计流程


@dataclass
class GearPairInput:
    name: str
    torque1: float  # 小齿轮转矩，N·m
    speed1_rpm: float
    ratio: float  # 期望齿数比 u
    life_hours: float
    material1: str = "40Cr_QT"
    material2: str = "45_QT"
    grade: int = 8  # GB/T 10095 精度等级
    z1: int = 24
    beta_deg: float = 14.0
    phi_d: float = 1.0
    alpha_n_deg: float = 20.0
    k_a: float = 1.0  # 使用系数
    s_h: float = 1.0
    s_f: float = 1.4
    min_module: float = 1.5e-3
    center_distance_step: float = 5e-3  # 中心距圆整到 5 mm 的倍数
    min_d1: float = 0.0  # 结构要求的小齿轮最小分度圆直径（如齿轮轴需容纳轴承轴肩）
    overrides: dict = field(default_factory=dict)


@dataclass
class StrengthCheck:
    k_v: float
    k_alpha: float
    k_hbeta: float
    k_fbeta: float
    k_h: float
    k_f: float
    z_h: float
    z_eps: float
    z_beta: float
    y_eps: float
    y_beta: float
    eps_alpha: float
    eps_beta: float
    sigma_h: float
    sigma_h_allow: float
    y_fa: tuple[float, float]
    y_sa: tuple[float, float]
    sigma_f: tuple[float, float]
    sigma_f_allow: tuple[float, float]

    @property
    def ok(self) -> bool:
        return self.sigma_h <= self.sigma_h_allow * (1 + 1e-9) and all(
            s <= a * (1 + 1e-9) for s, a in zip(self.sigma_f, self.sigma_f_allow)
        )


@dataclass
class GearPair:
    inp: GearPairInput
    # 许用应力
    cycles: tuple[float, float]
    k_hn: tuple[float, float]
    k_fn: tuple[float, float]
    sigma_h_allow: float
    sigma_f_allow: tuple[float, float]
    # 设计阶段
    d1_trial: float  # 按 Kt = 1.3 试算的 d1t
    d1_design: float  # 修正 K 后的 d1
    mn_trial: float
    mn_design: float
    # 最终几何
    mn: float
    z1: int
    z2: int
    beta: float  # rad
    a: float
    d1: float
    d2: float
    da1: float
    da2: float
    df1: float
    df2: float
    b1: float
    b2: float
    check: StrengthCheck
    iterations: int

    @property
    def u(self) -> float:
        return self.z2 / self.z1

    @property
    def alpha_n(self) -> float:
        return math.radians(self.inp.alpha_n_deg)

    @property
    def tangential_force(self) -> float:
        return 2 * self.inp.torque1 / self.d1

    @property
    def radial_force(self) -> float:
        return self.tangential_force * math.tan(self.alpha_n) / math.cos(self.beta)

    @property
    def axial_force(self) -> float:
        return self.tangential_force * math.tan(self.beta)

    @property
    def pitch_velocity(self) -> float:
        return math.pi * self.d1 * self.inp.speed1_rpm / 60


def _allowables(inp: GearPairInput, u: float):
    m1, m2 = standards.gear_material(inp.material1), standards.gear_material(inp.material2)
    n1 = 60 * inp.speed1_rpm * 1 * inp.life_hours
    n2 = n1 / u
    ov = inp.overrides
    khn = (ov.get("k_hn1", life_factor_contact(n1)), ov.get("k_hn2", life_factor_contact(n2)))
    kfn = (ov.get("k_fn1", life_factor_bending(n1)), ov.get("k_fn2", life_factor_bending(n2)))
    sh = (khn[0] * m1.sigma_hlim / inp.s_h, khn[1] * m2.sigma_hlim / inp.s_h)
    sf = (kfn[0] * m1.sigma_fe / inp.s_f, kfn[1] * m2.sigma_fe / inp.s_f)
    return (n1, n2), khn, kfn, min(sh), sf


def check_strength(inp: GearPairInput, z1: int, z2: int, mn: float, beta: float, b: float,
                   sigma_h_allow: float, sigma_f_allow: tuple[float, float]) -> StrengthCheck:
    """用确定的几何参数校核接触和弯曲强度（b 为工作齿宽，取大齿轮齿宽）。"""
    an = math.radians(inp.alpha_n_deg)
    u = z2 / z1
    d1 = z1 * mn / math.cos(beta)
    t1 = inp.torque1
    ov = inp.overrides
    v = math.pi * d1 * inp.speed1_rpm / 60
    ft = 2 * t1 / d1
    k_v = ov.get("k_v", dynamic_factor(v, inp.grade))
    k_al = ov.get("k_alpha", load_sharing_factor(inp.grade, beta > 0, inp.k_a * ft / b))
    phi = b / d1
    k_hb = ov.get("k_hbeta", face_load_factor_contact(phi, b, inp.grade))
    k_fb = ov.get("k_fbeta", face_load_factor_bending(k_hb, b, 2.25 * mn))
    k_h = inp.k_a * k_v * k_al * k_hb
    k_f = inp.k_a * k_v * k_al * k_fb

    ea = transverse_contact_ratio(z1, z2, an, beta)
    eb = b * math.sin(beta) / (math.pi * mn)
    z_h = zone_factor(an, beta)
    z_e = Z_E_STEEL
    z_eps = contact_ratio_factor(ea, eb)
    z_b = helix_factor_contact(beta)
    sigma_h = z_h * z_e * z_eps * z_b * math.sqrt(2 * k_h * t1 / (b * d1**2) * (u + 1) / u)

    y_eps = bending_contact_ratio_factor(ea, beta, an)
    y_b = helix_factor_bending(eb, beta)
    ff = [standards.form_factors(virtual_teeth(z, beta)) for z in (z1, z2)]
    sigma_f = tuple(2 * k_f * t1 * yfa * ysa * y_eps * y_b / (b * mn * d1) for yfa, ysa in ff)
    return StrengthCheck(
        k_v, k_al, k_hb, k_fb, k_h, k_f, z_h, z_eps, z_b, y_eps, y_b, ea, eb,
        sigma_h, sigma_h_allow, (ff[0][0], ff[1][0]), (ff[0][1], ff[1][1]), sigma_f, sigma_f_allow,
    )


def _ceil_to(x: float, step: float) -> float:
    return round(math.ceil(x / step - 1e-9) * step, 9)


def _pick_teeth(z1: int, u: float) -> int:
    """z2 ≈ u·z1，优先与 z1 互质，以使轮齿磨损均匀。"""
    z2 = round(u * z1)
    for cand in sorted((z2, z2 - 1, z2 + 1), key=lambda z: abs(z / z1 - u)):
        if math.gcd(z1, cand) == 1:
            return cand
    return z2


def design(inp: GearPairInput) -> GearPair:
    an = math.radians(inp.alpha_n_deg)
    beta0 = math.radians(inp.beta_deg)
    u = inp.ratio
    z1, z2 = inp.z1, _pick_teeth(inp.z1, u)
    cycles, khn, kfn, sh_allow, sf_allow = _allowables(inp, u)
    t1, phi = inp.torque1, inp.phi_d

    # 1. 按接触疲劳强度试算 d1t（Kt = 1.3）
    kt = 1.3
    ea = transverse_contact_ratio(z1, z2, an, beta0)
    eb = overlap_ratio(phi, z1, beta0)
    z_term = zone_factor(an, beta0) * Z_E_STEEL * contact_ratio_factor(ea, eb) * helix_factor_contact(beta0)
    d1t = (2 * kt * t1 / phi * (u + 1) / u * (z_term / sh_allow) ** 2) ** (1 / 3)

    # 修正载荷系数
    v = math.pi * d1t * inp.speed1_rpm / 60
    b = phi * d1t
    ft = 2 * t1 / d1t
    ov = inp.overrides
    k_v = ov.get("k_v", dynamic_factor(v, inp.grade))
    k_al = ov.get("k_alpha", load_sharing_factor(inp.grade, True, inp.k_a * ft / b))
    k_hb = ov.get("k_hbeta", face_load_factor_contact(phi, b, inp.grade))
    k_h = inp.k_a * k_v * k_al * k_hb
    d1 = max(d1t * (k_h / kt) ** (1 / 3), inp.min_d1)

    # 2. 按弯曲疲劳强度试算 mnt（Kt = 1.3）
    y_eps = bending_contact_ratio_factor(ea, beta0, an)
    y_b = helix_factor_bending(eb, beta0)
    ratios = []
    for z, sf in zip((z1, z2), sf_allow):
        yfa, ysa = standards.form_factors(virtual_teeth(z, beta0))
        ratios.append(yfa * ysa / sf)
    mnt = (2 * kt * t1 * y_eps * y_b * math.cos(beta0) ** 2 / (phi * z1**2) * max(ratios)) ** (1 / 3)
    d1f = mnt * z1 / math.cos(beta0)
    bf = phi * d1f
    vf = math.pi * d1f * inp.speed1_rpm / 60
    k_vf = ov.get("k_v", dynamic_factor(vf, inp.grade))
    k_alf = ov.get("k_alpha", load_sharing_factor(inp.grade, True, inp.k_a * 2 * t1 / d1f / bf))
    k_hbf = ov.get("k_hbeta", face_load_factor_contact(phi, bf, inp.grade))
    k_fbf = ov.get("k_fbeta", face_load_factor_bending(k_hbf, bf, 2.25 * mnt))
    k_f = inp.k_a * k_vf * k_alf * k_fbf
    mn_design = mnt * (k_f / kt) ** (1 / 3)

    # 3. 取标准模数，按 d1 定齿数，圆整中心距并反算螺旋角
    mn = next(m for m in standards.standard_modules(1) if m >= max(mn_design, inp.min_module) - 1e-12)
    z1 = max(math.ceil(d1 * math.cos(beta0) / mn - 1e-9), 17)
    a_min = None
    for it in range(1, 40):
        z2 = _pick_teeth(z1, u)
        a = _ceil_to((z1 + z2) * mn / (2 * math.cos(beta0)), inp.center_distance_step)
        if a_min is not None:
            a = max(a, a_min)
        beta = math.acos((z1 + z2) * mn / (2 * a))
        if not math.radians(8) <= beta <= math.radians(20):
            # 螺旋角超出 8°–20°：增减齿数使中心距贴近
            z1 += 1 if beta > math.radians(20) else -1
            continue
        d1f = z1 * mn / math.cos(beta)
        b2 = _ceil_to(phi * d1f, 1e-3)
        chk = check_strength(inp, z1, z2, mn, beta, b2, sh_allow, sf_allow)
        if chk.ok:
            break
        # 强度不足：加大中心距（齿数随之增加）
        a_min = a + inp.center_distance_step
        z1 = math.ceil(2 * a_min * math.cos(beta0) / (mn * (1 + u)))
    else:
        raise RuntimeError(f"{inp.name}：迭代未收敛，请检查材料或输入参数")

    d2 = z2 * mn / math.cos(beta)
    return GearPair(
        inp=inp, cycles=cycles, k_hn=khn, k_fn=kfn, sigma_h_allow=sh_allow, sigma_f_allow=sf_allow,
        d1_trial=d1t, d1_design=d1, mn_trial=mnt, mn_design=mn_design,
        mn=mn, z1=z1, z2=z2, beta=beta, a=a, d1=d1f, d2=d2,
        da1=d1f + 2 * mn, da2=d2 + 2 * mn, df1=d1f - 2.5 * mn, df2=d2 - 2.5 * mn,
        b1=round(b2 + 5e-3, 9), b2=b2, check=chk, iterations=it,
    )

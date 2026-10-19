"""普通圆柱蜗杆传动（阿基米德蜗杆 ZA，轴交角 90°，钢蜗杆配青铜蜗轮）的设计与校核。

方法按濮良贵《机械设计》第八版第 11 章：
- 蜗杆头数 z1 按传动比选取：i ≈ 7～13 取 4，14～27 取 2，28～40 取 2 或 1，> 40 取 1；z2 = i z1，宜 28～80；
- 按蜗轮齿面接触疲劳强度设计中心距（式 11-12）：a ≥ ∛[K T2 (ZE Zρ / [σH])²]，
  校核（式 11-11）：σH = ZE Zρ √(K T2 / a³) ≤ [σH]；Zρ 为接触系数，按 d1/a 查图 11-18；
- 锡青铜蜗轮 [σH] = KHN [σH]'，KHN = (10⁷/N)^(1/8)；无锡青铜蜗轮 [σH] 按滑动速度查表（以胶合为主要失效形式）；
- 蜗轮齿根弯曲疲劳强度（式 11-13）：σF = 1.53 K T2 YFa2 Yβ / (d1 d2 m cos γ) ≤ [σF]，Yβ = 1 − γ/140°，
  [σF] = KFN [σF]'，KFN = (10⁶/N)^(1/9)；YFa2 按当量齿数 zv2 = z2/cos³γ 取（本程序借用圆柱齿轮的 YFa 曲线，偏保守）；
- 效率 η = (0.95～0.96) tan γ / tan(γ + φv)，φv 为当量摩擦角，按滑动速度 vs = v1 / cos γ 查表 11-18；
- 受力：Ft1 = 2T1/d1 = Fa2，Fa1 = Ft2 = 2T2/d2，Fr1 = Fr2 = Ft2 tan α。
设计时按 GB/T 10085 的标准中心距和 (m, d1) 搭配逐一试算，用蜗轮变位系数 x2 凑中心距（|x2| ≤ 0.5），
取满足强度、传动比误差最小的最小中心距。
几何：d2 = m z2，a = (d1 + d2 + 2 x2 m)/2，γ = arctan(z1 m / d1)，da1 = d1 + 2m，df1 = d1 − 2.4m，
da2 = m(z2 + 2 + 2x2)，df2 = m(z2 − 2.4 + 2x2)，蜗轮外径 de2 ≤ da2 + 2m（z1 = 1）、+1.5m（z1 = 2～3）、+m（z1 = 4），
蜗轮齿宽 b2 ≤ 0.75 da1（z1 ≤ 3）或 0.67 da1（z1 = 4），蜗杆螺纹部分长度 b1 ≥ (11 + 0.06 z2) m（z1 = 1～2）
或 (12.5 + 0.09 z2) m（z1 = 4），磨削的蜗杆再加长 25 mm（m < 10 mm）。
"""

from __future__ import annotations

import bisect
import math
from dataclasses import dataclass

from gongke_core import standards

ALPHA = math.radians(20.0)


def _table():
    return standards.load("textbook/worm_gearing.yaml")


def _interp(rows: list, x: float, col: int = 1) -> float:
    xs = [r[0] for r in rows]
    if x <= xs[0]:
        return rows[0][col]
    if x >= xs[-1]:
        return rows[-1][col]
    i = bisect.bisect_left(xs, x)
    (x0, y0), (x1, y1) = (rows[i - 1][0], rows[i - 1][col]), (rows[i][0], rows[i][col])
    return y0 + (y1 - y0) * (x - x0) / (x1 - x0)


def z_rho(d1_over_a: float) -> float:
    """接触系数 Zρ（图 11-18 曲线Ⅰ的读数，线性插值）。"""
    return _interp(_table()["z_rho"], d1_over_a)


def friction_angle(vs: float, tin_bronze: bool = True) -> float:
    """当量摩擦角 φv = arctan fv（rad），fv 按滑动速度 vs（m/s）插值。"""
    return math.atan(_interp(_table()["friction"], vs, 1 if tin_bronze else 2))


def worm_starts(ratio: float) -> int:
    """蜗杆头数 z1。"""
    if ratio <= 13.5:
        return 4
    if ratio <= 30:
        return 2
    return 1


@dataclass(frozen=True)
class WheelMaterial:
    key: str
    name: str
    casting: str
    sigma_h0: tuple[float | None, float | None]  # [σH]'（蜗杆 ≤ 350HB, > 45HRC），Pa
    sigma_f0: tuple[float, float]  # [σF]'（单侧、双侧受载），Pa
    tin: bool


def wheel_material(key: str) -> WheelMaterial:
    r = _table()["wheel_materials"].get(key)
    if r is None:
        raise KeyError(f"未知蜗轮材料 {key}")
    mpa = lambda v: None if v is None else v * 1e6  # noqa: E731
    return WheelMaterial(key, r[0], r[1], (mpa(r[2]), mpa(r[3])), (r[4] * 1e6, r[5] * 1e6), bool(r[6]))


def life_factor_contact(cycles: float) -> float:
    n = min(max(cycles, 2.6e5), 25e7)
    return (1e7 / n) ** (1 / 8)


def life_factor_bending(cycles: float) -> float:
    n = min(max(cycles, 1e5), 25e7)
    return (1e6 / n) ** (1 / 9)


@dataclass
class WormPairInput:
    name: str
    torque1: float  # 蜗杆转矩，N·m
    speed1_rpm: float
    ratio: float
    life_hours: float
    wheel_material: str = "ZCuSn10P1_metal"
    worm_material: str = "45 钢，齿面淬火 45～55HRC"
    worm_hardened: bool = True
    k_a: float = 1.0  # 使用系数（载荷平稳）
    k_beta: float = 1.0  # 齿向载荷分布系数（载荷平稳时取 1）
    grade: int = 8  # GB/T 10089 精度等级
    two_sided: bool = False  # 蜗轮齿双侧受载（正反转）
    z1: int | None = None
    max_ratio_error: float = 0.04
    min_a: float = 0.0
    min_d1: float = 0.0  # 结构要求的蜗杆最小分度圆直径（如为满足蜗杆刚度而加大）


@dataclass
class WormCheck:
    k_v: float
    k: float
    z_rho: float
    sigma_h: float
    sigma_h_allow: float
    zv2: float
    y_fa2: float
    y_beta: float
    sigma_f: float
    sigma_f_allow: float

    @property
    def ok(self) -> bool:
        return self.sigma_h <= self.sigma_h_allow * (1 + 1e-9) and self.sigma_f <= self.sigma_f_allow * (1 + 1e-9)


@dataclass
class WormPair:
    inp: WormPairInput
    material: WheelMaterial
    cycles: float  # 蜗轮应力循环次数 N = 60 j n2 Lh
    a_required: float  # 按估算 Zρ、η 求得的最小中心距
    a: float
    m: float
    d1: float
    z1: int
    z2: int
    x2: float
    check: WormCheck
    eta_mesh: float  # 啮合效率 tan γ / tan(γ + φv)
    eta: float  # 含搅油损失的蜗杆传动效率

    # ---------------- 几何
    @property
    def u(self) -> float:
        return self.z2 / self.z1

    @property
    def q(self) -> float:
        return self.d1 / self.m

    @property
    def gamma(self) -> float:
        return math.atan(self.z1 * self.m / self.d1)

    @property
    def d2(self) -> float:
        return self.m * self.z2

    @property
    def da1(self) -> float:
        return self.d1 + 2 * self.m

    @property
    def df1(self) -> float:
        return self.d1 - 2.4 * self.m

    @property
    def da2(self) -> float:
        return self.m * (self.z2 + 2 + 2 * self.x2)

    @property
    def df2(self) -> float:
        return self.m * (self.z2 - 2.4 + 2 * self.x2)

    @property
    def de2(self) -> float:
        """蜗轮外径（取上限并圆整到整毫米）。"""
        k = 2.0 if self.z1 == 1 else 1.5 if self.z1 <= 3 else 1.0
        return math.floor((self.da2 + k * self.m) * 1e3 + 1e-9) * 1e-3

    @property
    def b2(self) -> float:
        """蜗轮齿宽（取上限并向下圆整到整毫米）。"""
        k = 0.75 if self.z1 <= 3 else 0.67
        return math.floor(k * self.da1 * 1e3 + 1e-9) * 1e-3

    @property
    def b1(self) -> float:
        """蜗杆螺纹部分长度（磨削蜗杆加长量计入，向上圆整到 5 mm）。"""
        base = (11 + 0.06 * self.z2) * self.m if self.z1 <= 2 else (12.5 + 0.09 * self.z2) * self.m
        extra = 25e-3 if self.m < 10e-3 else 35e-3
        return math.ceil((base + extra) / 5e-3 - 1e-9) * 5e-3

    @property
    def throat_radius(self) -> float:
        """蜗轮齿顶圆弧半径 rg2 = a − da2/2。"""
        return self.a - self.da2 / 2

    # ---------------- 运动与受力
    @property
    def speed2_rpm(self) -> float:
        return self.inp.speed1_rpm / self.u

    @property
    def worm_velocity(self) -> float:
        return math.pi * self.d1 * self.inp.speed1_rpm / 60

    @property
    def sliding_velocity(self) -> float:
        return self.worm_velocity / math.cos(self.gamma)

    @property
    def wheel_velocity(self) -> float:
        return math.pi * self.d2 * self.speed2_rpm / 60

    @property
    def torque2(self) -> float:
        return self.inp.torque1 * self.u * self.eta

    @property
    def tangential_force1(self) -> float:
        return 2 * self.inp.torque1 / self.d1

    @property
    def tangential_force2(self) -> float:
        return 2 * self.torque2 / self.d2

    @property
    def radial_force(self) -> float:
        return self.tangential_force2 * math.tan(ALPHA)

    @property
    def axial_force1(self) -> float:
        return self.tangential_force2

    @property
    def axial_force2(self) -> float:
        return self.tangential_force1


def _efficiency(z1: int, m: float, d1: float, n1: float, tin: bool) -> tuple[float, float, float]:
    """返回 (啮合效率, 总效率, φv)。总效率计入搅油损失 0.96。"""
    gamma = math.atan(z1 * m / d1)
    vs = math.pi * d1 * n1 / 60 / math.cos(gamma)
    phi = friction_angle(vs, tin)
    eta1 = math.tan(gamma) / math.tan(gamma + phi)
    return eta1, 0.96 * eta1, phi


def _allowable_h(mat: WheelMaterial, hardened: bool, cycles: float, vs: float) -> float:
    if mat.tin:
        return life_factor_contact(cycles) * mat.sigma_h0[1 if hardened else 0]
    return _interp(_table()["al_bronze_sigma_h"], vs) * 1e6


def check_strength(inp: WormPairInput, mat: WheelMaterial, cycles: float, a: float, m: float, d1: float,
                   z1: int, z2: int, torque2: float) -> WormCheck:
    gamma = math.atan(z1 * m / d1)
    d2 = m * z2
    v2 = math.pi * d2 * inp.speed1_rpm / (z2 / z1) / 60
    k_v = 1.05 if v2 <= 3 else 1.15
    k = inp.k_a * inp.k_beta * k_v
    zr = z_rho(d1 / a)
    z_e = _table()["z_e_mpa_sqrt"] * 1e3  # √Pa
    sigma_h = z_e * zr * math.sqrt(k * torque2 / a**3)
    vs = math.pi * d1 * inp.speed1_rpm / 60 / math.cos(gamma)
    sigma_h_allow = _allowable_h(mat, inp.worm_hardened, cycles, vs)
    zv2 = z2 / math.cos(gamma) ** 3
    y_fa2 = standards.form_factors(zv2)[0]
    y_beta = 1 - math.degrees(gamma) / 140
    sigma_f = 1.53 * k * torque2 * y_fa2 * y_beta / (d1 * d2 * m * math.cos(gamma))
    sigma_f_allow = life_factor_bending(cycles) * mat.sigma_f0[1 if inp.two_sided else 0]
    return WormCheck(k_v, k, zr, sigma_h, sigma_h_allow, zv2, y_fa2, y_beta, sigma_f, sigma_f_allow)


def design(inp: WormPairInput) -> WormPair:
    mat = wheel_material(inp.wheel_material)
    z1 = inp.z1 or worm_starts(inp.ratio)
    n2 = inp.speed1_rpm / inp.ratio
    cycles = 60 * n2 * inp.life_hours
    # 初估：η 按头数估取，Zρ 按 d1/a = 0.35 取 2.9，[σH] 按 vs ≈ 3 m/s（无锡青铜）
    eta0 = {1: 0.72, 2: 0.80, 4: 0.88}.get(z1, 0.80)
    t2 = inp.torque1 * inp.ratio * eta0
    k0 = inp.k_a * inp.k_beta * 1.05
    sh0 = _allowable_h(mat, inp.worm_hardened, cycles, 3.0)
    z_e = _table()["z_e_mpa_sqrt"] * 1e3
    a_req = (k0 * t2 * (z_e * 2.9 / sh0) ** 2) ** (1 / 3)

    best = None
    for a in standards.worm_center_distances(include_series_2=True):
        if a < max(0.8 * a_req, inp.min_a) - 1e-12:
            continue
        cands = []
        for m, d1 in standards.worm_module_d1():
            if not 0.25 <= d1 / a <= 0.55 or d1 < inp.min_d1 - 1e-12:
                continue
            base = (2 * a - d1) / m
            for z2 in {math.floor(base), math.ceil(base), round(base) - 1, round(base) + 1}:
                if z2 < 28 or z2 > 90:
                    continue
                x2 = (2 * a - d1 - m * z2) / (2 * m)
                if abs(x2) > 0.5 + 1e-9:
                    continue
                err = abs(z2 / z1 - inp.ratio) / inp.ratio
                if err > inp.max_ratio_error:
                    continue
                eta1, eta, _ = _efficiency(z1, m, d1, inp.speed1_rpm, mat.tin)
                torque2 = inp.torque1 * (z2 / z1) * eta
                c = check_strength(inp, mat, cycles, a, m, d1, z1, z2, torque2)
                if not c.ok:
                    continue
                # 传动比误差小优先，其次变位量小、直径系数 q 适中（8～12）
                q = d1 / m
                score = err + 0.01 * abs(x2) + 0.002 * max(0.0, abs(q - 10) - 2)
                cands.append((score, m, d1, z2, x2, c, eta1, eta))
        if cands:
            best = (a, min(cands, key=lambda t: t[0]))
            break
    if best is None:
        raise standards.SelectionError(f"{inp.name}：标准中心距 ≤ 500 mm 内没有满足强度和传动比要求的蜗杆传动")
    a, (_, m, d1, z2, x2, c, eta1, eta) = best
    return WormPair(inp, mat, cycles, a_req, a, m, d1, z1, z2, x2, c, eta1, eta)


# ---------------------------------------------------------------- 热平衡、蜗杆刚度

AMBIENT = 20.0
OIL_LIMIT = 80.0  # 油温许用值 70～80 ℃，取上限


def housing_area(a: float) -> float:
    """箱体有效散热面积估算 S ≈ 9×10⁻⁵ a^1.88（m²，a 以 mm 计），课程设计指导书经验式。"""
    return 9e-5 * (a * 1e3) ** 1.88


@dataclass
class ThermalCheck:
    power_in: float  # W
    eta: float
    heat: float  # W，Φ = 1000 P (1 − η)
    area: float  # m²
    alpha_d: float  # 散热系数 W/(m²·℃)
    t_oil: float  # ℃

    @property
    def ok(self) -> bool:
        return self.t_oil <= OIL_LIMIT


def thermal(power_in: float, eta: float, a: float, alpha_d: float = 14.0) -> ThermalCheck:
    """热平衡（式 11-22）：t0 = ta + 1000 P (1 − η) / (αd S)，αd 取 10～17（通风良好取大值）。"""
    heat = power_in * (1 - eta)
    area = housing_area(a)
    return ThermalCheck(power_in, eta, heat, area, alpha_d, AMBIENT + heat / (alpha_d * area))


@dataclass
class WormStiffness:
    span: float
    deflection: float
    allowable: float

    @property
    def ok(self) -> bool:
        return self.deflection <= self.allowable


def worm_stiffness(pair: WormPair, span: float, e_mod: float = 206e9) -> WormStiffness:
    """蜗杆刚度：把蜗杆看作以齿根圆直径为直径的简支梁，y = √(Ft1² + Fr1²) L³ / (48 E I) ≤ [y] = d1/1000。"""
    i_sec = math.pi * pair.df1**4 / 64
    f = math.hypot(pair.tangential_force1, pair.radial_force)
    y = f * span**3 / (48 * e_mod * i_sec)
    return WormStiffness(span, y, pair.d1 / 1000)

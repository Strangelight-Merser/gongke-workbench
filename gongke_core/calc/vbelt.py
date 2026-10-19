"""普通 V 带传动设计。

按濮良贵《机械设计》（第八版）§8-4 的设计步骤：
1. 计算功率 Pca = KA P；
2. 选带型和小带轮基准直径 dd1，验算带速 v = π dd1 n1 / 60000（5～25 m/s）；
3. 大带轮 dd2 = i dd1，圆整为基准直径系列；
4. 初定中心距 0.7(dd1 + dd2) ≤ a0 ≤ 2(dd1 + dd2)，基准长度 Ld0 = 2a0 + π(dd1 + dd2)/2 + (dd2 − dd1)²/(4a0)，
   取标准 Ld，实际中心距 a ≈ a0 + (Ld − Ld0)/2；
5. 小带轮包角 α1 = 180° − (dd2 − dd1) 57.3°/a ≥ 120°；
6. 根数 z = Pca / [(P0 + ΔP0) Kα KL]；
7. 单根带初拉力 (F0)min = 500 (2.5 − Kα) Pca / (Kα z v) + q v²，压轴力 (Fp)min = 2 z (F0)min sin(α1/2)。

教材中选带型靠查图 8-11。这里改为在 A、B 两种带型中逐个试选小带轮直径，取满足 z ≤ 4
（不行再放宽到 5）的最小带轮直径，同时要求小带轮轮缘内径能容下电动机轴的轮毂。
P0 查表并按转速线性插值；ΔP0、Kα 用公式。
"""

from __future__ import annotations

import bisect
import math
from dataclasses import dataclass

from gongke_core import standards

MM = 1e-3
_DATA = "standards/GB-T_13575.1-2008_V_belts.yaml"


def service_factor(hours_per_day: float) -> float:
    """工况系数 KA（表 8-8，载荷变动小的带式输送机，空、轻载启动的交流电动机）。"""
    if hours_per_day <= 10:
        return 1.1
    if hours_per_day <= 16:
        return 1.2
    return 1.3


def wrap_factor(alpha_deg: float) -> float:
    """包角系数 Kα = 1.25 (1 − 5^(−α/180°))，与表 8-5 的数值相差在 0.01 以内。"""
    return 1.25 * (1 - 5 ** (-alpha_deg / 180))


def _data() -> dict:
    return standards.load(_DATA)


def sections() -> list[str]:
    return list(_data()["sections"])


def ratio_factor(i: float) -> float:
    rows = _data()["ratio_factor"]
    i = max(i, 1 / i)
    k = 1.0
    for lo, v in rows:
        if i >= lo:
            k = v
    return k


def power_increment(section: str, n1: float, i: float) -> float:
    """额定功率增量 ΔP0 = Kb n1 (1 − 1/Ki)，kW。"""
    kb = _data()["sections"][section]["Kb"]
    return kb * n1 * (1 - 1 / ratio_factor(i))


def rated_power(section: str, dd1: float, n1: float) -> float:
    """单根 V 带的基本额定功率 P0（kW），dd1 单位 m。dd1 需在表中，n1 线性插值（超出范围时取端点外推）。"""
    tab = _data()["rated_power"][section]
    key = round(dd1 / MM)
    row = tab["dd1"].get(key)
    if row is None:
        raise standards.SelectionError(f"{section} 型带的 P0 表中没有 dd1 = {key} mm")
    ns = tab["n1"]
    j = min(max(bisect.bisect_left(ns, n1), 1), len(ns) - 1)
    n_lo, n_hi = ns[j - 1], ns[j]
    return row[j - 1] + (row[j] - row[j - 1]) * (n1 - n_lo) / (n_hi - n_lo)


def length_factor(section: str, ld: float) -> float | None:
    col = sections().index(section) + 1
    for row in _data()["datum_lengths"]:
        if abs(row[0] * MM - ld) < 1e-9:
            return row[col]
    return None


def datum_lengths(section: str) -> list[float]:
    col = sections().index(section) + 1
    return [r[0] * MM for r in _data()["datum_lengths"] if r[col] is not None]


def std_diameter(d: float) -> float:
    """圆整为带轮基准直径系列中最接近的值。"""
    ds = [v * MM for v in _data()["datum_diameters_mm"]]
    return min(ds, key=lambda v: abs(v - d))


@dataclass(frozen=True)
class Section:
    name: str
    bp: float
    b: float
    h: float
    q: float  # kg/m
    dd_min: float
    ha: float
    hf: float
    e: float
    f: float
    delta: float
    phi34_max: float

    def groove_angle(self, dd: float) -> float:
        return 34.0 if dd <= self.phi34_max + 1e-9 else 38.0

    def pulley_width(self, z: int) -> float:
        """带轮轮缘宽度 B = (z − 1) e + 2f。"""
        return (z - 1) * self.e + 2 * self.f


def section(name: str) -> Section:
    s = _data()["sections"][name]
    g = _data()["grooves"][name]
    return Section(name, s["bp"] * MM, s["b"] * MM, s["h"] * MM, s["q"], s["dd_min"] * MM,
                   g["ha"] * MM, g["hf"] * MM, g["e"] * MM, g["f"] * MM, g["delta"] * MM, g["phi34_max"] * MM)


@dataclass
class BeltInput:
    power: float  # 传递功率 P，W（电动机所需功率）
    n1: float  # 小带轮转速 r/min
    ratio: float  # 要求的传动比
    service_factor: float = 1.2
    motor_shaft_d: float | None = None  # 小带轮装在电动机轴上，用于检查轮毂
    section: str | None = None  # 指定带型（不指定时自动选择）
    dd1: float | None = None  # 指定小带轮直径
    a0: float | None = None  # 指定初定中心距


@dataclass
class BeltDrive:
    inp: BeltInput
    sec: Section
    p_ca: float  # W
    dd1: float
    dd2: float
    v: float
    a0: float
    ld0: float
    ld: float
    a: float
    a_range: tuple[float, float]
    alpha1: float  # 度
    p0: float  # kW
    dp0: float  # kW
    k_alpha: float
    k_l: float
    z: int
    f0: float  # 单根带的最小初拉力 N
    fp: float  # 最小压轴力 N

    @property
    def ratio(self) -> float:
        """实际传动比（不计弹性滑动）。"""
        return self.dd2 / self.dd1

    @property
    def width(self) -> float:
        return self.sec.pulley_width(self.z)

    @property
    def z_exact(self) -> float:
        return self.p_ca / 1e3 / ((self.p0 + self.dp0) * self.k_alpha * self.k_l)


def _hub_fits(sec: Section, dd1: float, shaft_d: float | None) -> bool:
    """小带轮装在电动机轴上：轮缘内径 dd1 − 2(hf + δ) 应不小于轮毂外径 ≈ 1.8 d。"""
    if shaft_d is None:
        return True
    return dd1 - 2 * (sec.hf + sec.delta) >= 1.8 * shaft_d - 1e-9


def _layout(inp: BeltInput, sec: Section, dd1: float, p_ca: float) -> BeltDrive:
    n1 = inp.n1
    v = math.pi * dd1 * n1 / 60
    dd2 = std_diameter(inp.ratio * dd1)
    a0 = inp.a0 or min(max(1.2 * (dd1 + dd2), 0.7 * (dd1 + dd2)), 2 * (dd1 + dd2))
    ld0 = 2 * a0 + math.pi / 2 * (dd1 + dd2) + (dd2 - dd1) ** 2 / (4 * a0)
    lds = datum_lengths(sec.name)
    ld = min(lds, key=lambda x: abs(x - ld0))
    a = a0 + (ld - ld0) / 2
    alpha = 180 - (dd2 - dd1) * 57.3 / a
    p0 = rated_power(sec.name, dd1, n1)
    dp0 = power_increment(sec.name, n1, dd2 / dd1)
    ka = wrap_factor(alpha)
    kl = length_factor(sec.name, ld)
    z = max(1, math.ceil(p_ca / 1e3 / ((p0 + dp0) * ka * kl) - 1e-9))
    f0 = 500 * (2.5 - ka) * p_ca / 1e3 / (ka * z * v) + sec.q * v**2
    fp = 2 * z * f0 * math.sin(math.radians(alpha) / 2)
    return BeltDrive(inp, sec, p_ca, dd1, dd2, v, a0, ld0, ld, a, (a - 0.015 * ld, a + 0.03 * ld), alpha,
                     p0, dp0, ka, kl, z, f0, fp)


def design(inp: BeltInput) -> BeltDrive:
    p_ca = inp.service_factor * inp.power
    names = [inp.section] if inp.section else sections()
    for z_max in (4, 5):
        cands = []
        for name in names:
            sec = section(name)
            table = sorted(k * MM for k in _data()["rated_power"][name]["dd1"])
            for dd1 in ([inp.dd1] if inp.dd1 else table):
                v = math.pi * dd1 * inp.n1 / 60
                if dd1 < sec.dd_min - 1e-9 or v > 25 or not _hub_fits(sec, dd1, inp.motor_shaft_d):
                    continue
                bd = _layout(inp, sec, dd1, p_ca)
                if bd.z <= z_max and bd.alpha1 >= 120:
                    cands.append(bd)
                    break
        if cands:
            return min(cands, key=lambda b: (b.dd1, b.z))
    raise standards.SelectionError(
        f"计算功率 {p_ca / 1e3:.1f} kW、n1 = {inp.n1:.0f} r/min：A、B 型 V 带在 5 根以内都传不了（超出本程序的数据范围），"
        "可减小 V 带传动比或改用联轴器方案")

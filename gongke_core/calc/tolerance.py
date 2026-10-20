"""零件图用到的公差：标准公差和极限偏差、齿轮精度（单个齿距、齿距累积、齿廓、螺旋线、径向跳动）、
齿厚和公法线长度偏差、齿轮副中心距极限偏差、轴线平行度、轴承配合面的几何公差。

长度参数用 SI（m），返回值也用 m。
"""

from __future__ import annotations

import bisect
import math
import re
from dataclasses import dataclass

from gongke_core import standards

UM = 1e-6
MM = 1e-3


def it(grade: int, size: float) -> float:
    """标准公差 ITn（GB/T 1800.1-2020），size 为公称尺寸（m）。"""
    data = standards.load("standards/GB-T_1800.1-2020_IT_grades.yaml")
    uppers = data["size_upper"]
    i = bisect.bisect_left(uppers, size / MM - 1e-9)
    if i >= len(uppers):
        raise ValueError(f"公称尺寸 {size / MM:g} mm 超出表格范围（≤ 500 mm）")
    return data["it"][grade][i] * UM


def center_distance_fa(grade: int, a: float) -> float:
    """齿轮副中心距极限偏差 ±fa（GB/T 10095-1988 的取法：5～6 级 IT7/2，7～8 级 IT8/2，9～10 级 IT9/2）。

    现行 GB/T 10095 不再规定 fa，课程设计教材仍按此取值。"""
    g = {5: 7, 6: 7, 7: 8, 8: 8, 9: 9, 10: 9}.get(grade)
    if g is None:
        raise ValueError(f"不支持的精度等级 {grade}")
    return it(g, a) / 2


_D_BOUNDS = [5, 20, 50, 125, 280, 560, 1000, 1600]  # mm
_B_BOUNDS = [4, 10, 20, 40, 80, 160, 250, 400]  # mm


def _geo_mean(v_mm: float, bounds: list[float]) -> float:
    i = min(max(bisect.bisect_left(bounds, v_mm - 1e-9), 1), len(bounds) - 1)
    return math.sqrt(bounds[i - 1] * bounds[i])


def _round_iso(v_um: float) -> float:
    """ISO 1328-1 的圆整：大于 10 μm 圆整到整数，5～10 μm 圆整到 0.5，小于 5 μm 圆整到 0.1。"""
    if v_um > 10:
        return float(round(v_um))
    if v_um >= 5:
        return round(v_um * 2) / 2
    return round(v_um, 1)


def helix_total_Fbeta(grade: int, d: float, b: float) -> float:
    """螺旋线总偏差 Fβ（GB/T 10095.1-2008）：Fβ = (0.1√d + 0.63√b + 4.2)·2^((Q−5)/2) μm，
    d、b 取所在分段界限的几何平均值（mm）。"""
    dm, bm = _geo_mean(d / MM, _D_BOUNDS), _geo_mean(b / MM, _B_BOUNDS)
    v = (0.1 * math.sqrt(dm) + 0.63 * math.sqrt(bm) + 4.2) * 2 ** ((grade - 5) / 2)
    return _round_iso(v) * UM


def axis_parallelism(L: float, b: float, Fbeta: float) -> tuple[float, float]:
    """轴线平行度推荐值（GB/Z 18620.3-2008）：垂直平面 fΣβ = 0.5(L/b)Fβ，轴线平面 fΣδ = 2fΣβ。
    L 为轴承跨距，b 为齿宽。返回 (fΣδ, fΣβ)。"""
    f_beta = 0.5 * (L / b) * Fbeta
    return 2 * f_beta, f_beta


# 滚动轴承外壳孔的圆柱度（GB/T 275-2015，普通级轴承），按孔径分段上限（mm）：公差（μm）
_HOUSING_CYL = [(30, 6), (50, 7), (80, 8), (120, 10), (180, 12), (250, 14), (315, 16), (400, 18), (500, 20)]


def housing_bore_cylindricity(D: float) -> float:
    for lim, t in _HOUSING_CYL:
        if D / MM <= lim + 1e-9:
            return t * UM
    raise ValueError(f"孔径 {D / MM:g} mm 超出表格范围")


# ---------------------------------------------------------------- 极限偏差


def _fd(letter: str, size: float) -> float:
    """轴的基本偏差（μm），letter 为 d、f（es）或 k、r（ei）。"""
    data = standards.load("standards/GB-T_1800.1-2020_fundamental_deviations.yaml")[letter]
    i = bisect.bisect_left(data["upper"], size / MM - 1e-9)
    if i >= len(data["upper"]):
        raise ValueError(f"公称尺寸 {size / MM:g} mm 超出表格范围（≤ 500 mm）")
    return float(data["value"][i])


def deviations(code: str, size: float) -> tuple[float, float]:
    """公差带代号（如 k6、r6、H7、N9、JS9、d11、D11）的 (上极限偏差, 下极限偏差)，m。

    规则（GB/T 1800.1-2020）：h/H 的基本偏差为 0；js/JS 为 ±IT/2；
    N 在 IT9 及更粗时 ES = 0；D 的 EI 等于 d 的 es 取反。
    """
    m = re.fullmatch(r"([A-Za-z]{1,2})(\d+)", code)
    if m is None:
        raise ValueError(f"无法识别的公差带代号 {code}")
    letter, grade = m.group(1), int(m.group(2))
    t = it(grade, size) / UM
    if letter in ("h",):
        up = 0.0
        lo = -t
    elif letter == "H":
        up, lo = t, 0.0
    elif letter in ("js", "JS"):
        up, lo = t / 2, -t / 2
    elif letter in ("d", "f"):
        up = _fd(letter, size)
        lo = up - t
    elif letter == "D":
        lo = -_fd("d", size)
        up = lo + t
    elif letter in ("k", "r"):
        if letter == "k" and not 4 <= grade <= 7:
            raise ValueError("k 只录入了 IT4～IT7 的基本偏差")
        lo = _fd(letter, size)
        up = lo + t
    elif letter == "N" and grade >= 9:
        up, lo = 0.0, -t
    else:
        raise ValueError(f"未录入公差带 {code} 的基本偏差")
    return up * UM, lo * UM


def fmt_dev(v: float) -> str:
    """极限偏差的图样写法（mm）：+0.018、−0.036、0。"""
    um = round(v / UM)
    if um == 0:
        return "0"
    return f"{'+' if um > 0 else '-'}{abs(um) / 1000:.3f}"


# ---------------------------------------------------------------- 齿轮精度（GB/T 10095.1/.2-2008）

_M_BOUNDS = [0.5, 2, 3.5, 6, 10, 16, 25, 40, 70]  # mm


def _gear_value(v5_um: float, grade: int) -> float:
    return _round_iso(v5_um * 2 ** ((grade - 5) / 2)) * UM


def single_pitch_fpt(grade: int, d: float, mn: float) -> float:
    """单个齿距偏差 ±fpt：5 级 fpt = 0.3(m + 0.4√d) + 4 μm，其余级按 √2 递推（d、m 取分段几何平均值）。"""
    dm, mm_ = _geo_mean(d / MM, _D_BOUNDS), _geo_mean(mn / MM, _M_BOUNDS)
    return _gear_value(0.3 * (mm_ + 0.4 * math.sqrt(dm)) + 4, grade)


def _fp5(d: float, mn: float) -> float:
    dm, mm_ = _geo_mean(d / MM, _D_BOUNDS), _geo_mean(mn / MM, _M_BOUNDS)
    return 0.3 * mm_ + 1.25 * math.sqrt(dm) + 7


def cumulative_pitch_Fp(grade: int, d: float, mn: float) -> float:
    """齿距累积总偏差 Fp：5 级 Fp = 0.3m + 1.25√d + 7 μm。"""
    return _gear_value(_fp5(d, mn), grade)


def profile_total_Falpha(grade: int, d: float, mn: float) -> float:
    """齿廓总偏差 Fα：5 级 Fα = 3.2√m + 0.22√d + 0.7 μm。"""
    dm, mm_ = _geo_mean(d / MM, _D_BOUNDS), _geo_mean(mn / MM, _M_BOUNDS)
    return _gear_value(3.2 * math.sqrt(mm_) + 0.22 * math.sqrt(dm) + 0.7, grade)


def radial_runout_Fr(grade: int, d: float, mn: float) -> float:
    """径向跳动公差 Fr（GB/T 10095.2-2008）：Fr = 0.8Fp（5 级值，未圆整）再按级递推。"""
    return _gear_value(0.8 * _fp5(d, mn), grade)


# 切齿径向进刀公差 br（课程设计手册齿厚公差算法）：精度等级 → (IT 等级, 倍数)
_BR = {4: (7, 1.26), 5: (8, 1.0), 6: (8, 1.26), 7: (9, 1.0), 8: (9, 1.26), 9: (10, 1.0), 10: (10, 1.26)}


def min_backlash(a: float, mn: float) -> float:
    """最小法向侧隙 jbn,min = 2/3(0.06 + 0.0005a + 0.03mn) mm（GB/Z 18620.2-2008，a、mn 以 mm 计），返回 m。"""
    return 2 / 3 * (0.06 + 0.0005 * a / MM + 0.03 * mn / MM) * MM


@dataclass
class ThicknessDeviation:
    jbn_min: float
    Esns: float  # 齿厚上偏差
    Esni: float  # 齿厚下偏差
    Ebns: float  # 公法线长度上偏差 = Esns cos αn
    Ebni: float  # 公法线长度下偏差


def thickness_deviation(grade: int, a: float, mn: float, alpha_n: float, d1: float, d2: float, d: float,
                        b: float, span: float) -> ThicknessDeviation:
    """齿厚和公法线长度极限偏差（课程设计手册的算法，两轮齿厚上偏差取相同值）。

    Esns = −[fa tan αn + (jbn,min + Jn) / (2 cos αn)]，Jn = √(0.88(fpb1² + fpb2²) + [2 + 0.34(L/b)²]Fβ²)，fpb ≈ fpt cos αn；
    Tsn = 2 tan αn √(Fr² + br²)，Esni = Esns − Tsn；公法线长度偏差 Ebn = Esn cos αn。
    d 为本齿轮分度圆直径，d1、d2 为两轮分度圆直径，span 为轴承跨距 L。
    """
    fa = center_distance_fa(grade, a)
    jmin = min_backlash(a, mn)
    fpb1 = single_pitch_fpt(grade, d1, mn) * math.cos(alpha_n)
    fpb2 = single_pitch_fpt(grade, d2, mn) * math.cos(alpha_n)
    Fb = helix_total_Fbeta(grade, max(d1, d2), b)
    Jn = math.sqrt(0.88 * (fpb1**2 + fpb2**2) + (2 + 0.34 * (span / b) ** 2) * Fb**2)
    esns = -(fa * math.tan(alpha_n) + (jmin + Jn) / (2 * math.cos(alpha_n)))
    g, k = _BR[grade]
    br = k * it(g, d)
    tsn = 2 * math.tan(alpha_n) * math.hypot(radial_runout_Fr(grade, d, mn), br)
    esni = esns - tsn
    c = math.cos(alpha_n)
    return ThicknessDeviation(jmin, esns, esni, esns * c, esni * c)


# ---------------------------------------------------------------- 轴颈、轴肩（GB/T 275-2015，普通级轴承）

_JOURNAL_CYL = [(10, 2.5), (18, 3), (30, 4), (50, 4), (80, 5), (120, 6), (180, 8), (250, 10)]
_SHOULDER_RUNOUT = [(10, 6), (18, 8), (30, 10), (50, 12), (80, 15), (120, 15), (180, 20), (250, 20)]


def _by_size(table, size: float) -> float:
    for lim, t in table:
        if size / MM <= lim + 1e-9:
            return t * UM
    raise ValueError(f"尺寸 {size / MM:g} mm 超出表格范围")


def journal_cylindricity(d: float) -> float:
    """与普通级滚动轴承配合的轴颈圆柱度。"""
    return _by_size(_JOURNAL_CYL, d)


def shoulder_runout(d: float) -> float:
    """滚动轴承定位轴肩的端面圆跳动。"""
    return _by_size(_SHOULDER_RUNOUT, d)


# 键槽对称度（GB/T 1184-1996 8 级，主参数为键槽宽 b）
_KEY_SYM = [(6, 15), (10, 20), (18, 25), (30, 30), (50, 40)]


def keyway_symmetry(b: float) -> float:
    return _by_size(_KEY_SYM, b)


def fmt_mm(v: float) -> str:
    """几何公差值（mm），如 0.012。"""
    return f"{round(v / UM) / 1000:.3f}"

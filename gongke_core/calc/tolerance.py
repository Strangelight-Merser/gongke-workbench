"""箱体零件图用到的公差：标准公差、齿轮副中心距极限偏差、轴线平行度、轴承座孔圆柱度。

长度参数用 SI（m），返回值也用 m。
"""

from __future__ import annotations

import bisect
import math

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

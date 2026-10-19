"""国标与教材数据的加载和查询。

数据文件放在仓库的 ``data/`` 目录，一个标准一个 YAML 文件。这里把行数组转换成带字段名的
dataclass，并提供按条件查询的函数。所有长度在返回时换算为 SI（m），载荷换算为 N。
"""

from __future__ import annotations

import bisect
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml


def data_dir() -> Path:
    """数据目录。可用环境变量 ``GONGKE_DATA`` 覆盖，默认是仓库根目录下的 ``data/``。"""
    env = os.environ.get("GONGKE_DATA")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[2] / "data"


@lru_cache(maxsize=None)
def load(relpath: str) -> dict:
    with open(data_dir() / relpath, encoding="utf-8") as f:
        return yaml.safe_load(f)


class SelectionError(ValueError):
    """标准件表中找不到满足条件的规格。"""


# ---------------------------------------------------------------- 电动机

@dataclass(frozen=True)
class Motor:
    model: str
    poles: int
    sync_speed_rpm: float
    power: float  # W
    speed_rpm: float
    shaft_d: float  # m
    shaft_l: float  # m


def motors() -> list[Motor]:
    rows = load("standards/JB-T_10391-2008_y_motors.yaml")["motors"]
    return [Motor(r[0], r[1], r[2], r[3] * 1e3, r[4], r[5] * 1e-3, r[6] * 1e-3) for r in rows]


def select_motor(required_power: float, sync_speed_rpm: float) -> Motor:
    """在给定同步转速下选额定功率不小于 ``required_power``（W）的最小电机。"""
    cands = sorted(
        (m for m in motors() if m.sync_speed_rpm == sync_speed_rpm and m.power >= required_power),
        key=lambda m: m.power,
    )
    if not cands:
        raise SelectionError(f"同步转速 {sync_speed_rpm} r/min 下没有功率 ≥ {required_power/1e3:.2f} kW 的电机")
    return cands[0]


# ---------------------------------------------------------------- 深沟球轴承

@dataclass(frozen=True)
class Bearing:
    designation: str
    d: float  # m
    D: float  # m
    B: float  # m
    Cr: float  # N
    C0r: float  # N

    @property
    def series(self) -> str:
        return self.designation[:2]


def deep_groove_ball_bearings() -> list[Bearing]:
    rows = load("standards/GB-T_276-2013_deep_groove_ball_bearings.yaml")["bearings"]
    return [Bearing(str(r[0]), r[1] * 1e-3, r[2] * 1e-3, r[3] * 1e-3, r[4] * 1e3, r[5] * 1e3) for r in rows]


def bearings_with_bore(d: float) -> list[Bearing]:
    """同一内径的各系列轴承，按承载能力从小到大排列。"""
    return sorted((b for b in deep_groove_ball_bearings() if abs(b.d - d) < 1e-6), key=lambda b: b.Cr)


def radial_load_factors(fa_c0r: float) -> tuple[float, float, float]:
    """深沟球轴承：按 Fa/C0r 插值得到 (e, X, Y)，其中 X、Y 用于 Fa/Fr > e 的情况。"""
    tab = load("standards/GB-T_6391-2010_radial_ball_load_factors.yaml")
    rows = tab["rows"]
    xs = [r[0] for r in rows]
    x = min(max(fa_c0r, xs[0]), xs[-1])
    i = max(1, min(bisect.bisect_left(xs, x), len(xs) - 1))
    (x0, e0, y0), (x1, e1, y1) = rows[i - 1], rows[i]
    t = (x - x0) / (x1 - x0)
    return e0 + t * (e1 - e0), tab["x_when_exceeds"], y0 + t * (y1 - y0)


# ---------------------------------------------------------------- 平键

@dataclass(frozen=True)
class KeySize:
    b: float  # m
    h: float
    t1: float  # 轴槽深
    t2: float  # 毂槽深


def key_size(d: float) -> KeySize:
    dm = d * 1e3
    for over, upto, b, h, t1, t2 in load("standards/GB-T_1095-2003_flat_keys.yaml")["sizes"]:
        if over < dm <= upto + 1e-9:
            return KeySize(b * 1e-3, h * 1e-3, t1 * 1e-3, t2 * 1e-3)
    raise SelectionError(f"轴径 {dm:.1f} mm 超出平键表范围")


def key_lengths() -> list[float]:
    return [v * 1e-3 for v in load("standards/GB-T_1095-2003_flat_keys.yaml")["lengths_mm"]]


# ---------------------------------------------------------------- 模数

def standard_modules(series: int = 1) -> list[float]:
    tab = load("standards/GB-T_1357-2008_modules.yaml")
    return [v * 1e-3 for v in tab["series_1" if series == 1 else "series_2"]]


# ---------------------------------------------------------------- 齿形系数、材料

def form_factors(zv: float) -> tuple[float, float]:
    """按当量齿数插值 (YFa, YSa)。zv < 17 时按 17 取值（会有根切，设计上应避免）。"""
    rows = load("textbook/gear_form_factors.yaml")["rows"]
    finite = [r for r in rows if r[0] is not None]
    rack = next(r for r in rows if r[0] is None)
    if zv <= finite[0][0]:
        return finite[0][1], finite[0][2]
    if zv >= finite[-1][0]:
        # 在 1/z 坐标下向齿条值插值
        z0, f0, s0 = finite[-1]
        t = (1 / z0 - 1 / zv) / (1 / z0)
        return f0 + t * (rack[1] - f0), s0 + t * (rack[2] - s0)
    zs = [r[0] for r in finite]
    i = bisect.bisect_left(zs, zv)
    (z0, f0, s0), (z1, f1, s1) = finite[i - 1], finite[i]
    t = (zv - z0) / (z1 - z0)
    return f0 + t * (f1 - f0), s0 + t * (s1 - s0)


@dataclass(frozen=True)
class GearMaterial:
    key: str
    name: str
    hardness_hb: float
    sigma_hlim: float  # Pa
    sigma_fe: float  # Pa


def gear_material(key: str) -> GearMaterial:
    for r in load("textbook/gear_materials.yaml")["materials"]:
        if r[0] == key:
            return GearMaterial(r[0], r[1], r[2], r[3] * 1e6, r[4] * 1e6)
    raise KeyError(f"未知齿轮材料 {key}")

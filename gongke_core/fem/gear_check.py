"""用二维齿根应力有限元模型复核圆柱齿轮、锥齿轮的弯曲强度计算中的 YFa·YSa（见 `fem/gear_tooth.py`）。

斜齿轮按当量齿数 zv = z/cos³β、锥齿轮按 zv = z/cos δ 建当量直齿轮模型，与教材查表的 YFa·YSa 比较；
其余系数（K、Yε、Yβ）不变，有限元齿根应力 σF' = σF × (有限元 YFa·YSa / 查表 YFa·YSa)。蜗轮不在此列。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from gongke_core.calc.gear import virtual_teeth
from gongke_core.fem import gear_tooth


@dataclass
class GearFemRow:
    name: str
    z: int
    zv: float
    yfa: float
    ysa: float
    yfs_fem: float
    sigma_f: float  # Pa，教材公式
    sigma_f_allow: float
    tooth: gear_tooth.ToothResult | None = field(default=None, repr=False)

    @property
    def yfs_table(self) -> float:
        return self.yfa * self.ysa

    @property
    def diff(self) -> float:
        return self.yfs_fem / self.yfs_table - 1

    @property
    def sigma_f_fem(self) -> float:
        return self.sigma_f * self.yfs_fem / self.yfs_table


def _pairs(design):
    if getattr(design.task, "scheme", "") == "worm":
        return []
    out = []
    stages = (("", design.high),) if design.low is None else (("高速级", design.high), ("低速级", design.low))
    for key, p in stages:
        bevel = not hasattr(p, "mn")
        kind = "锥齿轮" if bevel else "齿轮"
        for i, z in enumerate((p.z1, p.z2)):
            zv = p.check.zv[i] if bevel else virtual_teeth(z, p.beta)
            out.append((f"{key}{'小' if i == 0 else '大'}{kind}", z, zv, p.check, i))
    return out


def run(design, workdir: Path) -> list[GearFemRow]:
    rows = []
    cache: dict[float, gear_tooth.ToothResult] = {}
    for name, z, zv, chk, i in _pairs(design):
        key = round(zv, 3)
        if key not in cache:
            cache[key] = gear_tooth.solve(zv, Path(workdir), f"tooth_zv{round(zv * 10)}")
        t = cache[key]
        rows.append(GearFemRow(name, z, zv, chk.y_fa[i], chk.y_sa[i], t.yfs_fem, chk.sigma_f[i], chk.sigma_f_allow[i], t))
    return rows

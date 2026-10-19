"""用 CalculiX 梁单元模型复核各轴的刚度计算：对每个刚度校核点，列出解析法（只计弯曲，即教材方法）、
解析法计入剪切变形（Timoshenko 梁）和有限元三个结果。

U1 是 Timoshenko 梁单元，计入剪切变形，所以短粗的轴上有限元挠度比只计弯曲的解析解大（减速器轴约大 5%～30%），
应与计入剪切的解析解对照；两者的差别只来自数值积分和单元划分，应在 1% 以内。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from gongke_core.calc import shaft_stiffness as stiff
from gongke_core.fem import ccx, gear_check, gear_tooth, shaft_beam


@dataclass
class FemRow:
    shaft: str
    label: str
    kind: str  # "y" / "θ"
    z: float
    bending: float  # 解析法，只计弯曲（与刚度校核相同）
    timoshenko: float  # 解析法，计入剪切
    fem: float
    allow: float

    @property
    def diff(self) -> float:
        """有限元相对计入剪切的解析解的偏差。"""
        return self.fem / self.timoshenko - 1 if self.timoshenko else 0.0


@dataclass
class ShaftFem:
    name: str
    inp: Path
    dat: Path
    analytic: stiff.Deflection = field(repr=False)
    timoshenko: stiff.Deflection = field(repr=False)
    fem: shaft_beam.BeamResult = field(repr=False)
    supports: tuple[float, float] = (0.0, 0.0)


@dataclass
class FemReport:
    solver: str
    shafts: list[ShaftFem]
    rows: list[FemRow]
    gears: list[gear_check.GearFemRow] = field(default_factory=list)
    gear_note: str = ""  # 没有做齿根应力复核时的原因

    @property
    def max_diff(self) -> float:
        """轴：有限元与计入剪切的解析解的最大偏差。"""
        return max((abs(r.diff) for r in self.rows), default=0.0)

    @property
    def ok(self) -> bool:
        """有限元结果也满足许用值。"""
        return all(r.fem <= r.allow for r in self.rows) and all(g.sigma_f_fem <= g.sigma_f_allow for g in self.gears)


def run(design, workdir: Path, gears: bool = True) -> FemReport:
    """对已做刚度校核的各轴建立梁单元模型并求解；gears=True 时再做齿根应力复核（需要 gmsh）。
    design 为任一方案的设计结果（有 shafts 属性）。"""
    workdir = Path(workdir)
    exe = ccx.find()
    ccx.check_version(exe)
    v = ccx.version(exe)
    solver = f"CalculiX {v[0]}.{v[1]}"
    shafts, rows = [], []
    for s in design.shafts:
        if s.stiffness is None:
            continue
        lay = s.layout
        name = f"shaft{lay.index}"
        timo = stiff.solve(lay.segments, s.load_case, shear=True)
        fem = shaft_beam.solve(lay.segments, s.load_case, workdir, name)
        shafts.append(ShaftFem(lay.name, workdir / f"{name}.inp", workdir / f"{name}.dat", s.stiffness.curve, timo, fem,
                               tuple(s.load_case.supports)))
        for it in s.stiffness.items:
            if it.kind == "y":
                vals = (timo.deflection(it.z), fem.deflection(it.z))
            else:
                vals = (timo.slope(it.z), fem.slope(it.z))
            rows.append(FemRow(lay.name, it.label, it.kind, it.z, it.value, *vals, it.allow))
    rep = FemReport(solver, shafts, rows)
    if gears:
        try:
            rep.gears = gear_check.run(design, workdir)
        except gear_tooth.GmshNotFound as e:
            rep.gear_note = str(e)
    return rep


def to_markdown(rep: FemReport) -> str:
    lines = ["# 轴的刚度有限元复核（CalculiX）", "", f"求解器：{rep.solver}", "",
             "| 轴 | 校核点 | z / mm | 解析（弯曲） | 解析（计剪切） | 有限元 | 偏差 | 许用值 |",
             "|---|---|---|---|---|---|---|---|"]
    for r in rep.rows:
        if r.kind == "y":
            v = [f"{x * 1e3:.4f} mm" for x in (r.bending, r.timoshenko, r.fem, r.allow)]
        else:
            v = [f"{x:.5f} rad" for x in (r.bending, r.timoshenko, r.fem)] + [f"{r.allow:g} rad"]
        lines.append(f"| {r.shaft} | {r.label} | {r.z * 1e3:.1f} | {v[0]} | {v[1]} | {v[2]} | {r.diff * 100:+.1f}% | {v[3]} |")
    lines += ["", "偏差 = 有限元 / 解析（计剪切） − 1。输入文件 shaft*.inp 可用 FreeCAD FEM 或 ccx 直接打开复算。", ""]
    if rep.gears:
        lines += ["## 齿根弯曲应力", "",
                  "| 齿轮 | z | zv | YFa·YSa（查表） | YFa·YSa（有限元） | 偏差 | σF（公式） | σF（有限元） | [σF] |",
                  "|---|---|---|---|---|---|---|---|---|"]
        for g in rep.gears:
            lines.append(f"| {g.name} | {g.z} | {g.zv:.1f} | {g.yfa:.3f}×{g.ysa:.3f} = {g.yfs_table:.3f} | {g.yfs_fem:.3f} | "
                         f"{g.diff * 100:+.1f}% | {g.sigma_f / 1e6:.1f} MPa | {g.sigma_f_fem / 1e6:.1f} MPa | {g.sigma_f_allow / 1e6:.0f} MPa |")
        lines += ["", "二维平面应力模型（三个齿，齿顶加载），输入文件 tooth_z*.inp。", ""]
    elif rep.gear_note:
        lines += [f"未做齿根应力复核：{rep.gear_note}", ""]
    return "\n".join(lines)

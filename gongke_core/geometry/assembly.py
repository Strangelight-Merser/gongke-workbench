"""减速器装配体：按布置结果把各零件放到位，导出 STEP。"""

from __future__ import annotations

import math
from pathlib import Path

import build123d as bd

from gongke_core.design import ReducerDesign
from gongke_core.geometry import parts

MM = 1e-3


def _phase_for_mesh(z: int) -> float:
    """让从动轮在 −x 方向（朝向主动轮）对准齿槽：齿数为偶数时转半个齿距。"""
    return math.pi / z if z % 2 == 0 else 0.0


def build(design: ReducerDesign, with_housing: bool = True, z_up: bool = True, teeth: bool = False) -> dict[str, bd.Shape]:
    """返回 {零件名: 已定位的实体}，单位 mm。

    teeth=False 时齿轮用齿顶圆柱体简化表示（STEP 约 1 MB，打开快）；True 时建出完整渐开线斜齿（约 30 MB）。
    布置计算的坐标系是 y 向上、z 沿轴线；z_up=True 时绕 x 轴转 90°，使竖直方向为 +Z（FreeCAD 等 CAD 的习惯）。
    """
    if getattr(design, "bevel", None) is not None:
        from gongke_core.geometry import bevel

        out = bevel.build(design, with_housing, teeth)
        if z_up:
            rot = bd.Location((0, 0, 0), (1, 0, 0), 90)
            out = {k: rot * v for k, v in out.items()}
        return out
    out: dict[str, bd.Shape] = {}
    pairs = {"high": design.high, "low": design.low}
    for sr in design.shafts:
        lay = sr.layout
        x = lay.x / MM
        integral = []
        for g in lay.gears:
            pair = pairs[g.pair]
            if g.integral:
                integral.append((pair, g.z, 0.0))
        shaft = parts.stepped_shaft(lay.segments, integral, teeth)
        out[f"{lay.name}"] = shaft.moved(bd.Location((x, 0, 0)))
        for g in lay.gears:
            if g.integral:
                continue
            pair = pairs[g.pair]
            seat = next(s for s in lay.segments if s.role == "齿轮" and s.z0 <= g.z <= s.z1)
            z = pair.z1 if g.member == 1 else pair.z2
            rot = _phase_for_mesh(z) if g.member == 2 else 0.0
            blank = parts.gear_blank(pair, g.member, g.seat_d, seat.keyway, rot, teeth)
            label = f"{pair.inp.name}{'小' if g.member == 1 else '大'}齿轮"
            out[label] = blank.moved(bd.Location((x, 0, g.z / MM)))
        brg = lay.bearing
        for i, zc in enumerate(lay.bearing_z):
            out[f"{lay.name}轴承{brg.designation}-{'AB'[i]}"] = parts.ball_bearing(brg.d, brg.D, brg.B).moved(
                bd.Location((x, 0, zc / MM)))
        if lay.extension == "left" and design.belt is not None:
            from gongke_core.layout.pulley import large_pulley

            end = next(s for s in lay.segments if s.role == "端部")
            # 轮毂外端面比轴端多出 2 mm（轴端用挡圈压紧）
            out["大带轮"] = parts.v_pulley(large_pulley(design)).moved(bd.Location((x, 0, (end.z0 - 2 * MM) / MM)))
        elif lay.extension:
            end = next(s for s in lay.segments if s.role == "端部")
            hub = parts.coupling_half(end.d, lay.coupling_hub)
            if lay.extension == "left":
                # 轮毂端面与轴端齐平偏 2 mm，法兰朝外
                hub = hub.moved(bd.Location((x, 0, (end.z0 - 2 * MM) / MM)))
                hub = hub.mirror(bd.Plane((x, 0, (end.z0 + lay.coupling_hub / 2 - 2 * MM) / MM), z_dir=(0, 0, 1)))
            else:
                hub = hub.moved(bd.Location((x, 0, end.z0 / MM)))
            out[f"{lay.name}联轴器半体"] = hub
    if with_housing:
        from gongke_core.geometry import housing as hg
        from gongke_core.layout.housing_detail import detail

        t = detail(design)
        out["箱座"] = parts.housing_base(design.housing, [s.layout.x for s in design.shafts],
                                        [s.layout.bearing.D for s in design.shafts])
        out["箱盖"] = hg.cover(t)
        out.update(hg.accessories(t))
        seals = [s.layout.diameters.get("密封") or s.layout.bearing.d for s in design.shafts]
        out.update(hg.bearing_caps(t, [s.layout.extension for s in design.shafts], seals))
    if z_up:
        rot = bd.Location((0, 0, 0), (1, 0, 0), 90)
        out = {k: rot * v for k, v in out.items()}
    return out


def export(design: ReducerDesign, path: str | Path, with_housing: bool = True, teeth: bool = False) -> dict[str, bd.Shape]:
    shapes = build(design, with_housing, teeth=teeth)
    children = []
    for name, shp in shapes.items():
        shp.label = name
        children.append(shp)
    label = "圆锥-圆柱齿轮减速器" if getattr(design, "bevel", None) is not None else "二级圆柱齿轮减速器"
    asm = bd.Compound(children=children, label=label)
    bd.export_step(asm, str(path))
    return shapes

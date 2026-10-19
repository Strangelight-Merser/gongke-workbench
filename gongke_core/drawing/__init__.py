"""二维工程图：按 GB 制图规定生成零件图和装配图（DXF），并可渲染为 SVG 预览。

图形按国标规定画法直接由设计数据生成（齿轮用齿顶线、分度线、齿根线表示，不画齿形），
不依赖三维模型的投影，因此线条干净、尺寸与计算结果完全一致。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class DrawingFile:
    name: str  # 中文图名（显示用）
    number: str  # 图号
    dxf: Path
    svg: Path | None
    size: str  # 图幅


def material_name(code: str) -> str:
    """任务书材料代号（如 40Cr_QT）→ 图样材料栏写法（40Cr）。"""
    return code.split("_")[0]


def build_all(design, out_dir: str | Path, svg: bool = True) -> list[DrawingFile]:
    """生成整套图纸：装配图 GK-00、各轴 GK-01-0n、各（非齿轮轴的）齿轮 GK-02-0n，V 带方案另有大带轮 GK-03-01。

    文件名用 ASCII：assembly.dxf、shaft1.dxf…、gear_high2.dxf（高速级大齿轮）等。
    """
    from gongke_core.drawing import assembly, gear, render, shaft

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    files: list[DrawingFile] = []

    def done(sh, name, number, stem):
        dxf = out / f"{stem}.dxf"
        svg_path = None
        if svg:
            svg_path = out / f"{stem}.svg"
            render.to_svg(dxf, svg_path, sh.w, sh.h)
        files.append(DrawingFile(name, number, dxf, svg_path, sh.size))

    worm = getattr(design, "worm_shaft", None) is not None
    if not worm:
        sh = assembly.draw(design, out / "assembly.dxf", "GK-00")
        done(sh, "减速器装配图", "GK-00", "assembly")
    for i, sr in enumerate(design.shafts, 1):
        no = f"GK-01-0{i}"
        sh = shaft.draw(design, sr, out / f"shaft{i}.dxf", no)
        name = "蜗杆" if worm and i == 1 else sr.layout.name.split("（")[0]
        done(sh, name + "零件图", no, f"shaft{i}")
    pairs = {"high": design.high, "low": getattr(design, "low", None)}
    k = 0
    for sr in design.shafts:
        for g in sr.layout.gears:
            if g.integral:
                continue
            k += 1
            no = f"GK-02-0{k}"
            stem = f"gear_{g.pair}{g.member}"
            if g.pair == "worm":
                from gongke_core.drawing import worm_wheel

                title = "蜗轮"
                sh = worm_wheel.draw(design.worm, g.seat_d, g.width, out / "wheel.dxf", title, no)
                done(sh, title + "零件图", no, "wheel")
                continue
            if g.pair == "bevel":
                from gongke_core.drawing import bevel_gear

                pair = design.bevel
                title = f"{'小' if g.member == 1 else '大'}锥齿轮"
                mat = material_name(pair.inp.material1 if g.member == 1 else pair.inp.material2)
                hub = design.pinion.pinion_length if g.member == 1 else design.positions.hub
                sh = bevel_gear.draw(pair, g.member, g.seat_d, out / f"{stem}.dxf", title, no, mat, hub)
            else:
                pair = pairs[g.pair]
                title = f"{pair.inp.name}{'小' if g.member == 1 else '大'}齿轮"
                mat = material_name(pair.inp.material1 if g.member == 1 else pair.inp.material2)
                sh = gear.draw(pair, g.member, g.seat_d, out / f"{stem}.dxf", title, no, mat)
            done(sh, title + "零件图", no, stem)
    if design.belt is not None:
        from gongke_core.drawing import pulley as pulley_dwg
        from gongke_core.layout.pulley import large_pulley

        sh = pulley_dwg.draw(large_pulley(design), out / "pulley.dxf", "大带轮", "GK-03-01")
        done(sh, "大带轮零件图", "GK-03-01", "pulley")
    return files

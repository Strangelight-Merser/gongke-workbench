"""命令行入口。

    python -m gongke_core design 任务书.yaml -o 输出目录 [--no-step] [--no-docx] [--no-drawings]

输出：summary.json（结果摘要）、report.docx / .md、reducer_assembly.step、
drawings/（装配图和零件图，DXF + SVG 预览）。
FreeCAD 工作台也通过这个入口在独立进程中生成模型。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="gongke_core", description="工科工作台：带式输送机传动装置（二级减速器）设计")
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("design", help="按任务书完成设计计算，生成说明书和三维模型")
    d.add_argument("task", help="任务书 YAML 文件")
    d.add_argument("-o", "--out", default="out", help="输出目录")
    d.add_argument("--no-step", action="store_true", help="不生成三维模型")
    d.add_argument("--no-docx", action="store_true", help="不生成 Word 说明书（仍生成 Markdown）")
    d.add_argument("--no-housing", action="store_true", help="装配体中不含箱座")
    d.add_argument("--no-drawings", action="store_true", help="不生成二维工程图")
    d.add_argument("--full-teeth", action="store_true", help="建出完整渐开线齿形（文件约 30 MB，生成较慢）")
    args = ap.parse_args(argv)

    from gongke_core import design, summary
    from gongke_core.report import content, markdown_writer

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    res = design.run(design.ReducerTask.from_yaml(args.task))
    (out / "summary.json").write_text(json.dumps(summary.summarize(res), ensure_ascii=False, indent=2), encoding="utf-8")
    doc = content.build(res)
    markdown_writer.write(doc, out / "report.md")
    if not args.no_docx:
        try:
            from gongke_core.report import docx_writer
            docx_writer.write(doc, out / "report.docx")
        except ImportError:
            print("未安装 python-docx，跳过 Word 说明书", file=sys.stderr)
    print(f"计算完成（{time.time()-t0:.1f} s）：{'全部校核通过' if res.ok else '有校核项不满足，见 summary.json'}")
    no_geometry = res.task.scheme == "bevel"
    if no_geometry:
        print("圆锥-圆柱齿轮减速器方案暂不生成三维模型和工程图（后续版本提供）", file=sys.stderr)
    if not args.no_drawings and not no_geometry:
        try:
            from gongke_core import drawing
            from gongke_core.drawing import render  # noqa: F401  需要 ezdxf
        except ImportError:
            print("未安装 ezdxf，跳过工程图", file=sys.stderr)
        else:
            t1 = time.time()
            files = drawing.build_all(res, out / "drawings")
            index = [{"name": f.name, "number": f.number, "size": f.size, "dxf": f.dxf.name,
                      "svg": f.svg.name if f.svg else None} for f in files]
            (out / "drawings" / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"工程图已生成（{time.time()-t1:.1f} s）：{len(files)} 张，见 {out / 'drawings'}")
    if not args.no_step and not no_geometry:
        from gongke_core.geometry import assembly
        t1 = time.time()
        assembly.export(res, out / "reducer_assembly.step", with_housing=not args.no_housing, teeth=args.full_teeth)
        print(f"三维模型已生成（{time.time()-t1:.1f} s）：{out / 'reducer_assembly.step'}")
    return 0 if res.ok else 2


if __name__ == "__main__":
    sys.exit(main())

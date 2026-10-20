"""命令行入口。

    python -m gongke_core design 任务书.yaml -o 输出目录 [--no-step] [--no-docx] [--no-drawings] [--fem]

输出：summary.json（结果摘要）、report.docx / .md、reducer_assembly.step、
drawings/（装配图和零件图，DXF + SVG 预览，整套 drawings.pdf）；加 --fem 时还有 fem/（CalculiX 输入、结果和对照表）。
FreeCAD 工作台也通过这个入口在独立进程中生成模型。

    python -m gongke_core mcp       # 以 MCP 服务器方式运行（stdio），供 AI agent 直接调用，见 docs/agent-api.md
    python -m gongke_core schema    # 输出任务书的 JSON Schema
    python -m gongke_core check-drawings 输出目录/drawings   # 检查图纸文字重叠和压线
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
    d.add_argument("--fem", action="store_true", help="用 CalculiX 复核轴的刚度和齿根应力（需要 ccx 和 gmsh，FreeCAD 自带）")
    d.add_argument("--full-teeth", action="store_true", help="建出完整渐开线齿形（文件约 30 MB，生成较慢）")
    sub.add_parser("mcp", help="以 MCP 服务器方式运行（stdio），供 AI agent 调用")
    sub.add_parser("schema", help="输出任务书的 JSON Schema")
    c = sub.add_parser("check-drawings", help="检查 DXF 图纸中文字重叠和图线压字")
    c.add_argument("path", help="DXF 文件或图纸目录")
    args = ap.parse_args(argv)
    if args.cmd == "check-drawings":
        from gongke_core import api
        r = api.check_drawings(args.path)
        for sh in r["sheets"]:
            for i in sh["issues"]:
                print(f"{sh['file']}  {i['kind']}  “{i['text']}” 于 ({i['at'][0]}, {i['at'][1]}) {i['other']}")
        print(f"检查 {r['checked']} 张图，发现 {r['total']} 处问题")
        return 1 if r["total"] else 0
    if args.cmd == "mcp":
        from gongke_core import mcp_server
        mcp_server.serve()
        return 0
    if args.cmd == "schema":
        from gongke_core import api
        print(json.dumps(api.task_schema(), ensure_ascii=False, indent=2))
        return 0

    from gongke_core import design, summary
    from gongke_core.report import content, markdown_writer

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    res = design.run(design.ReducerTask.from_yaml(args.task))
    fem = None
    if args.fem:
        from gongke_core.fem import ccx, shaft_check
        try:
            fem = shaft_check.run(res, out / "fem")
        except ccx.CcxNotFound as e:
            print(f"跳过有限元复核：{e}", file=sys.stderr)
        else:
            (out / "fem" / "comparison.md").write_text(shaft_check.to_markdown(fem), encoding="utf-8")
            gears = f"，{len(fem.gears)} 个齿轮的齿根应力" if fem.gears else ""
            print(f"有限元复核完成：{len(fem.shafts)} 根轴（与解析结果最大相差 {fem.max_diff * 100:.2f}%）{gears}")
            if fem.gear_note:
                print(f"跳过齿根应力复核：{fem.gear_note}", file=sys.stderr)
    (out / "summary.json").write_text(json.dumps(summary.summarize(res, fem), ensure_ascii=False, indent=2), encoding="utf-8")
    doc = content.build(res, fem=fem)
    markdown_writer.write(doc, out / "report.md")
    if not args.no_docx:
        try:
            from gongke_core.report import docx_writer
            docx_writer.write(doc, out / "report.docx")
        except ImportError:
            print("未安装 python-docx，跳过 Word 说明书", file=sys.stderr)
    print(f"计算完成（{time.time()-t0:.1f} s）：{'全部校核通过' if res.ok else '有校核项不满足，见 summary.json'}")
    no_geometry = False
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
            print(f"工程图已生成（{time.time()-t1:.1f} s）：{len(files)} 张，见 {out / 'drawings'}（整套打印用 drawings.pdf）")
    if not args.no_step and not no_geometry:
        from gongke_core.geometry import assembly
        t1 = time.time()
        assembly.export(res, out / "reducer_assembly.step", with_housing=not args.no_housing, teeth=args.full_teeth)
        print(f"三维模型已生成（{time.time()-t1:.1f} s）：{out / 'reducer_assembly.step'}")
    return 0 if res.ok else 2


if __name__ == "__main__":
    sys.exit(main())

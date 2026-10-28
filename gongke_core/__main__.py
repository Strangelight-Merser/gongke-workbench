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

    import yaml
    from gongke_core.delivery import generate
    from gongke_core.task_input import TaskError

    try:
        with open(args.task, encoding="utf-8") as f:
            task = yaml.safe_load(f)
        result = generate(task, args.out, report_docx=not args.no_docx,
                          drawings=not args.no_drawings, step=not args.no_step,
                          full_teeth=args.full_teeth, fem=args.fem,
                          with_housing=not args.no_housing, source_task=args.task)
    except (TaskError, OSError, yaml.YAMLError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(f"计算校核：{'通过' if result['calculation_ok'] else '未通过或未完成'}；"
          f"请求产物：{'齐全' if result['exports_complete'] else '未完成'}")
    for note in result['notes']:
        print(note)
    print(f"本次交付清单：{Path(result['out_dir']) / 'manifest.json'}")
    return 0 if result['ok'] else 2


if __name__ == "__main__":
    sys.exit(main())

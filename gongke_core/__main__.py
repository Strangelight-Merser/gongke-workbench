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
    ap = argparse.ArgumentParser(prog="gongke_core", description="工科工作台：原生工程检查与工程计算")
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
    m = sub.add_parser("mcp", help="以 MCP 服务器方式运行（stdio），供 AI agent 调用")
    m.add_argument("--profile", choices=("all", "native", "batch"), default="all", help="限定原生工程或任务书批处理工具")
    r = sub.add_parser("inspect-revision", help="只读核对已有轴与原生图纸，不生成或修改 CAD")
    r.add_argument("--host", choices=("freecad",), default="freecad")
    r.add_argument("--case", required=True, type=Path, help="包含工程路径、尺寸映射和条件的任务 JSON")
    r.add_argument("--capture", type=Path, help="可选的离线 FreeCAD 采集；省略时读取当前宿主")
    r.add_argument("--previous", type=Path, help="上次 revision.json，用于核对旧结论是否过期")
    r.add_argument("--out", required=True, type=Path, help="必须尚不存在的新输出目录")
    sub.add_parser("schema", help="输出任务书的 JSON Schema")
    c = sub.add_parser("check-drawings", help="检查 DXF 图纸中文字重叠和图线压字")
    c.add_argument("path", help="DXF 文件或图纸目录")
    args = ap.parse_args(argv)
    if args.cmd == "inspect-revision":
        from gongke_core.native_client import NativeBridgeError
        from gongke_core.revision_case import inspect_revision, format_summary
        try:
            if args.out.exists():
                raise ValueError("输出目录已存在，请指定新目录，保留原来的检查记录")
            read = lambda path: json.loads(path.read_text(encoding="utf-8")) if path else None
            result = inspect_revision(read(args.case), read(args.capture), read(args.previous))
            summary = format_summary(result)
            args.out.mkdir(parents=True, exist_ok=False)
            (args.out / "revision.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
            print(summary)
            print(f"检查结果：{(args.out / 'revision.json').resolve()}")
            return 0 if result["drawing_review"]["status"] == "pass" and result["calculation"]["numerical_status"] == "pass" else 1
        except (OSError, ValueError, NativeBridgeError) as exc:
            print(str(exc), file=sys.stderr)
            return 2
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
        mcp_server.serve(profile=args.profile)
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

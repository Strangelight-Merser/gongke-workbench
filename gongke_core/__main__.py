"""命令行入口。

    python -m gongke_core design 任务书.yaml -o 输出目录 [--no-step] [--no-docx]

输出：summary.json（结果摘要）、report.docx / .md、reducer_assembly.step。
FreeCAD 工作台也通过这个入口在独立进程中生成模型。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="gongke_core", description="工科工作台：二级圆柱齿轮减速器设计")
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("design", help="按任务书完成设计计算，生成说明书和三维模型")
    d.add_argument("task", help="任务书 YAML 文件")
    d.add_argument("-o", "--out", default="out", help="输出目录")
    d.add_argument("--no-step", action="store_true", help="不生成三维模型")
    d.add_argument("--no-docx", action="store_true", help="不生成 Word 说明书（仍生成 Markdown）")
    d.add_argument("--no-housing", action="store_true", help="装配体中不含箱座")
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
    if not args.no_step:
        from gongke_core.geometry import assembly
        t1 = time.time()
        assembly.export(res, out / "reducer_assembly.step", with_housing=not args.no_housing)
        print(f"三维模型已生成（{time.time()-t1:.1f} s）：{out / 'reducer_assembly.step'}")
    return 0 if res.ok else 2


if __name__ == "__main__":
    sys.exit(main())

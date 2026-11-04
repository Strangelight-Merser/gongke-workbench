"""沙箱外启动真实 Electron、dsh、FreeCAD；不替模型执行建模配方。"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tests.e2e.agent_modeling_result import classify, summarize
from scripts.owned_processes import OwnedProcesses
OWNED = OwnedProcesses()
SOURCE = Path("/Users/huaiyi/Documents/gongke-workbench/samples/student-materials/drawing-to-model-sheet-01.jpg")
PDF_SOURCE = Path("/Users/huaiyi/Documents/gongke-workbench/samples/student-materials/quadruped-robot-drawings.pdf")
PDF_CASES = {"robot14": 14, "robot13": 13, "robot4": 4}
STUDY = Path("/Users/huaiyi/Documents/gongke-workbench/out/drawing-to-model-study")
# 只裁局部原图，不放大、不补画尺寸。参考体不进入模型可读的工程。
CROPS = {"p7": (77, 1282, 451, 1574), "p8": (472, 1282, 876, 1575), "p6": (473, 1009, 862, 1267)}


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def isolated_runs(args):
    """重复试验使用不同宿主，防止下一次从 host.context 看到上一次的答案。"""
    results = []
    for case in args.cases:
        for i in range(1, args.repeats + 1):
            directory = args.output / "runs" / f"{case}-{i}"
            command = [sys.executable, str(Path(__file__).resolve()), "--cases", case, "--delivery", args.delivery,
                       "--repetition-index", str(i), "--timeout", str(args.timeout), "--reasoning", args.reasoning]
            for name, value in (("output", directory), ("source", args.source), ("study", args.study),
                                ("dsh", args.dsh), ("freecad", args.freecad)):
                command += ["--"+name, str(value)]
            if args.background:
                command.append("--background")
            code = subprocess.run(command, cwd=ROOT).returncode
            summary = directory / "summary.json"
            rows = json.loads(summary.read_text()).get("results", []) if summary.exists() else []
            if not rows:
                rows = [{"case": case, "repetition": i, "status": "run_failed", "error": f"子试验退出 {code}，见 {directory}"}]
            for row in rows:
                row["run_directory"] = str(directory)
            results.extend(rows)
            report = summarize(results)
            if any(r.get("failure_category") == "provider_balance_exhausted" for r in rows):
                report.update(stopped_reason="provider_balance_exhausted", requested_trials=len(args.cases)*args.repeats)
                write_json(args.output / "summary.json", report)
                return 1  # 余额已明确耗尽，不再启动余下付费请求；未运行不计为建模失败。
            write_json(args.output / "summary.json", report)
    return int(any(r["status"] not in {"passed", "review_required"} for r in results))


def cad_environment(env):
    # macOS 启动器会输出环境；CAD 不需要 Agent 的凭据或服务环境。
    system = {"HOME", "PATH", "TMPDIR", "USER", "LOGNAME", "LANG", "LC_ALL", "LC_CTYPE", "DISPLAY", "XAUTHORITY"}
    return {k: v for k, v in env.items() if k in system or k in {
        "GONGKE_MODELING_ROOT", "GONGKE_FREECAD_SESSION", "GONGKE_TRIAL_OUTPUT", "GONGKE_CONSTRAINT_EXIT", "GONGKE_TRIAL_BACKGROUND"}}


def launch_cad(args, macro, env, log):
    local = cad_environment(env)
    command = [str(args.freecad), str(macro)]
    with log.open("w") as stream:
        return OWNED.spawn(command, cwd=ROOT, env=local, stdout=stream, stderr=subprocess.STDOUT)


def prepare_pdf(args):
    import pypdfium2 as pdfium
    args.output.mkdir(parents=True, exist_ok=False)
    folder = args.output / "inputs"
    folder.mkdir()
    inputs = {}
    with pdfium.PdfDocument(args.source) as source:
        for case in args.cases:
            target = folder / (case+".pdf")
            with pdfium.PdfDocument.new() as excerpt:
                excerpt.import_pages(source, [PDF_CASES[case]-1])
                excerpt.save(target)
            inputs[case] = {"path": str(target), "source_page": PDF_CASES[case], "sha256": hashlib.sha256(target.read_bytes()).hexdigest()}
    manifest = {"started_at": datetime.now(timezone.utc).isoformat(), "root": str(ROOT),
        "source": str(args.source), "source_sha256": hashlib.sha256(args.source.read_bytes()).hexdigest(),
        "crops": inputs, "structured": {}, "cases": args.cases, "repeats": args.repeats,
        "delivery": "pdf", "input_scope": "vector_pdf_extraction_without_images",
        "python": sys.executable, "dsh": str(args.dsh), "freecad": str(args.freecad),
        "repetition_index": args.repetition_index, "background": args.background, "reasoning": args.reasoning,
        "acp_initial_model": {"provider": "deepseek-official", "model": "deepseek-flash"},
        "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()}
    manifest["sources"] = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
        for base in ("gongke_app", "freecad/gongke", "desktop/electron", "desktop/tests", "scripts", "tests/e2e")
        for p in (ROOT / base).rglob("*") if p.is_file() and p.suffix in {".py", ".cts", ".cjs", ".FCMacro"}}
    write_json(args.output / "manifest.json", manifest)
    return manifest


def wait_for_host(host, directory):
    deadline = time.monotonic() + 90
    while not (directory / "bootstrap.json").exists():
        if host.poll() is not None:
            raise RuntimeError(f"FreeCAD 提前退出，请读取 {directory / 'freecad.log'}")
        if time.monotonic() > deadline:
            raise TimeoutError(f"宿主未就绪；检查 {directory} 的宏提示与日志")
        time.sleep(.25)
    boot = json.loads((directory / "bootstrap.json").read_text())
    assert Path(boot["root"]) == ROOT
    for row in boot["sources"].values():
        assert hashlib.sha256(Path(row["path"]).read_bytes()).hexdigest() == row["sha256"]


def constraint_preflight(args, env):
    directory = args.output / "constraint-preflight"
    directory.mkdir()
    stop = directory / "exit"
    local = {**env, "GONGKE_FREECAD_SESSION": str(directory / "session.json"), "GONGKE_CONSTRAINT_EXIT": str(stop)}
    print(f"先运行独立宿主约束回归：{directory}", flush=True)
    host = launch_cad(args, ROOT / "tests/e2e/sketch_constraint_host.FCMacro", local, directory / "freecad.log")
    write_json(directory / "process.json", {"pid": host.pid})
    try:
        wait_for_host(host, directory)
        with (directory / "runner.log").open("w") as log:
            subprocess.run([sys.executable, str(ROOT / "tests/e2e/sketch_constraint_acceptance.py"), str(directory)],
                           cwd=ROOT, env=local, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=180)
    except Exception as exc:
        write_json(directory / "failure.json", {"error": str(exc), "host_exit_code": host.poll()})
        raise RuntimeError(f"约束回归未通过，未消费模型 token；请交回 {directory}") from exc
    finally:
        stop.touch()
        try:
            host.wait(timeout=10)
        except subprocess.TimeoutExpired:
            # 只终止本脚本新建的回归进程，不碰学生或真实建模实例。
            host.terminate()
            try:
                host.wait(timeout=5)
            except subprocess.TimeoutExpired:
                host.kill()
                host.wait()


def prepare(args):
    if args.delivery == "pdf":
        return prepare_pdf(args)
    from PIL import Image
    args.output.mkdir(parents=True, exist_ok=False)
    image = Image.open(args.source)
    if image.size != (920, 2000):
        raise ValueError("裁剪坐标只适用于本次 920×2000 原图，请核对输入")
    inputs = args.output / "inputs"
    inputs.mkdir()
    crops = {}
    for case in args.cases:
        target = inputs / (case + ".png")
        image.crop(CROPS[case]).save(target)
        crops[case] = {"path": str(target), "box": CROPS[case], "sha256": hashlib.sha256(target.read_bytes()).hexdigest()}
    structured = {}
    vision_expectations = {}
    vision_fields = {}
    vision_review_required = {}
    reading_sources = {}
    if args.delivery in {"dimensions", "vision"}:
        dimension_path = args.study / "dimensions.json"
        extraction = json.loads(dimension_path.read_text())
        if Path(extraction["source_path"]).resolve() != args.source or extraction["source_pixels"] != list(image.size):
            raise ValueError("尺寸提取资料与本轮原图来源不符")
        for case in args.cases:
            if case == "p7":
                p7 = extraction["p7"]
                if p7["bbox_px"] != list(CROPS["p7"]):
                    raise ValueError("P7 尺寸资料裁剪区域不符")
                record = {
                    "kind": "drawing-dimensions", "part": "p7", "extraction": "人工读图复核，非自动视觉识别",
                    "source": {"name": args.source.name, "sha256": hashlib.sha256(args.source.read_bytes()).hexdigest(),
                               "crop_sha256": crops["p7"]["sha256"], "bbox_px": p7["bbox_px"],
                               "dimension_record_sha256": hashlib.sha256(dimension_path.read_bytes()).hexdigest()},
                    "unit": extraction["unit"], "unit_status": extraction["unit_status"], "tolerance": extraction["tolerance"],
                    "values": p7["values"], "evidence": p7["evidence"], "coordinate_system": p7["coordinate_system"],
                    "view_interpretation": [
                        "底座俯视外轮廓为等宽长圆，两端圆心分别与槽左端、圆筒轴重合；两侧直边与端圆相切。端部半径未独立标注，base_end_radius 是假设。",
                        "槽口俯视为长圆，左右端圆心间距 slot_center_distance；槽右端圆心至筒轴距离 slot_to_tube_center，三者在同一中心线上。",
                        "槽周围有同心长圆凸台，其外轮廓端圆半径 boss_radius；内槽端圆半径 slot_radius，内槽贯穿凸台及底板。",
                        "右侧圆筒与底座一体，外径 tube_outer_diameter、孔径 tube_inner_diameter；孔贯穿到底面。",
                        "base_thickness 是底板厚度；boss_total_height、tube_total_height 均为从底面 z=0 到顶部的总高度，不是底板之上的增加量。",
                    ],
                    "unconfirmed": ["无标题栏，单位暂按 mm", "底座端部 R10 及等宽相切外形为读图推断", "未给公差、材料；未标的倒角或圆角不补造"],
                }

                fields = {"base_thickness": "底板厚度", "boss_total_height": "槽凸台从底面起总高", "tube_total_height": "圆筒总高",
                          "tube_outer_diameter": "筒外径", "tube_inner_diameter": "筒孔径", "slot_center_distance": "槽两端圆心距",
                          "slot_to_tube_center": "槽右端圆心至筒轴距离", "boss_radius": "槽凸台端圆半径", "slot_radius": "槽端圆半径",
                          "slot_through": "槽是否穿透底板，布尔值", "bore_through": "筒孔是否穿透底板，布尔值"}
                expected = {k: v for k, v in record["values"].items() if k != "base_end_radius"}
                expected.update(slot_through=True, bore_through=True)
            else:
                record_path = ROOT / "tests/fixtures/agent_modeling/p6-reading.json"
                record = json.loads(record_path.read_text())
                record["source"] = {"name": args.source.name, "sha256": hashlib.sha256(args.source.read_bytes()).hexdigest(),
                                    "crop_sha256": crops[case]["sha256"], "bbox_px": CROPS[case],
                                    "dimension_record_sha256": hashlib.sha256(record_path.read_bytes()).hexdigest()}
                fields = dict(zip(record["values"], ["总长", "总宽", "总高", "左侧内宽", "内底至最高顶面的落差", "右平台至最高顶面的落差", "右端平台长", "右端平台及斜面总跨度", "前缘平台宽"]))
                expected = {k: record["values"][k] for k in record["confirmed_fields"]}
            vision_fields[case] = fields
            vision_expectations[case] = expected
            vision_review_required[case] = record.get("requires_drawing_review", False)
            reading_sources[case] = record["source"]["dimension_record_sha256"]
            if args.delivery == "dimensions":
                target = inputs / f"{case}-dimensions.json"
                write_json(target, record)
                structured[case] = {"path": str(target), "sha256": hashlib.sha256(target.read_bytes()).hexdigest()}
    manifest = {
        "started_at": datetime.now(timezone.utc).isoformat(), "root": str(ROOT),
        "source": str(args.source), "source_sha256": hashlib.sha256(args.source.read_bytes()).hexdigest(),
        "crops": crops, "structured": structured, "vision_expectations": vision_expectations, "vision_fields": vision_fields, "vision_review_required": vision_review_required, "input_scope": "human_transcribed_dimensions" if args.delivery == "dimensions" else "image", "cases": args.cases, "repeats": args.repeats, "delivery": args.delivery,
        "python": sys.executable, "dsh": str(args.dsh), "freecad": str(args.freecad), "repetition_index": args.repetition_index, "background": args.background, "reasoning": args.reasoning,
        "acp_initial_model": {"provider": "deepseek-official", "model": "deepseek-flash"} if args.delivery in {"dimensions", "vision"} else None,
        "constraint_fixture_sha256": hashlib.sha256((ROOT / "tests/fixtures/native_modeling/fixed-center.json").read_bytes()).hexdigest(),
        "reading_source_sha256": reading_sources,
        "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "git_diff_sha256": hashlib.sha256(subprocess.check_output(["git", "diff", "HEAD"], cwd=ROOT)).hexdigest(),
    }
    # 新增脚本尚未提交时也能明确归属运行的源码。
    files = [p for base in ("gongke_app", "freecad/gongke", "desktop/electron", "desktop/src", "scripts", "tests/e2e", "desktop/tests")
             for p in (ROOT / base).rglob("*") if p.is_file() and p.suffix in {".py", ".cts", ".tsx", ".ts", ".cjs", ".FCMacro"}]
    manifest["sources"] = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}
    write_json(args.output / "manifest.json", manifest)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--study", type=Path, default=STUDY)
    parser.add_argument("--output", type=Path, default=ROOT / "out" / ("agent-modeling-" + datetime.now().strftime("%Y%m%d-%H%M%S")))
    parser.add_argument("--cases", nargs="+", choices=[*CROPS, *PDF_CASES], default=["p7"])
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--repetition-index", type=int, default=1, help=argparse.SUPPRESS)
    parser.add_argument("--delivery", choices=["attachment", "mcp", "dimensions", "vision", "pdf"], default="attachment")
    parser.add_argument("--timeout", type=int, default=1200, help="每件零件最多秒数；超时取消，不自动重试写操作")
    parser.add_argument("--dsh", type=Path, default=Path("/Applications/DeepSeek Harness.app/Contents/Resources/runtime/cli/bin/dsh"))
    parser.add_argument("--freecad", type=Path, default=Path("/Applications/FreeCAD.app/Contents/MacOS/FreeCAD"))
    parser.add_argument("--reasoning", choices=["high", "low", "off"], default="high", help="通过 ACP 配置选择推理强度，记录在试验 manifest")
    parser.add_argument("--background", action="store_true", help="macOS 后台隐藏独立验收窗口，不占用桌面焦点；结束后关闭自身 CAD 实例")
    parser.add_argument("--prepare-only", action="store_true", help="只裁图、记录版本，不启动 GUI 或消费模型 token")
    args = parser.parse_args()
    if args.repeats < 1 or args.timeout < 1 or args.repetition_index < 1:
        parser.error("repeats、repetition-index 和 timeout 必须为正数")
    if args.delivery in {"dimensions", "vision"} and any(case not in {"p7", "p6"} for case in args.cases):
        parser.error("尺寸/视觉比较支持 P7 与 P6；P6 模糊读数显式列为假设")
    if args.delivery == "pdf":
        if any(case not in PDF_CASES for case in args.cases):
            parser.error("PDF 试验请选择 robot14、robot13 或 robot4")
        if args.source == SOURCE:
            args.source = PDF_SOURCE
    elif any(case in PDF_CASES for case in args.cases):
        parser.error("机器人零件需 --delivery pdf")
    for name in ("output", "source", "study", "dsh", "freecad"):
        setattr(args, name, getattr(args, name).expanduser().resolve())
    manifest = prepare(args)
    print(f"本轮记录：{args.output}", flush=True)
    if args.prepare_only:
        return
    if args.repeats > 1 or len(args.cases) > 1:
        sys.exit(isolated_runs(args))
    env = {**os.environ, "GONGKE_PYTHON": sys.executable, "GONGKE_MODELING_ROOT": str(ROOT),
           "GONGKE_FREECAD_SESSION": str(args.output / "host" / "session.json")}
    # 不沿用其他试验的 Agent/MCP 配置；Key 仍由已安装 dsh 自己读取。
    if args.background:
        env["GONGKE_TRIAL_BACKGROUND"] = "1"
    env.pop("GONGKE_AGENT_CONFIG", None)
    env.pop("ELECTRON_RUN_AS_NODE", None)
    manifest["dsh_version"] = subprocess.check_output([str(args.dsh), "--version"], env=env, text=True).strip()
    write_json(args.output / "manifest.json", manifest)
    desktop = ROOT / "desktop"
    if not (desktop / "node_modules").exists():
        subprocess.run(["npm", "ci"], cwd=desktop, env=env, check=True)
    # npm ci --ignore-scripts 的开发环境需显式补齐 Electron 可执行文件。
    if not (desktop / "node_modules/electron/path.txt").exists():
        subprocess.run(["node", "node_modules/electron/install.js"], cwd=desktop, env=env, check=True)
    with (args.output / "build.log").open("w") as log:
        subprocess.run(["npm", "run", "build"], cwd=desktop, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
    try:
        constraint_preflight(args, env)
    except Exception as exc:
        write_json(args.output / "summary.json", {"attempted": 0, "prompts_sent": 0, "passed": 0, "results": [],
                   "automatic_pass_rate": None, "failed_stage": "constraint-preflight", "error": str(exc)})
        raise
    host_dir = args.output / "host"
    host_dir.mkdir()
    host = launch_cad(args, ROOT / "tests/e2e/native_modeling_host.FCMacro", env, host_dir / "freecad.log")
    write_json(host_dir / "process.json", {"pid": host.pid})
    wait_for_host(host, host_dir)
    env.update(GONGKE_TRIAL_OUTPUT=str(args.output), GONGKE_TRIAL_STUDY=str(args.study),
               GONGKE_TRIAL_DSH=str(args.dsh), GONGKE_TRIAL_TIMEOUT=str(args.timeout))
    print(f"FreeCAD 启动进程 PID={host.pid}；结束后关闭本试验的 CAD/Agent。", flush=True)
    with (args.output / "runner.log").open("w") as log:
        with OWNED.spawn(["node", "tests/agent-modeling-live.cjs"], cwd=desktop, env=env,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8") as runner:
            for line in runner.stdout:
                log.write(line)
                log.flush()
                print(line, end="", flush=True)
            runner_code = runner.wait()
    summary_path = args.output / "summary.json"
    if summary_path.exists():
        summary = json.loads(summary_path.read_text())
        if any(row.get("audit", {}).get("model") for row in summary["results"]):
            try:
                reopener = launch_cad(args, ROOT / "tests/e2e/agent_modeling_reopen.FCMacro", env, args.output / "reopen.log")
                if reopener.wait(timeout=120):
                    raise RuntimeError("重开进程非零退出")
                reopened = json.loads((args.output / "reopened.json").read_text())
                for row in summary["results"]:
                    row["reopened"] = next(r for r in reopened if (r["case"], r["repetition"]) == (row["case"], row["repetition"]))
            except Exception as exc:
                summary["reopen_error"] = str(exc)
        for row in summary["results"]:
            classify(row)
            write_json(args.output / f"{row['case']}-{row['repetition']}" / "result.json", row)
        summary.update(summarize(summary["results"]))
        write_json(summary_path, summary)
    print(f"请把 {args.output} 的 summary.json、runner.log 和各轮记录交回；图片仅留本地，不提交仓库。", flush=True)
    sys.exit(runner_code or (1 if summary_path.exists() and summary["failed"] else 0))


if __name__ == "__main__":
    try:
        main()
    finally:
        OWNED.close()

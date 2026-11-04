"""独立只读检查真实 Agent 产物；参考条件不进入 Agent 的工程或提示词。"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import time
import traceback
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mcp import Client, StdioServerParameters


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def collect_tasks(state, project):
    # task.list 只返回最近100项；验收直接读取同一 SQLite，不能漏掉长对话前半段。
    with sqlite3.connect(f"file:{state / 'tasks.sqlite3'}?mode=ro", uri=True) as db:
        tasks = [json.loads(row[0]) for row in db.execute("SELECT record FROM tasks ORDER BY rowid")]
        tasks = [r for r in tasks if r["project"] == str(project)]
        for task in tasks:
            task["receipts"] = [json.loads(row[0]) for row in db.execute("SELECT record FROM receipts WHERE task_id=? ORDER BY rowid", (task["task_id"],))]
    return tasks


def current_receipts(receipts, document, body):
    saved = any(r["command"] == "host.model_save" and (r.get("result") or {}).get("document") == document
                and (r.get("result") or {}).get("outcome") == "committed" for r in receipts)
    checked = any(r["command"] == "host.check" and (r.get("result") or {}).get("document") == document
                  and (r.get("result") or {}).get("object_ref") == body
                  and (r.get("result") or {}).get("status") == "pass" for r in receipts)
    return {"saved_current_revision": saved, "self_check_current_revision": checked}


def input_was_read(receipts, users, delivery, sha256):
    if delivery in {"attachment", "vision"}:
        return any(im.get("sha256") == sha256 for e in users for im in e.get("images", []))
    if delivery in {"dimensions", "pdf"}:
        return any(sha256 in e["text"] and not e.get("images") for e in users)
    return any(r["command"] == "project.read_image" and (r.get("result") or {}).get("sha256") == sha256 for r in receipts)


async def inspect(args, tasks, evidence):
    evidence.update(accepted=False, scope="原生树、保存回执及有限尺寸/截面检查；完整图纸符合性另需目视复核",
                    agent_task_count=len(tasks), agent_self_checks=[], model=None)
    receipts = [r for t in tasks for r in t["receipts"]]
    conversation = args.output / "conversation.json"
    users = [e for e in json.loads(conversation.read_text()).get("events", []) if e["type"] == "user"] if conversation.exists() else []
    evidence["input_read"] = input_was_read(receipts, users, args.delivery, args.input_sha256)
    evidence["agent_self_checks"] = [r for r in receipts if r["command"] == "host.check"]
    evidence["failed_tools"] = [{"task_id": t["task_id"], "error": t.get("error"), "receipts": t["receipts"]}
                                for t in tasks if t["status"] != "complete"]
    params = StdioServerParameters(command=sys.executable, args=["-m", "gongke_app", "mcp", "--state-dir", str(args.state_dir),
        "--project", str(args.project)], cwd=str(ROOT), env={**os.environ, "PYTHONPATH": str(ROOT)})
    async with Client(params) as client:
        async def call(name, **arguments):
            response = await client.call_tool(name, {"host_id": "freecad", **arguments})
            with (args.output / "auditor-calls.jsonl").open("a", encoding="utf-8") as log:
                log.write(json.dumps({"tool": name, "arguments": arguments, "response": response.model_dump(mode="json")}, ensure_ascii=False) + "\n")
            if response.is_error:
                raise RuntimeError(str(response.structured_content or response.content))
            return response.structured_content["result"]

        context = await call("host.context")
        evidence["context"] = context
        target = args.project / (args.case + ".FCStd")
        docs = [d for d in context["documents"] if d["path"] and Path(d["path"]).resolve() == target]
        if len(docs) != 1:
            evidence["reason"] = "未找到约定输出文档；保留其他实际文档供排查"
            return evidence
        doc = docs[0]
        bodies = [o for o in doc["objects"] if o["kind"] == "PartDesign::Body"]
        if len(bodies) != 1:
            evidence["reason"] = "输出需包含一个原生 Body"
            return evidence
        document, body = doc["document"], bodies[0]["native_ref"]
        snapshot = await call("host.inspect", document=document, object_ref=body)
        evidence["snapshot"] = snapshot
        features = snapshot["features"]
        evidence["native_tree"] = (snapshot["state"] == "ready" and snapshot["solid_count"] == 1
            and any(f["type"] == "Sketcher::SketchObject" for f in features)
            and any(f["type"].startswith("PartDesign::") and f["type"] not in {"PartDesign::Body", "PartDesign::Feature"} for f in features)
            and not any(f["type"] in {"PartDesign::Feature", "Part::Feature"} for f in features))
        evidence.update(current_receipts(receipts, document, body))
        if target.is_file():
            with zipfile.ZipFile(target) as archive:
                evidence["archive_valid"] = archive.testzip() is None and "Document.xml" in archive.namelist()
            evidence["model"] = {"path": str(target), "bytes": target.stat().st_size, "sha256": hashlib.sha256(target.read_bytes()).hexdigest()}
        if args.case in {"p7", "p8"}:
            metric_path = args.study / "results/metrics.json"
            dimension_path = args.study / "dimensions.json"
            reference = json.loads(metric_path.read_text())["references"][args.case]
            evidence["reference"] = {"metrics_sha256": hashlib.sha256(metric_path.read_bytes()).hexdigest(),
                "dimensions_sha256": hashlib.sha256(dimension_path.read_bytes()).hexdigest(),
                "assumptions": json.loads(dimension_path.read_text())[args.case], "coordinate_policy": "输入约定轴向；未自动配准，坐标不一致需单独判读"}
            box = [(b-a)*1000 for a, b in zip(snapshot["bounds"]["min"], snapshot["bounds"]["max"])]
            evidence["volume_error_mm3"] = snapshot["volume"]*1e9 - reference["volume_mm3"]
            evidence["bbox_error_mm"] = [a-b for a, b in zip(box, reference["bbox_mm"])]
            conditions = json.loads((ROOT / "tests/fixtures/model_inspection/cases.json").read_text())[args.case]
            conditions += [{"id": "reference_section_"+z, "source": "既有独立 build123d 参考体；继承尺寸台账中的显式假设",
                "measurement": {"kind": "section_area", "plane": {"origin": [0, 0, float(z)/1000], "normal": [0, 0, 1]}},
                "expected": row["area_mm2"], "tolerance": .05, "unit": "mm^2"} for z, row in reference["sections_xy"].items()]
            evidence["independent_check"] = await call("host.check", document=document, object_ref=body, conditions=conditions)
            evidence["reference_pass"] = (evidence["independent_check"]["status"] == "pass"
                and abs(evidence["volume_error_mm3"]) <= .1 and max(map(abs, evidence["bbox_error_mm"])) <= .01)
        elif args.case in {"robot14", "robot13", "robot4"}:
            from tests.e2e.robot_drawing_check import check_robot
            evidence.update(await check_robot(args.case, snapshot, document, body, call))
        else:
            evidence["reference_pass"] = None
            record = json.loads((ROOT / "tests/fixtures/agent_modeling/p6-reading.json").read_text())
            evidence["requires_drawing_review"] = True
            evidence["provisional_bbox_comparison"] = {"actual_mm": [(b-a)*1000 for a,b in zip(snapshot["bounds"]["min"],snapshot["bounds"]["max"])],
                "candidate_mm": [record["values"][key] for key in ("overall_length", "overall_width", "overall_height")],
                "source_status": "候选读数/假设，不作为自动通过或失败的依据"}
            evidence["reason"] = "P6 源图顶部被截、部分数字模糊；构建与保存结果单独报告，图纸符合性待复核，不计自动成功"
        evidence["accepted"] = all(evidence.get(k) is True for k in
            ("input_read", "native_tree", "saved_current_revision", "archive_valid", "self_check_current_revision", "reference_pass"))
    return evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("state-dir", "project", "study", "output"):
        parser.add_argument("--"+name, type=Path, required=True)
    parser.add_argument("--case", choices=["p6", "p7", "p8", "robot14", "robot13", "robot4"], required=True)
    parser.add_argument("--delivery", choices=["attachment", "mcp", "dimensions", "vision", "pdf"], required=True)
    parser.add_argument("--input-sha256", required=True)
    args = parser.parse_args()
    deadline = time.monotonic() + 60
    while True:
        tasks = collect_tasks(args.state_dir, args.project)
        if not any(t["status"] in {"running", "queued"} for t in tasks):
            break
        if time.monotonic() >= deadline:
            dump(args.output / "agent-tasks.json", tasks)
            raise RuntimeError("Agent 已断开但工程任务仍在执行，不能宣告最终模型状态")
        time.sleep(.2)
    dump(args.output / "agent-tasks.json", tasks)
    with (args.output / "tool-calls.jsonl").open("w", encoding="utf-8") as log:
        for task in tasks:
            for receipt in task["receipts"]:
                log.write(json.dumps({"task_id": task["task_id"], "status": task["status"], **receipt}, ensure_ascii=False) + "\n")
    evidence = {"accepted": False}
    try:
        asyncio.run(inspect(args, tasks, evidence))
    except Exception:
        evidence.update(accepted=False, error=traceback.format_exc())
        raise
    finally:
        dump(args.output / "audit.json", evidence)


if __name__ == "__main__":
    main()

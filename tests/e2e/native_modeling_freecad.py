"""真实 MCP→应用执行器→HTTP→FreeCAD 主线程，从零建立 P7/P8。沙箱外运行，见 docs/native-modeling.md。"""
from __future__ import annotations
import argparse
import asyncio
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import traceback
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mcp import Client, StdioServerParameters
from tests.mcp_helpers import ServiceProcess
from tests.e2e.native_modeling_recipes import build
from tests.e2e.native_modeling_features import exercise

CASES = json.loads((ROOT / "tests/fixtures/model_inspection/cases.json").read_text(encoding="utf-8"))


async def journey(args, service, evidence):
    params = StdioServerParameters(command=sys.executable, args=["-m", "gongke_app", "mcp", "--state-dir", str(service.state),
        "--project", str(service.project), "--allow-writes"], cwd=str(ROOT), env={**os.environ, "GONGKE_FREECAD_SESSION": str(args.endpoint)})
    dimensions = json.loads((args.study / "dimensions.json").read_text(encoding="utf-8"))
    metrics = json.loads((args.study / "results/metrics.json").read_text(encoding="utf-8"))
    evidence["source"] = {"dimensions": dimensions, "dimensions_sha256": hashlib.sha256((args.study / "dimensions.json").read_bytes()).hexdigest(),
                          "metrics_sha256": hashlib.sha256((args.study / "results/metrics.json").read_bytes()).hexdigest()}
    async with Client(params) as client:
        async def call(name, arguments, *, fail=False):
            response = await client.call_tool(name, {"host_id": "freecad", **arguments})
            row = {"tool": name, "arguments": arguments, "response": response.model_dump(mode="json")}
            evidence["calls"].append(row)
            with (args.output / "calls.jsonl").open("a", encoding="utf-8") as log:
                log.write(json.dumps(row, ensure_ascii=False)+"\n")
            payload = response.structured_content or {}
            if fail:
                assert response.is_error or "error" in payload.get("result", {}), payload
                return payload
            assert not response.is_error and payload["status"] == "complete", payload
            result = payload["result"]
            assert "error" not in result, result
            return result
        context = await call("host.context", {})
        assert "model.new" in context["capabilities"], "桥接未加载新建模模块"
        for case in ("p7", "p8"):
            created = await call("host.model_new", {"host_instance": context["host_instance"], "name": "Body", "path": case+".FCStd", "operation_id": str(uuid4())})
            document, body = created["document"], created["body_ref"]
            async def write(tool, **fields):
                nonlocal document
                result = await call(tool, {"document": document, "operation_id": str(uuid4()), **fields})
                document = result["document"]
                return result
            async def sketch_feature(name, plane, offset, geometry, constraints, kind, length=None, **feature_options):
                sketch = await write("host.sketch", body_ref=body, name=name+"Sketch", support={"plane": plane, "offset": offset/1000}, geometry=geometry, constraints=constraints)
                feature = {"kind": kind, "sketch_ref": sketch["sketch_ref"], **feature_options}
                if length is not None:
                    feature["length"] = length/1000
                return await write("host.feature", body_ref=body, name=name, feature=feature)
            named = await build(case, dimensions[case]["values"], sketch_feature)
            async def inspect():
                return await call("host.inspect", {"document": document, "object_ref": body})
            snapshot = await inspect()
            assert snapshot["state"] == "ready" and snapshot["solid_count"] == 1, snapshot
            assert sum(f["type"] == "Sketcher::SketchObject" for f in snapshot["features"]) >= 5
            assert not any(f["type"] == "PartDesign::Feature" for f in snapshot["features"]), "不允许导入参考实体代替草图建模"
            ref = metrics["references"][case]
            assert abs(snapshot["volume"]*1e9-ref["volume_mm3"]) < 1e-4
            actual_box = [(b-a)*1000 for a, b in zip(snapshot["bounds"]["min"], snapshot["bounds"]["max"])]
            assert max(abs(a-b) for a, b in zip(actual_box, ref["bbox_mm"])) < 1e-5
            conditions = [*CASES[case]]
            for z, row in ref["sections_xy"].items():
                conditions.append({"id": "reference_section_"+z, "source": "独立 build123d 参考体 results/metrics.json；继承 dimensions.json 的显式假设",
                                   "measurement": {"kind": "section_area", "plane": {"origin": [0, 0, float(z)/1000], "normal": [0, 0, 1]}},
                                   "expected": row["area_mm2"], "tolerance": .001, "unit": "mm^2"})
            report = await call("host.check", {"document": document, "object_ref": body, "conditions": conditions})
            assert report["status"] == "pass", report
            evidence[case] = {"snapshot": snapshot, "report": report, "reference_volume_mm3": ref["volume_mm3"], "reference_bbox_mm": ref["bbox_mm"]}
            if case == "p7":
                # 制造真实特征错误变体→host.check 定位→工具改回；不是只核对原始成功体。
                old = document
                await write("host.feature_edit", feature_ref=named["tube_feature"], parameter="Length", value=.020)
                changed = await inspect()
                evidence[case]["changed_snapshot"] = changed
                assert abs(changed["bounds"]["max"][2]-.028) < 1e-10, changed["bounds"]
                # 筒延长 8 mm，只增加圆环体积；若留下实心封顶，这里必须失败。
                p = dimensions[case]["values"]
                added_volume = math.pi*((p["tube_outer_diameter"]/2000)**2-(p["tube_inner_diameter"]/2000)**2)*.008
                assert abs(changed["volume"]-snapshot["volume"]-added_volume) < 1e-12, changed["volume"]
                failed = await call("host.check", {"document": document, "object_ref": body, "conditions": CASES[case]})
                assert next(c for c in failed["checks"] if c["id"] == "tube_height")["status"] == "fail", failed
                await call("host.feature_edit", {"document": old, "operation_id": str(uuid4()), "feature_ref": named["tube_feature"], "parameter": "Length", "value": .012}, fail=True)
                await write("host.feature_edit", feature_ref=named["tube_feature"], parameter="Length", value=.012)
                repaired = await call("host.check", {"document": document, "object_ref": body, "conditions": conditions})
                assert repaired["status"] == "pass", repaired
                evidence[case]["correction"] = {"failed": failed, "repaired": repaired}
            saved = await write("host.model_save")
            operation = await call("host.model_operation", {"operation_id": saved["operation_id"]})
            assert operation["result"] == saved
            evidence[case]["saved"] = saved
        evidence["feature_acceptance"] = await exercise(call, context["host_instance"])
        # MCP 只读绑定必须在执行端拒绝，不仅隐藏清单。
    readonly = StdioServerParameters(command=sys.executable, args=["-m", "gongke_app", "mcp", "--state-dir", str(service.state), "--project", str(service.project)], cwd=str(ROOT))
    async with Client(readonly) as client:
        names = {t.name for t in (await client.list_tools()).tools}
        assert "host.feature" not in names and "host.check" in names
        blocked = await client.call_tool("host.rebuild", {"host_id": "freecad", "document": document, "operation_id": str(uuid4())})
        assert blocked.is_error
        evidence["read_only_refusal"] = blocked.model_dump(mode="json")
    evidence["status"] = "passed"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", type=Path, required=True)
    parser.add_argument("--study", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="必须为未使用目录")
    args = parser.parse_args()
    args.output = args.output.resolve(); args.endpoint = args.endpoint.resolve(); args.study = args.study.resolve()
    args.output.mkdir(parents=True, exist_ok=False)
    evidence = {"status": "failed", "calls": []}
    bootstrap = args.endpoint.parent / "bootstrap.json"
    boot = json.loads(bootstrap.read_text(encoding="utf-8"))
    assert Path(boot["root"]) == ROOT, boot
    for row in boot["sources"].values():
        assert hashlib.sha256(Path(row["path"]).read_bytes()).hexdigest() == row["sha256"], "宿主加载后源码已改变，请重启独立验收宿主"
    evidence["bootstrap"] = boot
    service = ServiceProcess(args.output, env={**os.environ, "GONGKE_FREECAD_SESSION": str(args.endpoint)})
    try:
        asyncio.run(journey(args, service, evidence))
    except BaseException:
        evidence["traceback"] = traceback.format_exc()
        raise
    finally:
        (args.output / "acceptance.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
        service.close()
    print("PASS: P7/P8 原生特征树、参考体尺寸/截面/体积、检查后修正、旧修订拒绝、只读开关；"+str(args.output))


if __name__ == "__main__":
    main()

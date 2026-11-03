"""配合屏幕验收逐段执行真实 MCP 建模；桌面须已打开 output/project。无模型 API 用量。"""
import argparse
import asyncio
import json
import os
from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mcp import Client, StdioServerParameters


async def run(output, phase):
    state_path = output / "journey.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    params = StdioServerParameters(command=sys.executable,
        args=["-m", "gongke_app", "mcp", "--state-dir", str(output / "user/state"),
              "--project", str(output / "project"), "--allow-writes"], cwd=str(ROOT), env=dict(os.environ))
    async with Client(params) as client:
        async def call(tool, **fields):
            response = await client.call_tool(tool, ({"host_id": "freecad", **fields} if tool.startswith("host.") else fields))
            payload = response.structured_content or {}
            with (output / "calls.jsonl").open("a") as stream:
                stream.write(json.dumps({"phase": phase, "tool": tool, "params": fields, "response": payload}, ensure_ascii=False)+"\n")
            assert not response.is_error and payload.get("status") == "complete", payload
            result = payload["result"]
            assert "error" not in result, result
            return result
        async def write(tool, **fields):
            result = await call(tool, document=state["document"], operation_id=str(uuid4()), **fields)
            state["document"] = result["document"]
            return result
        async def sketch(name, radius, offset):
            result = await write("host.sketch", body_ref=state["body"], name=name,
                support={"plane": "XY", "offset": offset},
                geometry=[{"kind": "circle", "center": [0, 0], "radius": r} for r in [radius, .008]], constraints=[])
            state["sketch"] = result["sketch_ref"]
        async def pad(name, length):
            result = await write("host.feature", body_ref=state["body"], name=name,
                feature={"kind": "pad", "sketch_ref": state["sketch"], "length": length})
            state["feature"] = result["feature_ref"]
        def condition(name, kind, selectors, expected):
            return {"id": name, "source": "验收设计：底板厚8 mm、凸台高10 mm、外径24 mm、通孔16 mm",
                    "measurement": {"kind": kind, "selectors": selectors}, "expected": expected,
                    "tolerance": .001, "unit": "mm"}
        height = condition("凸台高度", "plane_distance", [
            {"kind": "plane", "direction": [0, 0, 1], "offset": .008},
            {"kind": "plane", "direction": [0, 0, 1], "offset": .020 if phase != "repaired" else .018}], 10)
        if phase == "sketch":
            context = await call("host.context")
            result = await call("host.model_new", host_instance=context["host_instance"], name="VisualBody", path="visual_part.FCStd", operation_id=str(uuid4()))
            state.update(document=result["document"], body=result["body_ref"])
            await sketch("BaseSketch", .025, 0)
        elif phase == "base":
            await pad("BasePad", .008)
        elif phase == "tube-sketch":
            await sketch("TubeSketch", .012, .008)
        elif phase == "tube":
            await pad("TubePad", .012)
        elif phase in {"fail", "repaired"}:
            if phase == "repaired":
                await write("host.feature_edit", feature_ref=state["feature"], parameter="Length", value=.010)
            report = await call("host.check", document=state["document"], object_ref=state["body"], conditions=[height])
            assert report["status"] == ("pass" if phase == "repaired" else "fail"), report
        elif phase == "cylinder":
            report = await call("host.check", document=state["document"], object_ref=state["body"], conditions=[
                condition("凸台外径故意不符", "diameter", [{"kind": "cylinder", "radius": .012}], 22)])
            assert report["status"] == "fail", report
        elif phase == "section":
            report = await call("host.check", document=state["document"], object_ref=state["body"], conditions=[{
                "id": "环形截面积故意不符", "source": "验收故意错误面积1 mm^2", "measurement": {
                "kind": "section_area", "plane": {"origin": [0, 0, .014], "normal": [0, 0, 1]}},
                "expected": 1, "tolerance": .001, "unit": "mm^2"}])
            assert report["status"] == "fail" and report["checks"][0]["actual"]["locations"][0]["edges"], report
        elif phase == "save":
            await write("host.model_save")
        scene = await call("freecad.scene")
        assert scene["revision"] == state["document"]["revision"]
        (output / (phase + "-scene.json")).write_text(json.dumps(scene, ensure_ascii=False))
        if phase == "save":
            snapshot = await call("host.inspect", document=state["document"], object_ref=state["body"])
            body = next(o for o in scene["objects"] if o["id"] == state["body"])
            bounds = [(b-a)*1000 for a, b in zip(snapshot["bounds"]["min"], snapshot["bounds"]["max"])]
            assert all(abs(a-b) < 1e-6 for a, b in zip(bounds, [50, 50, 18]))
            assert len(body["faces"]) == len(snapshot["faces"])
            for mesh, face in zip(body["faces"], snapshot["faces"]):
                assert mesh["native_ref"] == face["native_ref"]
                assert mesh["triangles"]
                for point in mesh["vertices"]:
                    assert all(a*1000-1e-6 <= p <= b*1000+1e-6 for p, a, b in zip(point, snapshot["bounds"]["min"], snapshot["bounds"]["max"]))
                if face["kind"] == "plane":
                    # 三张环形面不能跨越通孔；检查每个三角形到轴心的最近距离。
                    import math
                    for indices in mesh["triangles"]:
                        points = [mesh["vertices"][i][:2] for i in indices]
                        crosses = [a[0]*b[1]-a[1]*b[0] for a, b in zip(points, points[1:] + points[:1])]
                        assert not (all(v >= 0 for v in crosses) or all(v <= 0 for v in crosses))
                        for a, b in zip(points, points[1:] + points[:1]):
                            delta = [b[i]-a[i] for i in range(2)]
                            t = max(0, min(1, -sum(a[i]*delta[i] for i in range(2))/sum(v*v for v in delta)))
                            assert math.hypot(*(a[i]+t*delta[i] for i in range(2))) > 7.8
            (output / "geometry-audit.json").write_text(json.dumps({"faces": len(body["faces"]), "bounds_mm": bounds, "finite_bounds": True, "annular_holes_preserved": True}, indent=2))
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2))
        print(phase, state["document"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("phase", choices=["sketch", "base", "tube-sketch", "tube", "fail", "cylinder", "section", "repaired", "save"])
    args = parser.parse_args()
    asyncio.run(run(args.output.resolve(), args.phase))

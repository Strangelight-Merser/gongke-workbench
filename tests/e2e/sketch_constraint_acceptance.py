"""真实应用执行器→HTTP→FreeCAD 回放；输出回执和每次错误后的读写健康证据。"""
from copy import deepcopy
import json
from pathlib import Path
import sys
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from gongke_app.commands import Commands
from gongke_app.hosts import Hosts
from gongke_app.project import Project


def exercise(output):
    project = Project.create(output / "project")
    commands = Commands(Hosts(output / "state"))
    results = []

    def call(method, **fields):
        started = time.monotonic()
        row = {"method": method, "params": {"host_id": "freecad", **fields}}
        try:
            row["result"] = commands.call(method, row["params"], project)
            return row["result"]
        except Exception as exc:
            row["exception"] = str(exc)
            raise
        finally:
            row["elapsed_seconds"] = time.monotonic() - started
            with (output / "calls.jsonl").open("a") as log:
                log.write(json.dumps(row, ensure_ascii=False) + "\n")

    fixture = json.loads((ROOT / "tests/fixtures/native_modeling/fixed-center.json").read_text())
    circle = [{"kind": "circle", "center": [.02, .03], "radius": .005}]
    fixed = {"kind": "fixed", "entities": [{"geometry": 0, "point": "center"}], "name": "Position"}
    cases = [("RecordedP7", fixture["sketch"], True)]
    arc = json.loads((ROOT / "tests/fixtures/native_modeling/clockwise-arc.json").read_text())
    cases.append(("ClockwiseArcRecorded", arc["sketch"], False))
    corrected = deepcopy(arc["sketch"])
    # 原调用还包含重复的两圆心水平关系；端点修复后应明确报冗余而非端点冲突。
    corrected["constraints"] = [c for i,c in enumerate(corrected["constraints"]) if i not in {6,8}]
    cases.append(("ClockwiseArc", corrected, True))
    for name, geometry, constraints, success in [
        ("WholeBlock", circle, [{"kind": "fixed", "entities": [{"geometry": 0}]}], True),
        ("PointXY", circle, [fixed], True),
        ("PointOnAxis", [{**circle[0], "center": [0, .03]}], [fixed], True),
        ("InvalidBlock", circle, [{"kind": "fixed", "entities": [{"geometry": 0}, {"geometry": 0}]}], False),
        ("InvalidPoint", circle, [{"kind": "fixed", "entities": [{"geometry": 0, "point": "start"}]}], False),
        ("InvalidRadius", circle, [{"kind": "radius", "entities": [{"geometry": 0, "point": "center"}], "value": .005}], False),
        ("SolverConflict", circle, [{"kind": "radius", "entities": [{"geometry": 0}], "value": value} for value in [.005, .01]], False),
    ]:
        cases.append((name, {"name": "Profile", "support": {"plane": "XY"}, "geometry": geometry, "constraints": constraints}, success))
    for name, sketch, success in cases:
        context = call("host.context")
        new = call("host.model_new", host_instance=context["host_instance"], name="Body", path=name+".FCStd", operation_id=str(uuid4()))
        assert new.get("outcome") == "committed", new
        operation = str(uuid4())
        result = call("host.sketch", document=new["document"], body_ref=new["body_ref"], operation_id=operation, **deepcopy(sketch))
        assert (result.get("outcome") == "committed") == success, result
        if name == "ClockwiseArcRecorded":
            solver = json.loads(result["error"]["message"])
            assert not solver["conflicting_constraints"] and solver["redundant_constraints"], solver
        if not success:
            assert result["error"]["outcome"] == "rolled_back", result
        # 原 ID 查询不重发写入；随后真实 context/save 证明主线程仍可工作。
        recovered = call("host.model_operation", operation_id=operation)
        assert recovered["state"] == "finished" and recovered["result"] == result, recovered
        context = call("host.context")
        document = next(d["document"] for d in context["documents"] if d["path"] == new["path"])
        if name in {"RecordedP7", "ClockwiseArc"}:
            feature = call("host.feature", document=document, operation_id=str(uuid4()), body_ref=new["body_ref"], name="Pad",
                           feature={"kind": "pad", "sketch_ref": result["sketch_ref"], "length": .008})
            assert feature.get("outcome") == "committed", feature
            document = feature["document"]
            snapshot = call("host.inspect", document=document, object_ref=new["body_ref"])
            assert snapshot["solid_count"] == 1 and snapshot["state"] == "ready", snapshot
        saved = call("host.model_save", document=document, operation_id=str(uuid4()))
        assert saved.get("outcome") == "committed", saved
        results.append({"case": name, "expected_success": success, "result": result, "bridge_read_write_alive": True})
        (output / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2)+"\n")
    return results


if __name__ == "__main__":
    output = Path(sys.argv[1]).resolve()
    report = {"passed": False}
    try:
        report["results"] = exercise(output)
        report["passed"] = True
    except Exception as exc:
        report["error"] = str(exc)
        raise
    finally:
        (output / "summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n")

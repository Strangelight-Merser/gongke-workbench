"""补充原生特征验收，全部使用公开工具；几何断言来自解析体积。"""
import math
from uuid import uuid4


async def exercise(call, host_instance):
    output = {}
    for kind in ("revolve", "hole", "fillet", "chamfer", "mirror", "linear_pattern", "polar_pattern"):
        result = await call("host.model_new", {"host_instance": host_instance, "operation_id": str(uuid4()), "name": "Body", "path": "features/"+kind+".FCStd"})
        document, body = result["document"], result["body_ref"]
        async def write(name, **fields):
            nonlocal document
            result = await call(name, {"document": document, "operation_id": str(uuid4()), **fields})
            document = result["document"]
            return result
        async def sketch(name, geometry, constraints=(), offset=0):
            return await write("host.sketch", body_ref=body, name=name, support={"plane": "XY", "offset": offset}, geometry=geometry, constraints=list(constraints))
        async def feature(name, data):
            return await write("host.feature", body_ref=body, name=name, feature=data)
        async def inspect():
            return await call("host.inspect", {"document": document, "object_ref": body})
        if kind == "revolve":
            profile = await sketch("Profile", [{"kind": "rectangle", "start": [.005, 0], "end": [.010, .020]}])
            made = await feature("Revolve", {"kind": kind, "sketch_ref": profile["sketch_ref"], "axis": "vertical", "angle": 2*math.pi})
            expected = math.pi*(.010**2-.005**2)*.020
        else:
            profile = await sketch("BaseProfile", [{"kind": "rectangle", "start": [-.020, -.015], "end": [.020, .015]}])
            base = await feature("Base", {"kind": "pad", "sketch_ref": profile["sketch_ref"], "length": .005})
            expected = .040*.030*.005
            if kind == "hole":
                hole = await sketch("HoleProfile", [{"kind": "circle", "center": [0, 0], "radius": .002}],
                                    [{"kind": "diameter", "entities": [{"geometry": 0}], "value": .004, "name": "HoleDiameter"}], .005)
                made = await feature("Hole", {"kind": kind, "sketch_ref": hole["sketch_ref"], "length": .005, "diameter": .004})
                expected -= math.pi*.002**2*.005
            elif kind in {"fillet", "chamfer"}:
                snapshot = await inspect()
                edge = next(e for e in snapshot["edges"] if e["kind"] == "line")
                made = await feature("DressUp", {"kind": kind, "edges": [edge["native_ref"]], "radius" if kind == "fillet" else "size": .0005})
                expected = None
            else:
                boss = await sketch("BossProfile", [{"kind": "circle", "center": [.008, 0], "radius": .002}], offset=.005)
                seed = await feature("Boss", {"kind": "pad", "sketch_ref": boss["sketch_ref"], "length": .003})
                data = {"kind": kind, "features": [seed["feature_ref"]]}
                if kind == "mirror": data["plane"] = "YZ"; count = 2
                elif kind == "linear_pattern": data.update(axis="Y", spacing=.006, count=3); count = 3
                else: data.update(axis="Z", angle=2*math.pi, count=4); count = 4
                made = await feature("Pattern", data)
                expected += count*math.pi*.002**2*.003
        snapshot = await inspect()
        assert snapshot["state"] == "ready" and snapshot["solid_count"] == 1, snapshot
        if expected is not None:
            assert abs(snapshot["volume"]-expected) < 1e-12, (kind, snapshot["volume"], expected)
        else:
            assert 0 < snapshot["volume"] < .040*.030*.005
        if kind == "hole":
            # 面引用支持、批量追加约束、原生删除拒绝/删除成功与工作副本。
            top = next(f for f in snapshot["faces"] if f["kind"] == "plane" and abs(f["point"][2]-.005) < 1e-10)
            face_sketch = await write("host.sketch", body_ref=body, name="FaceSketch", support={"face_ref": top["native_ref"]}, geometry=[], constraints=[])
            assert abs(abs(face_sketch["frame"]["normal"][2])-1) < 1e-10
            await write("host.sketch", body_ref=body, sketch_ref=face_sketch["sketch_ref"], geometry=[{"kind": "line", "start": [0, 0], "end": [.001, 0], "construction": True}],
                        constraints=[{"kind": "horizontal", "entities": [{"geometry": 0}]}])
            await call("host.feature_delete", {"document": document, "operation_id": str(uuid4()), "feature_ref": made["feature_ref"]}, fail=True)
            context = await call("host.context", {})
            document = next(d["document"] for d in context["documents"] if d["document"]["document_id"] == document["document_id"])
            await write("host.feature_delete", feature_ref=face_sketch["sketch_ref"])
            await write("host.feature_delete", feature_ref=made["feature_ref"])
            restored = await inspect()
            assert abs(restored["volume"]-.040*.030*.005) < 1e-12
            await write("host.model_save")
            copy = await write("host.model_copy", path="features/hole_copy.FCStd")
            assert copy["path"].endswith("hole_copy.FCStd")
        saved = await write("host.model_save")
        output[kind] = {"snapshot": snapshot, "expected_volume": expected, "saved": saved}
    return output

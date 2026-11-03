"""截面检查沿原生截交边定位，不能把辅助平面当成有限面。"""
from gongke_app.inspection import measure


def test_section_locations_preserve_native_contours():
    document = {"host_instance": "test", "document_id": "part", "revision": 3, "configuration": ""}
    snapshot = {"document": document, "object_ref": "Body", "state": "ready"}
    plane = {"origin": [0, 0, .014], "normal": [0, 0, 1]}
    edges = [{"native_ref": "section.Edge1", "samples": [[.012, 0, .014], [0, .012, .014]]}]
    result = measure(snapshot, {"kind": "section_area", "plane": plane},
                     lambda p: {"document": document, "plane": p, "status": "ok", "area": .00025, "edges": edges})
    assert result["value"] == .00025
    assert result["locations"] == [{"object_ref": "Body", "plane": plane, "edges": edges}]

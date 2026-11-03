"""官方 MCP SDK 验证修订检查；合成采集不作为 CAD 实机证据。"""
import asyncio
from copy import deepcopy
from mcp import Client

from gongke_core.revision_case import inspect_revision
from tests.test_mcp_server import service, client_params


def sample():
    """明确选定一个教学直径，两个图纸显示实例；不依赖用户文件或 FreeCAD。"""
    path = "/课程 工程/教学轴.FCStd"
    signature = [{"name": "radius_middle", "type": "DistanceY", "driving": True}]
    case = {
        "schema_version": 1, "case_id": "protocol-synthetic-revision",
        "document": {"path": path, "body": "Rotor", "sketch": "Outline", "revolution": "Turned",
                     "structure_signature": signature},
        "target": {"radius_constraint": "radius_middle", "segment_index": 1},
        "pages": ["Sheet"],
        "annotations": [{"page": "Sheet", "view": view, "dimension": dim, "target": "diameter"}
                        for view, dim in (("Front", "DFront"), ("Back", "DBack"))],
    }
    views = []
    for view, dim in (("Front", "DFront"), ("Back", "DBack")):
        views.append({"name": view, "state": [], "sources": [{"path": path, "object": "Rotor"}],
                      "dimensions": [{"name": dim, "type": "Diameter", "measurement_m": .038,
                                      "raw_value": 38.0, "raw_unit": "mm", "measure_type": "Projected",
                                      "display_text": "⌀38.00 mm", "format_spec": "⌀%.2w",
                                      "display_unit": "mm", "precision": 2, "arbitrary": False, "valid": True,
                                      "references2d": [{"object": view, "subelements": ["Edge5"]}],
                                      "references3d": [], "reference_status": "valid", "state": [], "issues": [],
                                      "over_tolerance_m": 0, "under_tolerance_m": 0}]})
    capture = {
        "host": "freecad", "session_id": "synthetic-session", "document": {"path": path},
        "geometry": {"supported": True, "body_name": "Rotor", "sketch": "Outline", "revolution": "Turned",
                     "structure_signature": deepcopy(signature), "segments": [
                         {"length_m": .05, "diameter_m": .03, "radius_constraint": "radius_left"},
                         {"length_m": .1, "diameter_m": .038, "radius_constraint": "radius_middle"},
                         {"length_m": .05, "diameter_m": .03, "radius_constraint": "radius_right"}]},
        "drawing": {"coverage": {"status": "complete", "scope": "selected_pages"}, "issues": [],
                    "pages": [{"name": "Sheet", "state": [], "unknown_objects": [], "views": views}]},
    }
    return case, capture


def test_official_sdk_revision_retains_provenance_and_detects_stale_drawing(service):
    async def journey():
        async with Client(client_params(service, write=False)) as client:
            tools = {t.name: t for t in (await client.list_tools()).tools}
            assert tools["revision.inspect"].annotations.read_only_hint is True
            assert tools["revision.inspect"].input_schema["required"] == ["case"]
            case, capture = sample()
            first = await client.call_tool("revision.inspect", {"case": case, "capture": capture})
            assert not first.is_error
            report = first.structured_content["result"]
            assert report == inspect_revision(case, capture=capture)
            assert report["source_mode"] == "recorded_capture"
            assert report["drawing_review"]["status"] == "pass"
            assert report["calculation"]["numerical_status"] == "unknown"
            assert all(c["status"] == "unavailable" for c in report["calculation"]["checks"])
            assert report["modification_eligibility"]["allowed"] is False
            capture["drawing"]["pages"][0]["views"][1]["dimensions"][0]["arbitrary"] = True
            second = await client.call_tool("revision.inspect", {"case": case, "capture": capture, "previous": report})
            assert not second.is_error
            result = second.structured_content["result"]
            assert result["drawing_review"]["status"] == "fail"
            assert result["applicability"]["previous"]["status"] == "stale"
            assert result["modification_eligibility"]["allowed"] is False
            invalid = await client.call_tool("revision.inspect", {"case": {}})
            assert invalid.is_error
    asyncio.run(journey())

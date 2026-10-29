"""官方 MCP SDK 的真实 stdio 验收；采集数据是合成契约样例，不是 CAD 实机证据。

安装项目 dev 依赖后运行。本门禁缺 SDK 即失败，不能用 skip 代替协议验收。
"""

import asyncio
from copy import deepcopy
import io
import json
from pathlib import Path
import sys

import pytest
from mcp import Client, StdioServerParameters
from mcp.shared.exceptions import MCPError

from gongke_core import mcp_server
from gongke_core.revision_case import inspect_revision


ROOT = Path(__file__).resolve().parents[1]
BATCH_NAMES = {
    "get_task_schema", "get_example_task", "validate_task", "run_design", "explore_parameter",
    "get_report", "lookup_standard", "generate_files", "check_drawings",
}


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


def test_profiles_partition_the_actual_dispatch_not_only_the_listing():
    native, batch, all_tools = (mcp_server.Server(profile) for profile in ("native", "batch", "all"))
    native_names, batch_names = set(native.by_name), set(batch.by_name)
    assert batch_names == BATCH_NAMES
    assert native_names.isdisjoint(batch_names)
    assert native_names | batch_names == set(all_tools.by_name)
    assert "inspect_revision" in native_names
    assert {"get_project_context", "read_engineering_object", "apply_change"} <= native_names
    for server, names in ((native, batch_names), (batch, native_names)):
        for name in names:
            result = server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name}})
            assert result["error"]["code"] == -32602


def test_invalid_profile_and_stdio_serve_selection():
    with pytest.raises(ValueError, match="profile"):
        mcp_server.Server("unknown")
    output = io.StringIO()
    mcp_server.serve(io.StringIO('{"jsonrpc":"2.0","id":1,"method":"tools/list"}\n'), output, profile="batch")
    assert {t["name"] for t in json.loads(output.getvalue())["result"]["tools"]} == BATCH_NAMES


def test_tool_calls_same_use_case_and_retains_explicit_offline_provenance():
    case, capture = sample()
    expected = inspect_revision(case, capture=capture)
    result = mcp_server.Server("native").handle({
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "inspect_revision", "arguments": {"case": case, "capture": capture}},
    })["result"]
    assert result["isError"] is False
    assert result["structuredContent"] == expected
    assert json.loads(result["content"][0]["text"]) == expected
    assert expected["source_mode"] == "recorded_capture"
    assert expected["modification_eligibility"]["allowed"] is False


def test_official_sdk_lists_profiles_calls_revision_and_detects_stale_drawing():
    async def journey():
        params = StdioServerParameters(command=sys.executable,
                                       args=["-m", "gongke_core", "mcp", "--profile", "native"], cwd=str(ROOT))
        async with Client(params) as client:
            tools = {tool.name: tool for tool in (await client.list_tools()).tools}
            assert tools.keys().isdisjoint(BATCH_NAMES)
            assert tools["inspect_revision"].annotations.read_only_hint is True
            assert tools["inspect_revision"].input_schema["required"] == ["case"]
            with pytest.raises(MCPError) as error:
                await client.call_tool("run_design", {"task": {}})
            assert error.value.code == -32602
            case, capture = sample()
            first = await client.call_tool("inspect_revision", {"case": case, "capture": capture})
            assert first.is_error is False
            report = first.structured_content
            assert report == inspect_revision(case, capture=capture)
            assert report["drawing_review"]["status"] == "pass"
            assert report["calculation"]["numerical_status"] == "unknown"
            assert all(c["status"] == "unavailable" for c in report["calculation"]["checks"])
            capture["drawing"]["pages"][0]["views"][1]["dimensions"][0]["arbitrary"] = True
            second = await client.call_tool("inspect_revision", {"case": case, "capture": capture, "previous": report})
            assert second.is_error is False
            assert second.structured_content["drawing_review"]["status"] == "fail"
            assert second.structured_content["applicability"]["previous"]["status"] == "stale"
            assert second.structured_content["modification_eligibility"]["allowed"] is False
            invalid = await client.call_tool("inspect_revision", {"case": {}})
            assert invalid.is_error is True
        batch_params = StdioServerParameters(command=sys.executable,
                                             args=["-m", "gongke_core", "mcp", "--profile", "batch"], cwd=str(ROOT))
        async with Client(batch_params) as client:
            assert {tool.name for tool in (await client.list_tools()).tools} == BATCH_NAMES
            with pytest.raises(MCPError):
                await client.call_tool("inspect_revision", {"case": {}})

    asyncio.run(journey())

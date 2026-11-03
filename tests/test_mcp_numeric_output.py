"""复现 dsh 拒收 CAD 负零：真实服务/MCP 边界规范化，原始回执保留。"""
import asyncio
from copy import deepcopy
import json
import math
import sys

from mcp import Client, StdioServerParameters
from gongke_app.connection import ConnectionServer
from gongke_app.mcp_server import normalize_zero
from gongke_app.service import Application
from tests.mcp_helpers import ROOT


def test_normalization_preserves_nonzero_values_and_original_data():
    original = {"point": [-0.0, 0.0, -1e-20, 5], "label": "-0.0", "flag": False}
    result = normalize_zero(original)
    assert math.copysign(1, original["point"][0]) == -1
    assert math.copysign(1, result["point"][0]) == 1
    assert result == original and result["label"] == "-0.0" and result["flag"] is False


def test_mcp_text_and_structured_result_have_positive_zero_but_receipt_is_unchanged(tmp_path, monkeypatch):
    app = Application(tmp_path / "state")
    app.dispatch("project.create", {"path": str(tmp_path / "project")})
    server = ConnectionServer(app, tmp_path / "state")
    document = {"host_instance": "instance", "document_id": "doc", "revision": 1, "configuration": ""}
    snapshot = {"document": document, "object_ref": "Body", "state": "ready",
                "faces": [{"point": [-0.0, .01, 0.0], "direction": [0.0, -0.0, 1.0]}]}
    monkeypatch.setattr("gongke_app.hosts.native_client.call", lambda *a, **kw: deepcopy(snapshot))
    async def journey():
        params = StdioServerParameters(command=sys.executable, args=["-m", "gongke_app", "mcp", "--state-dir",
            str(tmp_path / "state"), "--project", str(tmp_path / "project")], cwd=str(ROOT))
        async with Client(params) as client:
            response = await client.call_tool("host.inspect", {"host_id": "freecad", "document": document, "object_ref": "Body"})
            assert not response.is_error
            result = response.structured_content
            for value in (result, json.loads(response.content[0].text)):
                assert math.copysign(1, value["result"]["faces"][0]["point"][0]) == 1
                assert math.copysign(1, value["result"]["faces"][0]["direction"][1]) == 1
            raw = app.tasks.get(result["task_id"])["receipts"][0]["result"]
            assert math.copysign(1, raw["faces"][0]["point"][0]) == -1
    try:
        asyncio.run(journey())
    finally:
        server.close()
        app.close()

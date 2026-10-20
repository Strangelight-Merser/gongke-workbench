"""MCP 服务器：按 JSON-RPC 2.0 / MCP 规范收发消息。装有官方 mcp SDK 时再用它的客户端实测一遍。"""

import asyncio
import json
import subprocess
import sys
from pathlib import Path

import pytest

from gongke_core import mcp_server

ROOT = Path(__file__).resolve().parents[1]


def _rpc(lines):
    p = subprocess.run([sys.executable, "-m", "gongke_core", "mcp"], input="\n".join(json.dumps(m) for m in lines) + "\n",
                       capture_output=True, text=True, encoding="utf-8", cwd=ROOT, timeout=120)
    return [json.loads(x) for x in p.stdout.splitlines()]


def test_protocol_over_stdio():
    out = _rpc([
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
         "params": {"name": "run_design", "arguments": {"task": {"conveyor": {"belt_pull_N": 3000, "belt_speed_m_s": 1.2,
                                                                              "drum_diameter_mm": 350}}}}},
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "run_design", "arguments": {"task": {}}}},
        {"jsonrpc": "2.0", "id": 5, "method": "nope"},
    ])
    assert [m["id"] for m in out] == [1, 2, 3, 4, 5]  # 通知没有响应
    assert out[0]["result"]["protocolVersion"] == "2025-06-18"
    tools = {t["name"]: t for t in out[1]["result"]["tools"]}
    assert {"run_design", "explore_parameter", "generate_files", "lookup_standard", "check_drawings"} <= set(tools)
    assert all(t["inputSchema"]["type"] == "object" for t in tools.values())
    r = out[2]["result"]
    assert r["isError"] is False and r["structuredContent"]["ok"] is True
    assert json.loads(r["content"][0]["text"])["motor"]["model"].startswith("Y")
    assert out[3]["result"]["isError"] is True and "conveyor" in out[3]["result"]["content"][0]["text"]
    assert out[4]["error"]["code"] == -32601


def test_unknown_tool_and_bad_arguments():
    s = mcp_server.Server()
    r = s.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "x"}})
    assert r["error"]["code"] == -32602
    r = s.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "lookup_standard", "arguments": {"bad": 1}}})
    assert r["result"]["isError"] is True


def test_official_sdk_client():
    mcp = pytest.importorskip("mcp")
    from mcp.client.stdio import stdio_client

    async def main():
        params = mcp.StdioServerParameters(command=sys.executable, args=["-m", "gongke_core", "mcp"], cwd=str(ROOT))
        async with stdio_client(params) as (r, w):
            async with mcp.ClientSession(r, w) as s:
                await s.initialize()
                names = [t.name for t in (await s.list_tools()).tools]
                ex = await s.call_tool("get_example_task", {"scheme": "vbelt"})
                task = json.loads(ex.content[0].text)
                res = await s.call_tool("explore_parameter", {"task": task, "param": "vbelt.ratio", "values": [2.0, 3.0]})
                return names, json.loads(res.content[0].text)

    names, res = asyncio.run(main())
    assert "run_design" in names
    assert [r["value"] for r in res["results"]] == [2.0, 3.0] and all(r["ok"] for r in res["results"])

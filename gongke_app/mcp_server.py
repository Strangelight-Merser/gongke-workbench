"""官方 MCP SDK stdio 入口，只转发到绑定的应用工程。"""
from __future__ import annotations

import asyncio
import json
from uuid import uuid4

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import CallToolResult, ListToolsResult, TextContent, Tool

from gongke_app import __version__


async def call_bound(connection, binding, method, arguments):
    task_id = uuid4().hex
    try:
        await asyncio.to_thread(connection.request, "call", binding_id=binding["binding_id"],
                                method=method, params=arguments, task_id=task_id)
    except (OSError, TimeoutError):
        # 请求可能已被接受：查询既定任务 ID，不重发命令或换 ID。
        await asyncio.to_thread(connection.request, "task", binding_id=binding["binding_id"], task_id=task_id)
    try:
        while True:
            record = await asyncio.to_thread(connection.request, "task", binding_id=binding["binding_id"], task_id=task_id)
            if record["status"] not in {"queued", "running"}:
                result = record.get("result", {"error": record.get("error", record["stage"])})
                return {"task_id": task_id, "project": binding["project"], "status": record["status"], "result": result}
            await asyncio.sleep(0.1)
    except asyncio.CancelledError:
        await asyncio.shield(asyncio.to_thread(connection.request, "cancel", binding_id=binding["binding_id"], task_id=task_id))
        raise


def create_server(connection, binding):
    async def list_tools(ctx, params):
        rows = await asyncio.to_thread(connection.request, "tools", binding_id=binding["binding_id"])
        return ListToolsResult(tools=[Tool.model_validate(row) for row in rows])

    async def call_tool(ctx, params):
        try:
            result = await call_bound(connection, binding, params.name, params.arguments or {})
            failed = result["status"] in {"failed", "interrupted", "canceled"}
        except Exception as exc:
            result, failed = {"error": str(exc), "project": binding["project"]}, True
        return CallToolResult(content=[TextContent(type="text", text=json.dumps(result, ensure_ascii=False, allow_nan=False))],
                              structured_content=result, is_error=failed)

    return Server("gongke-workbench", version=__version__, on_list_tools=list_tools, on_call_tool=call_tool,
                  instructions="操作绑定的桌面工程；先读取 project.current。原生写入前另存工作副本；保留未通过项和来源缺口。写入未知时查询原操作，不换 ID 重发。切换工程后重新连接。")


async def serve(connection, binding):
    server = create_server(connection, binding)
    async with stdio_server() as (reader, writer):
        await server.run(reader, writer, server.create_initialization_options())

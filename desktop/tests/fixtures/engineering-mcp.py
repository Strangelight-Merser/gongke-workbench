"""ACP 联调替身：MCP 传输极简，读工程和计算使用真实 Application。无写工具。"""
import json
import os
from pathlib import Path
import sys
import tempfile

from gongke_app.service import Application

app = Application(Path(tempfile.mkdtemp(prefix="gongke-acp-mcp-")))
app.dispatch("project.open", {"path": os.environ["GONGKE_PROJECT"]})
for line in sys.stdin:
    request = json.loads(line)
    if "id" not in request:
        continue
    try:
        method, params = request["method"], request.get("params", {})
        if method == "initialize":
            result = {"protocolVersion": params["protocolVersion"], "capabilities": {"tools": {}}, "serverInfo": {"name": "gongke-acp-test", "version": "1.0"}}
        elif method == "tools/list":
            result = {"tools": [{"name": name, "description": description, "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}}
                                for name, description in [("project_current", "读取当前工程和已保存任务书。"), ("design_calculate", "按当前已保存任务书计算传动方案、电机及轴校核，不修改工程。")]]}
        elif method == "tools/call":
            commands = {"project_current": "project.current", "design_calculate": "design.calculate"}
            value = app.dispatch(commands[params["name"]], params.get("arguments", {}))
            result = {"content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False)}]}
        elif method in {"resources/list", "prompts/list"}:
            result = {"resources" if method == "resources/list" else "prompts": []}
        elif method == "ping":
            result = {}
        else:
            raise ValueError("未知方法：" + method)
        response = {"jsonrpc": "2.0", "id": request["id"], "result": result}
    except Exception as exc:
        response = {"jsonrpc": "2.0", "id": request["id"], "error": {"code": -32603, "message": str(exc)}}
    print(json.dumps(response, ensure_ascii=False), flush=True)
app.close()

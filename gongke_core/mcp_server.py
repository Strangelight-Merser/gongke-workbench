"""MCP（Model Context Protocol）服务器：让 AI agent 直接调用工科工作台的设计能力，不需要操作图形界面。

    python -m gongke_core mcp

通过标准输入输出（stdio）收发 JSON-RPC 2.0 消息（每行一条），只用标准库实现，FreeCAD 自带的 Python 也能运行。
各工具是 `gongke_core.api` 中函数的薄包装，与 FreeCAD 工作台、命令行功能一致。
"""

from __future__ import annotations

import json
import sys
import traceback
from typing import Any, Callable

from gongke_core import api

SERVER_INFO = {"name": "gongke-workbench", "title": "工科工作台", "version": "0.1.0"}
PROTOCOL_VERSIONS = ["2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05"]

INSTRUCTIONS = """工科工作台：机械设计课程设计（带式输送机传动装置）的设计计算、说明书和工程图。
典型流程：get_task_schema 或 get_example_task 了解任务书格式 → run_design 计算并查看校核结论
→ 需要比较方案时用 explore_parameter → 用 get_report 读计算过程 → generate_files 输出说明书、DXF/PDF 图纸和三维模型。
任务书单位：力 N、长度 mm、速度 m/s、转速 r/min；结果中应力为 MPa、功率 kW。"""

_TASK = {"type": "object", "description": "任务书（结构见 get_task_schema）"}


def _tool(name: str, title: str, description: str, props: dict, required: list[str], fn: Callable[..., Any],
          read_only: bool = True) -> dict:
    return {"name": name, "title": title, "description": description,
            "inputSchema": {"type": "object", "properties": props, "required": required},
            "annotations": {"readOnlyHint": read_only, "openWorldHint": False}, "_fn": fn}


TOOLS = [
    _tool("get_task_schema", "任务书格式",
          "返回任务书的 JSON Schema：每个字段的含义、单位、默认值和可选值（传动方案、齿轮材料等）。",
          {}, [], lambda: api.task_schema()),
    _tool("get_example_task", "示例任务书",
          "返回某种传动方案的示例任务书，可在其基础上修改参数。scheme：coupling（二级圆柱齿轮）、vbelt（V 带 + 二级圆柱齿轮）、"
          "bevel（圆锥-圆柱齿轮）、worm（蜗杆）、single（V 带 + 一级圆柱齿轮）。",
          {"scheme": {"enum": list(api.SCHEMES), "default": "coupling"}}, [],
          lambda scheme="coupling": api.example_task(scheme)),
    _tool("validate_task", "检查任务书", "检查任务书的字段、类型和取值范围，返回错误列表（空表示无误）。",
          {"task": _TASK}, ["task"], lambda task: {"errors": api.validate(task)}),
    _tool("run_design", "设计计算",
          "完成全部设计计算：选电动机、分配传动比、设计各级齿轮（或 V 带、锥齿轮、蜗杆）、轴的结构和强度/疲劳/刚度校核、"
          "轴承寿命、键、联轴器、箱体尺寸。返回结果摘要、全部校核项和未通过项（failed）。约 0.1～0.5 秒。",
          {"task": _TASK}, ["task"], lambda task: api.design(task)),
    _tool("explore_parameter", "多方案对比",
          "把一个参数依次取多个值分别设计，返回每个方案的主要指标（电动机、模数、齿数、中心距、强度利用率 σ/[σ]、"
          "最大轴径、最短轴承寿命、未通过项），用于选择参数。param 为点号路径，如 ratio_split、gears.high.material1、"
          "gears.low.phi_d、scheme、motor_sync_speed_rpm。",
          {"task": _TASK, "param": {"type": "string"}, "values": {"type": "array", "minItems": 1, "maxItems": 20}},
          ["task", "param", "values"], lambda task, param, values: api.explore(task, param, values)),
    _tool("get_report", "计算说明书",
          "返回计算说明书的 Markdown 文本（每步计算的公式、代入值和结论）。chapter 为章标题中的关键字（如“低速级”“Ⅱ轴”“轴承”），"
          "不给出时返回全文。返回值中的 chapters 是章目录。",
          {"task": _TASK, "chapter": {"type": "string"}}, ["task"],
          lambda task, chapter=None: api.report(task, chapter)),
    _tool("lookup_standard", "查标准件和材料",
          "查询本项目收录的标准件和材料数据。kind 与 params：motor {power_kw, sync_rpm}（不给 power_kw 时列出全部型号）；"
          "bearing {bore_mm, type: deep_groove|tapered}；key {shaft_d_mm}；modules {series: 1|2|bevel|worm}；"
          "gear_materials {}；worm_wheel_materials {}；form_factors {zv}。",
          {"kind": {"enum": ["motor", "bearing", "key", "modules", "gear_materials", "worm_wheel_materials", "form_factors"]},
           "params": {"type": "object", "default": {}}},
          ["kind"], lambda kind, params=None: api.lookup(kind, **(params or {}))),
    _tool("generate_files", "生成文件",
          "按任务书生成文件到 out_dir：summary.json、report.md 和 report.docx（计算说明书）、drawings/（装配图和零件图 DXF、"
          "SVG 预览、整套 drawings.pdf）；step=true 时生成三维装配体 reducer_assembly.step（需要 build123d，约 1 分钟）；"
          "fem=true 时用 CalculiX 复核轴的刚度和齿根应力（需要 ccx 和 gmsh）。返回生成的文件列表。",
          {"task": _TASK, "out_dir": {"type": "string", "description": "输出目录（绝对路径）"},
           "docx": {"type": "boolean", "default": True}, "drawings": {"type": "boolean", "default": True},
           "step": {"type": "boolean", "default": False}, "full_teeth": {"type": "boolean", "default": False},
           "fem": {"type": "boolean", "default": False}},
          ["task", "out_dir"],
          lambda task, out_dir, docx=True, drawings=True, step=False, full_teeth=False, fem=False: api.generate(
              task, out_dir, report_docx=docx, drawings=drawings, step=step, full_teeth=full_teeth, fem=fem),
          read_only=False),
    _tool("check_drawings", "检查图纸重叠",
          "检查 DXF 工程图中文字互相重叠、图线（轮廓线、点画线、尺寸线）穿过文字的位置。path 为某张 DXF 或 generate_files "
          "输出的 drawings 目录（绝对路径）。返回问题总数和每张图的问题列表（类型、文字内容、图纸坐标 mm），总数为 0 表示无重叠。",
          {"path": {"type": "string", "description": "DXF 文件或图纸目录（绝对路径）"}}, ["path"],
          lambda path: api.check_drawings(path)),
]
_BY_NAME = {t["name"]: t for t in TOOLS}


def _public(t: dict) -> dict:
    return {k: v for k, v in t.items() if not k.startswith("_")}


class Server:
    def __init__(self):
        self.protocol = PROTOCOL_VERSIONS[0]

    def handle(self, msg: dict) -> dict | None:
        """处理一条 JSON-RPC 消息，返回响应（通知返回 None）。"""
        method, mid = msg.get("method"), msg.get("id")
        if mid is None:  # 通知（notifications/initialized、notifications/cancelled 等）
            return None
        try:
            result = self._dispatch(method, msg.get("params") or {})
        except _RpcError as e:
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": e.code, "message": str(e)}}
        return {"jsonrpc": "2.0", "id": mid, "result": result}

    def _dispatch(self, method: str, params: dict) -> dict:
        if method == "initialize":
            want = params.get("protocolVersion")
            self.protocol = want if want in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0]
            return {"protocolVersion": self.protocol, "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": SERVER_INFO, "instructions": INSTRUCTIONS}
        if method == "ping":
            return {}
        if method == "tools/list":
            return {"tools": [_public(t) for t in TOOLS]}
        if method == "tools/call":
            return self._call(params.get("name"), params.get("arguments") or {})
        raise _RpcError(-32601, f"Method not found: {method}")

    def _call(self, name: str, args: dict) -> dict:
        tool = _BY_NAME.get(name)
        if tool is None:
            raise _RpcError(-32602, f"Unknown tool: {name}")
        try:
            out = tool["_fn"](**args)
        except TypeError as e:  # 参数名不对
            return _error_result(f"参数错误：{e}")
        except (api.TaskError, ValueError, KeyError) as e:
            return _error_result(str(e))
        except Exception as e:  # 计算中的其他异常也作为工具错误返回，便于 agent 调整输入
            traceback.print_exc(file=sys.stderr)
            return _error_result(f"{type(e).__name__}: {e}")
        text = json.dumps(out, ensure_ascii=False)
        res: dict[str, Any] = {"content": [{"type": "text", "text": text}], "isError": False}
        if self.protocol >= "2025-06-18" and isinstance(out, dict):
            res["structuredContent"] = out
        return res


class _RpcError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code


def _error_result(message: str) -> dict:
    return {"content": [{"type": "text", "text": message}], "isError": True}


def serve(stdin=None, stdout=None) -> None:
    if stdin is None:
        sys.stdin.reconfigure(encoding="utf-8")
        stdin = sys.stdin
    if stdout is None:
        sys.stdout.reconfigure(encoding="utf-8")
        stdout = sys.stdout
        sys.stdout = sys.stderr  # 计算过程中的 print 不能混进协议消息
    server = Server()
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            resp = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}
        else:
            if isinstance(msg, list):  # 批量请求（旧版协议）
                resp = [r for r in (server.handle(m) for m in msg) if r is not None] or None
            else:
                resp = server.handle(msg)
        if resp is not None:
            stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            stdout.flush()


if __name__ == "__main__":
    serve()

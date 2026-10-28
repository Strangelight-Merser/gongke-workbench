"""MCP（Model Context Protocol）服务器：让 AI agent 直接调用工科工作台的设计能力，不需要操作图形界面。

    python -m gongke_core mcp

通过标准输入输出（stdio）收发 JSON-RPC 2.0 消息（每行一条），只用标准库实现，FreeCAD 自带的 Python 也能运行。
批处理工具调用计算 API；当前工程工具通过本机命令桥访问已打开的 FreeCAD 文档。
"""

from __future__ import annotations

import json
import sys
import traceback
from typing import Any, Callable

from gongke_core import api, native_client

SERVER_INFO = {"name": "gongke-workbench", "title": "工科工作台", "version": "0.1.0"}
PROTOCOL_VERSIONS = ["2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05"]

INSTRUCTIONS = """工科工作台：与学生共同修改 FreeCAD 中受支持的原生轴。
新案例用 create_shaft_project；已有工程用 get_project_context 获取会话与选择 → read_engineering_object 读取实际参数与约束
已有未绑定轴先查看 unbound_objects，明确工程条件及来源后用 bind_existing_shaft 接续；不默认套用教学工况。
→ review_current_object 固定当前尺寸复核
→ preview_shaft_change 比较直径，或 preview_fillet_change 比较课程轴右轴肩圆角 → 学生要求采用后 apply_change → 可撤销并保存。
圆角候选 ready/can_apply 只表示受限编辑可执行，review 的整轴受阻项目必须保留。
当前工程尺寸单位为 m，载荷 N、应力 Pa。预览过期后必须重新读取，不得覆盖学生手改。
局部校核通过不代表完整实际轴的疲劳、轴肩或配合检查通过，请保留工具返回的范围和限制。
需要梁刚度复核时用 run_analysis 提交当前轴快照，get_job 查询终态与结果适用性，cancel_job 取消。
任务成功不等于工程通过；仅使用 applicability=current 的结果描述当前工程。
任务书批处理工具 run_design、explore_parameter、get_report、generate_files 会重新设计，不会编辑当前原生工程。
批处理任务书单位：力 N、长度 mm、速度 m/s、转速 r/min；批处理结果中应力为 MPa、功率 kW。"""

_TASK = {"type": "object", "description": "任务书（结构见 get_task_schema）"}

_BINDING_ENGINEERING = {
    "type": "object", "additionalProperties": False,
    "description": "已有轴的明确局部工况；不得自动套用教学载荷或许用值。所有量使用 SI。",
    "properties": {
        "coordinate_system": {"const": "body_local_x", "description": "z_m 沿 Body 局部 X，fx_n 沿局部 Y，fy_n 沿局部 Z；不接受未转换的世界坐标。"},
        "source": {"type": "string", "minLength": 1, "description": "载荷、支承、转矩、限值及编辑区间的来源；保存为声明来源。"},
        "material": {"type": "object", "properties": {
            "name": {"type": "string"}, "young_modulus_pa": {"type": "number"},
            "allowable_stress_pa": {"type": "number"}, "source": {"type": "string"}},
            "required": ["name", "young_modulus_pa", "allowable_stress_pa", "source"]},
        "supports_m": {"type": "array", "minItems": 2, "maxItems": 2, "items": {"type": "number"}},
        "loads": {"type": "array", "items": {"type": "object", "additionalProperties": False,
            "properties": {key: {"type": "number"} for key in ("z_m", "fx_n", "fy_n")},
            "required": ["z_m", "fx_n", "fy_n"]}},
        "torque_points": {"type": "array", "items": {"type": "object", "additionalProperties": False,
            "properties": {key: {"type": "number"} for key in ("z_m", "torque_nm")},
            "required": ["z_m", "torque_nm"]}},
        "constraints": {"type": "object", "properties": {
            "alpha": {"type": "number"}, "max_deflection_m": {"type": "number"}},
            "required": ["alpha", "max_deflection_m"]},
        "middle_diameter_bounds_m": {"type": "array", "minItems": 2, "maxItems": 2,
            "items": {"type": "number"}, "description": "中段允许直径的下限和上限，当前实测直径须在范围内。"},
    },
    "required": ["coordinate_system", "source", "material", "supports_m", "loads", "torque_points",
                 "constraints", "middle_diameter_bounds_m"],
}


def _create_shaft_project(case="teaching", task=None):
    """初始化在外部 Python 计算，原生文档创建由 FreeCAD 主线程执行。"""
    if case == "teaching":
        if task is not None:
            raise ValueError("教学三段轴不接收减速器任务书")
        from importlib.resources import files
        from uuid import uuid4
        snapshot = json.loads(files("gongke_core").joinpath("resources/native_shaft.json").read_text(encoding="utf-8"))
        snapshot["entity_id"] = str(uuid4())
    elif case == "course_output":
        from gongke_core.course_shaft import from_design
        task = api.example_task("coupling") if task is None else task
        errors = api.validate(task)
        if errors:
            raise ValueError("；".join(errors))
        snapshot = from_design(api._run(task))
        snapshot["initialization"] = {"task": task, "source": "coupling design initialization"}
    else:
        raise ValueError("case 必须为 teaching 或 course_output")
    return native_client.call("create_project", snapshot=snapshot)


def _tool(name: str, title: str, description: str, props: dict, required: list[str], fn: Callable[..., Any],
          read_only: bool = True) -> dict:
    return {"name": name, "title": title, "description": description,
            "inputSchema": {"type": "object", "properties": props, "required": required},
            "annotations": {"readOnlyHint": read_only, "openWorldHint": False}, "_fn": fn}


TOOLS = [
    _tool("create_shaft_project", "创建原生轴工程",
          "在 FreeCAD 新文档中创建原生轴并选中。case=teaching 创建可比较改径的三段教学轴；"
          "case=course_output 从 coupling 任务书初始化真实七段输出轴、键槽和圆角，之后读取当前 CAD，不重新选径。"
          "课程轴可预览并应用受限的右轴承轴肩圆角增大，其他尺寸仍需原生编辑；不传 task 使用内置 coupling 示例。不会覆盖已打开工程。",
          {"case": {"enum": ["teaching", "course_output"], "default": "teaching"}, "task": _TASK}, [],
          _create_shaft_project, read_only=False),
    _tool("get_project_context", "读取当前工程",
          "读取已打开 FreeCAD 工程的文档会话、当前选择和受支持对象。先调用此工具获取 session_id 和 entity_id。"
          "unbound_objects 提供已有未绑定 Body 的实测尺寸、命名约束和可绑定范围；不会改模型。",
          {}, [], lambda: native_client.call("get_project_context")),
    _tool("bind_existing_shaft", "绑定已有原生轴",
          "将当前已有三段回转轴绑定为可校核工程。先从 get_project_context 的 unbound_objects[].name 取得 body_name、从 revision 取得 expected_revision，"
          "并明确提供工程条件。只添加对象身份与映射，不重建或改名草图、约束、形状。"
          "载荷和支承使用 Body 局部绝对坐标，手改轴段长度不会自动移动它们。"
          "绑定是一项可撤销事务；同一请求重试保持 operation_id，不重复绑定。复杂特征或表达式驱动暂不支持。",
          {"session_id": {"type": "string"}, "body_name": {"type": "string"},
           "expected_revision": {"type": "integer", "minimum": 0}, "engineering": _BINDING_ENGINEERING,
           "operation_id": {"type": "string"}},
          ["session_id", "body_name", "expected_revision", "engineering", "operation_id"],
          lambda session_id, body_name, expected_revision, engineering, operation_id: native_client.call(
              "bind_existing_shaft", session_id=session_id, body_name=body_name, expected_revision=expected_revision,
              engineering=engineering, operation_id=operation_id), read_only=False),
    _tool("read_engineering_object", "读取原生轴",
          "读取指定会话中原生轴的实际尺寸、材料、载荷、约束、来源和结果适用状态；长度单位 m。",
          {"session_id": {"type": "string"}, "entity_id": {"type": "string"}},
          ["session_id", "entity_id"],
          lambda session_id, entity_id: native_client.call("read_engineering_object", session_id=session_id, entity_id=entity_id)),
    _tool("review_current_object", "复核当前原生轴",
          "固定当前原生轴尺寸、材料与载荷重新计算，返回数值、约束及来源缺口。"
          "分析与对象内容关联，保存重开后仍可判断 current/stale；不改 CAD、不重新选型。"
          "课程轴的条件数值与完整验收分别报告，不能把来源或特征缺口解释为通过。",
          {"session_id": {"type": "string"}, "entity_id": {"type": "string"}},
          ["session_id", "entity_id"],
          lambda session_id, entity_id: native_client.call("review_current_object", session_id=session_id, entity_id=entity_id)),
    _tool("preview_shaft_change", "比较轴径候选",
          "在固定其他尺寸和工程条件下校核一个开放轴段的候选直径，返回差异及 change_id，不修改 CAD。"
          "diameter_m 单位为 m；保留未覆盖项，不把局部通过解释为完整轴安全。",
          {"session_id": {"type": "string"}, "entity_id": {"type": "string"}, "segment_id": {"type": "string"},
           "diameter_m": {"type": "number", "exclusiveMinimum": 0}},
          ["session_id", "entity_id", "segment_id", "diameter_m"],
          lambda session_id, entity_id, segment_id, diameter_m: native_client.call(
              "preview_shaft_change", session_id=session_id, entity_id=entity_id, segment_id=segment_id, diameter_m=diameter_m)),
    _tool("preview_fillet_change", "比较轴肩圆角候选",
          "预览课程轴右轴承邻接轴肩的圆角增大，radius_m 单位 m；左右轴段标识来自当前原生快照。"
          "can_apply 只表示满足本阶段编辑条件；实际特征重算在应用事务内检查。"
          "review 保留整轴受阻项目，ready 不代表工程验收通过。不会修改 CAD。",
          {"session_id": {"type": "string"}, "entity_id": {"type": "string"},
           "left_segment_id": {"type": "string"}, "right_segment_id": {"type": "string"},
           "radius_m": {"type": "number", "exclusiveMinimum": 0}},
          ["session_id", "entity_id", "left_segment_id", "right_segment_id", "radius_m"],
          lambda session_id, entity_id, left_segment_id, right_segment_id, radius_m: native_client.call(
              "preview_fillet_change", session_id=session_id, entity_id=entity_id,
              left_segment_id=left_segment_id, right_segment_id=right_segment_id, radius_m=radius_m)),
    _tool("apply_change", "应用候选修改",
          "将学生已选定且仍有效的候选应用为一次 FreeCAD 原生事务。operation_id 使用本次操作的唯一标识，"
          "重复调用同一操作时保持此标识；候选过期时重新读取和预览，不覆盖手改。",
          {"session_id": {"type": "string"}, "change_id": {"type": "string"}, "operation_id": {"type": "string"}},
          ["session_id", "change_id", "operation_id"],
          lambda session_id, change_id, operation_id: native_client.call(
              "apply_change", session_id=session_id, change_id=change_id, operation_id=operation_id), read_only=False),
    _tool("undo_last_agent_change", "撤销候选修改",
          "撤销指定 operation_id 对应且仍位于原生撤销栈顶的 agent 修改，不越过后续学生操作。",
          {"session_id": {"type": "string"}, "operation_id": {"type": "string"}},
          ["session_id", "operation_id"],
          lambda session_id, operation_id: native_client.call(
              "undo_last_agent_change", session_id=session_id, operation_id=operation_id), read_only=False),
    _tool("save_project", "保存原生工程",
          "保存指定 FreeCAD 文档；新工程需提供绝对 FCStd 路径 path，已有文件可省略 path。保存结果不代表工程校核通过。",
          {"session_id": {"type": "string"}, "path": {"type": "string"}}, ["session_id"],
          lambda session_id, path=None: native_client.call(
              "save_project", session_id=session_id, **({"path": path} if path is not None else {})), read_only=False),
    _tool("run_analysis", "提交当前轴梁复核",
          "从指定 FreeCAD 会话读取受支持原生轴的当前快照，提交 CalculiX 梁模型刚度复核并返回 job_id。"
          "不接受外部 snapshot，不修改工程。结果只覆盖梁挠度和转角，不代表实际 CAD 的局部应力、扭转或疲劳通过；"
          "解析比较与有限元接近也不等于完整零件安全。",
          {"session_id": {"type": "string"}, "entity_id": {"type": "string"}},
          ["session_id", "entity_id"],
          lambda session_id, entity_id: native_client.call(
              "run_analysis", session_id=session_id, entity_id=entity_id), read_only=False),
    _tool("get_job", "查询轴梁复核任务",
          "查询 job_id 的运行状态、结果与错误；applicability 区分 current、stale、missing、unsupported。"
          "运行期间手改后的旧结果可以保留，但不能用来描述当前工程；任务成功与工程校核结论分别读取。",
          {"job_id": {"type": "string"}}, ["job_id"],
          lambda job_id: native_client.call("get_job", job_id=job_id)),
    _tool("cancel_job", "取消轴梁复核任务",
          "请求取消指定 job_id 的梁复核任务，不回退或修改 CAD。取消请求返回后仍需用 get_job 核对最终状态。",
          {"job_id": {"type": "string"}}, ["job_id"],
          lambda job_id: native_client.call("cancel_job", job_id=job_id), read_only=False),
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
          "按任务书重新设计，不编辑当前 FreeCAD 工程。完成全部设计计算：选电动机、分配传动比、设计各级齿轮（或 V 带、锥齿轮、蜗杆）、轴的结构和强度/疲劳/刚度校核、"
          "轴承寿命、键、联轴器、箱体尺寸。返回结果摘要、全部校核项和未通过项（failed）。约 0.1～0.5 秒。",
          {"task": _TASK}, ["task"], lambda task: api.design(task)),
    _tool("explore_parameter", "多方案对比",
          "按任务书批处理，不编辑当前 FreeCAD 工程。把一个参数依次取多个值分别设计，返回每个方案的主要指标（电动机、模数、齿数、中心距、强度利用率 σ/[σ]、"
          "最大轴径、最短轴承寿命、未通过项），用于选择参数。param 为点号路径，如 ratio_split、gears.high.material1、"
          "gears.low.phi_d、scheme、motor_sync_speed_rpm。",
          {"task": _TASK, "param": {"type": "string"}, "values": {"type": "array", "minItems": 1, "maxItems": 20}},
          ["task", "param", "values"], lambda task, param, values: api.explore(task, param, values)),
    _tool("get_report", "计算说明书",
          "按任务书重新计算，不读取当前 FreeCAD 工程。返回计算说明书的 Markdown 文本（每步计算的公式、代入值和结论）。chapter 为章标题中的关键字（如“低速级”“Ⅱ轴”“轴承”），"
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
          "按任务书重新设计并导出，不导出当前已编辑的 FreeCAD 工程。生成文件到 out_dir：summary.json、report.md 和 report.docx（计算说明书）、drawings/（装配图和零件图 DXF、"
          "SVG 预览、整套 drawings.pdf）；step=true 时生成三维装配体 reducer_assembly.step（需要 build123d，约 1 分钟）；"
          "fem=true 时用 CalculiX 复核轴的刚度和齿根应力（需要 ccx 和 gmsh）。返回本次清单 manifest.json；calculation_ok 表示计算校核，exports_complete 表示请求文件齐全，ok 还要求自动图检通过。out_dir 必须是新目录或空目录，改参后使用新目录。",
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
        except (api.TaskError, native_client.NativeBridgeError, ValueError, KeyError) as e:
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

"""已有原生工程的只读检查用例；CLI 与 MCP 使用同一入口。"""

from copy import deepcopy
import json

from gongke_core import drawing_review, engineering_conditions, revision_calculations, revision_mapping


def inspect_revision(case, capture=None, previous=None):
    """capture 缺省时读取当前打开的 FreeCAD；离线采集始终标记为历史快照。"""
    revision_mapping.validate_case(case)
    live = capture is None
    if live:
        from gongke_core.native_client import call
        capture = call("read_revision_context", document_path=case["document"]["path"],
                       body_name=case["document"]["body"], pages=case["pages"])
    conditions = engineering_conditions.normalize_conditions(case.get("conditions", {"schema_version": 1, "fields": {}}))
    mapping = revision_mapping.map_capture(case, capture, case.get("conditions"))
    drawing = drawing_review.review(capture, mapping)
    # 身份不符时不能把另一工程的几何继续带入本任务计算。
    settled = not (capture["document"].get("pending_transaction") or capture["document"].get("needs_rebuild"))
    geometry = capture["geometry"] if mapping["mapping"] is not None and settled else {}
    calculation = revision_calculations.assess(geometry, conditions)
    if not settled:
        calculation["geometry_issues"].append("当前编辑事务尚未结束或模型待更新，几何暂不作为正式计算输入")
    current = {"status": "current_at_capture" if live else "recorded_capture",
               "message": "对应本次实时读取；相关编辑后须重新检查" if live else "离线采集，不证明当前 CAD 仍为此状态"}
    if previous is not None:
        if not isinstance(previous, dict) or not isinstance(previous.get("mapping"), dict):
            raise ValueError("previous 必须是本入口上次生成的完整 revision.json")
        current["previous"] = revision_mapping.applicability(previous["mapping"], mapping)
    return {"schema_version": 1, "case_id": case["case_id"],
            "stage": "assessed" if mapping["mapping"] is not None else "captured",
            "read_only": True, "source_mode": "live" if live else "recorded_capture",
            "capture": deepcopy(capture), "mapping": mapping, "conditions": conditions,
            "calculation": calculation, "drawing_review": drawing, "applicability": current,
            "modification_eligibility": {"allowed": False, "reason": "G1 只读检查，不执行 CAD 修改"}}


def format_summary(result):
    """给执行者明确的 CAD 定位与下一步，不以一个总状态隐藏独立结果。"""
    lines = ["原生工程只读检查", result["applicability"]["message"],
             f"工程：{result['capture']['document']['path']}"]
    mapping = result["mapping"]
    if mapping["mapping"]:
        target = mapping["mapping"]["target"]
        lines.append(f"目标：{target['radius_constraint']} 对应直径 {target['diameter_m'] * 1000:g} mm")
    for issue in mapping["issues"]:
        lines.append(f"映射待确认：{issue['location']} — {issue['message']}")
    lines.append("工程条件（确认状态由输入者声明）：")
    for entry in result["conditions"]["evidence"]:
        supplied = entry["input"]
        if not isinstance(supplied, dict):
            lines.append(f"  {entry['label']}：缺失")
            continue
        value = supplied.get("value", {k: supplied[k] for k in ("position", "fx", "fy", "torque") if k in supplied})
        # 载荷组的详细值由逐条证据展示，避免重复整个 JSON 列表。
        display = f"{len(value)} 项" if isinstance(value, list) and entry["field"] in ("loads", "torque_points") else json.dumps(value, ensure_ascii=False)
        source = supplied.get("source", {})
        state = "用于计算" if entry["usable"] else "未用于计算"
        lines.append(f"  {entry['label']}：{display} {supplied.get('unit', '')}；{state}；{supplied.get('status', '未声明')}")
        lines.append(f"    来源：{source.get('reference', '缺失')}；原文：{source.get('text', '缺失')}")
    labels = {"pass": "满足声明限值", "fail": "超出声明限值", "unknown": "未判定", "unavailable": "缺条件，未计算"}
    for reason in result["calculation"]["geometry_issues"]:
        lines.append("几何待确认：" + reason)
    for check in result["calculation"]["checks"]:
        value = check["value"]
        number = ""
        if value is not None:
            unit = "MPa" if check["unit"] == "Pa" else "mm"
            number = f" {value / 1e6 if check['unit'] == 'Pa' else value * 1000:.6g} {unit}；"
        lines.append(f"{check['title']}：{number}{labels[check['status']]}")
        lines.extend("  " + reason for reason in check["reasons"])
    for issue in result["conditions"]["issues"]:
        lines.append(f"条件：{issue['field']} — {issue['message']}")
    drawing = result["drawing_review"]
    lines.append("相关图纸：" + {"pass": "本次所选范围检查通过", "fail": "发现需要修复的问题", "unknown": "仍有未确认项"}[drawing["status"]])
    for issue in drawing["issues"]:
        location = issue["location"]
        where = "/".join(str(location[k]) for k in ("page", "view", "dimension") if location.get(k))
        lines.append(f"  {where}：{issue['message']}；{issue['next_action']}")
    previous = result["applicability"].get("previous")
    if previous:
        lines.append("上次结论：" + ("已过期（" + "、".join(previous["changed"]) + "）" if previous["status"] == "stale" else "基线未变化"))
    lines.append("当前检查不覆盖完整疲劳、制造与全图制图规范；未执行原生修改。")
    return "\n".join(lines)

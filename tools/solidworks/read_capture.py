"""校验 SOLIDWORKS 只读采集文件；不连接 CAD，不推断轴段或补入工况。"""

from __future__ import annotations

import argparse
import json
import math
import ntpath
from pathlib import Path
from typing import Any


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _object(value: Any, fields: tuple[str, ...], location: str) -> dict:
    _require(isinstance(value, dict), f"{location}: 应为对象")
    _require(all(field in value for field in fields), f"{location}: 缺少必要字段")
    return value


def _text(value: Any, location: str) -> None:
    _require(value is None or (isinstance(value, str) and bool(value)), f"{location}: 应为非空字符串或 null")


def _integer(value: Any, location: str) -> None:
    _require(value is None or type(value) is int, f"{location}: 应为整数或 null")


def _boolean(value: Any, location: str) -> None:
    _require(value is None or type(value) is bool, f"{location}: 应为布尔或 null")


def _number(value: Any, location: str) -> None:
    _require(value is None or (type(value) in (float, int) and math.isfinite(value)),
             f"{location}: 应为有限数值或 null")


def _rows(value: Any, location: str) -> list:
    _require(isinstance(value, list), f"{location}: 应为数组")
    return value


def _read_status(row: dict, fields: tuple[str, ...], location: str) -> None:
    _require(row["status"] in ("read", "partial"), f"{location}: 无效读取状态")
    if row["status"] == "read":
        _require(all(row[field] is not None for field in fields), f"{location}: read 状态不能有缺失字段")


def validate_capture(data: Any) -> dict:
    """返回已校验原数据；格式合格不代表枚举完整、工程合格或可写入。"""
    fields = ("schema_version", "capture_kind", "prototype_validation", "status",
              "captured_at_local", "document", "enumeration_completeness",
              "engineering_semantics", "dimensions", "open_drawings", "issues", "host",
              "selected_target", "state_before", "state_after", "state_preservation")
    data = _object(data, fields, "capture")
    _require(type(data["schema_version"]) is int and data["schema_version"] == 2, "不支持的 schema_version；请使用同包 v2 采集宏重新采集")
    _require(data["capture_kind"] == "solidworks_readonly_inventory", "无效 capture_kind")
    _require(data["prototype_validation"] == "unverified", "本原型尚无 SOLIDWORKS 实机验证")
    _require(data["enumeration_completeness"] == "not_established", "本采集方式不能证明尺寸枚举完整")
    _require(data["engineering_semantics"] == "unmapped", "采集文件不能声称已建立工程语义")
    _require(data["state_preservation"] == "not_established", "保存标志一致不能证明原状态完全不变")
    _require(data["status"] in ("collected", "partial", "unsupported", "error"), "无效采集状态")
    host = _object(data["host"], ("revision_number", "platform"), "host")
    _text(host["revision_number"], "host.revision_number")
    _require(host["platform"] == "Windows", "此原型仅采集 Windows SOLIDWORKS")
    _text(data["captured_at_local"], "captured_at_local")
    _require(data["captured_at_local"] is not None, "缺少采集本地时间")
    for issue in _rows(data["issues"], "issues"):
        _require(isinstance(issue, str) and bool(issue), "issues: 应为非空字符串数组")

    for key in ("state_before", "state_after"):
        for index, value in enumerate(_rows(data[key], key)):
            loc = f"{key}[{index}]"
            row = _object(value, ("path", "title", "type", "configuration", "save_flag", "selection_count"), loc)
            for field in ("path", "title", "configuration"):
                _text(row[field], f"{loc}.{field}")
            _integer(row["type"], f"{loc}.type")
            _integer(row["selection_count"], f"{loc}.selection_count")
            _require(row["selection_count"] is None or row["selection_count"] >= 0, f"{loc}: 选择数量不能为负")
            _boolean(row["save_flag"], f"{loc}.save_flag")

    target = data["selected_target"]
    if target is not None:
        target = _object(target, ("full_name", "value_si", "parameter_type", "unit", "display_type", "selection_type"), "selected_target")
        _text(target["full_name"], "selected_target.full_name")
        _integer(target["parameter_type"], "selected_target.parameter_type")
        _integer(target["display_type"], "selected_target.display_type")
        _require(target["selection_type"] == 14 and type(target["selection_type"]) is int, "目标必须来自选中的尺寸")
        _require(target["display_type"] != 10, "倒角包含两个参数，不能作为单一选定尺寸")
        _number(target["value_si"], "selected_target.value_si")
        _require(target["unit"] == {0: "m", 1: "rad", 2: "integer"}.get(target["parameter_type"]), "选定尺寸类型与单位不一致")
        if target["unit"] == "integer" and target["value_si"] is not None:
            _require(target["value_si"] == int(target["value_si"]), "选定整数尺寸不能包含小数")

    document = data["document"]
    if document is not None:
        document = _object(document, ("path", "title", "type", "configuration"), "document")
        for field in ("path", "title", "configuration"):
            _text(document[field], f"document.{field}")
        _integer(document["type"], "document.type")
    if data["status"] in ("collected", "partial"):
        _require(document is not None and document["type"] == 1, "仅活动零件可标记 collected/partial")
    if data["status"] == "collected":
        _require(not data["issues"], "collected 状态不能包含读取问题")
        _require(all(document[field] is not None for field in ("path", "title", "configuration")), "collected 状态缺少零件信息")
        _require(host["revision_number"] is not None, "collected 状态缺少宿主版本")
        _require(target is not None and all(value is not None for value in target.values()), "collected 状态缺少明确选择的尺寸")
        _require(bool(data["state_before"]) and data["state_before"] == data["state_after"], "collected 状态缺少一致的前后观察")
        for row in data["state_before"]:
            _require(all(row[field] is not None for field in ("path", "title", "type", "save_flag", "selection_count")), "collected 状态含未知观察字段")
            _require(row["type"] != 1 or row["configuration"] is not None, "collected 状态缺少零件配置观察")

    dimension_fields = ("full_name", "feature_name", "value_si", "parameter_type", "unit", "driven_state", "read_only")
    names: set[str] = set()
    for index, value in enumerate(_rows(data["dimensions"], "dimensions")):
        location = f"dimensions[{index}]"
        row = _object(value, dimension_fields + ("status",), location)
        for field in ("full_name", "feature_name", "unit"):
            _text(row[field], f"{location}.{field}")
        for field in ("parameter_type", "driven_state"):
            _integer(row[field], f"{location}.{field}")
        _boolean(row["read_only"], f"{location}.read_only")
        number = row["value_si"]
        _number(number, f"{location}.value_si")
        unit = {0: "m", 1: "rad", 2: "integer"}.get(row["parameter_type"])
        _require(row["unit"] == unit, f"{location}: 尺寸类型与单位不一致")
        if unit == "integer" and number is not None:
            _require(number == int(number), f"{location}: 整数尺寸不能包含小数")
        _read_status(row, dimension_fields, location)
        name = row["full_name"]
        if name is not None:
            _require(name not in names, f"{location}: FullName 重复")
            names.add(name)

    for index, value in enumerate(_rows(data["open_drawings"], "open_drawings")):
        location = f"open_drawings[{index}]"
        drawing = _object(value, ("path", "title", "status", "views"), location)
        for field in ("path", "title"):
            _text(drawing[field], f"{location}.{field}")
        _read_status(drawing, ("path", "title"), location)
        for view_index, value in enumerate(_rows(drawing["views"], f"{location}.views")):
            view_location = f"{location}.views[{view_index}]"
            view_fields = ("sheet_name", "view_name", "referenced_model", "referenced_configuration")
            view = _object(value, view_fields + ("status", "display_dimensions", "annotation_coverage", "view_update_status"), view_location)
            for field in view_fields:
                _text(view[field], f"{view_location}.{field}")
            _read_status(view, view_fields, view_location)
            _require(view["annotation_coverage"] == "not_established", "原型不能证明标注覆盖完整")
            _require(view["view_update_status"] == "not_checked", "原型尚未核验视图已更新")
            annotation_names = set()
            for a_index, value in enumerate(_rows(view["display_dimensions"], f"{view_location}.display_dimensions")):
                loc = f"{view_location}.display_dimensions[{a_index}]"
                annotation = _object(value, ("annotation_name", "dimension_full_names", "display_type", "override",
                                            "override_value", "override_value_unit", "dangling", "text_override_status", "status"), loc)
                _text(annotation["annotation_name"], f"{loc}.annotation_name")
                _integer(annotation["display_type"], f"{loc}.display_type")
                _boolean(annotation["override"], f"{loc}.override")
                _boolean(annotation["dangling"], f"{loc}.dangling")
                _number(annotation["override_value"], f"{loc}.override_value")
                _require(annotation["override_value_unit"] == "not_established", "覆盖值保留 API 原值，单位尚未核对")
                _require(annotation["text_override_status"] == "not_checked", "原型尚未核验整段文字覆盖")
                linked = _rows(annotation["dimension_full_names"], f"{loc}.dimension_full_names")
                _require(all(isinstance(name, str) and name for name in linked), f"{loc}: 无效尺寸标识")
                _require(len(linked) == len(set(linked)), f"{loc}: 重复尺寸标识")
                _read_status(annotation, ("annotation_name", "display_type", "override", "dangling"), loc)
                if annotation["status"] == "read":
                    _require(bool(linked), f"{loc}: read 状态缺少关联尺寸")
                    _require(annotation["override"] is not True or annotation["override_value"] is not None, f"{loc}: 数值覆盖启用但值未知")
                name = annotation["annotation_name"]
                if name is not None:
                    _require(name not in annotation_names, f"{loc}: 同视图标注身份重复")
                    annotation_names.add(name)
                _require(view["status"] != "read" or annotation["status"] == "read", f"{view_location}: 存在不完整标注，应标记 partial")
            _require(drawing["status"] != "read" or view["status"] == "read", f"{location}: 存在不完整视图，应标记 partial")

    if data["status"] == "collected":
        _require(bool(data["dimensions"]), "未枚举出尺寸应标记 partial")
        _require(all(row["status"] == "read" for row in data["dimensions"] + data["open_drawings"]), "collected 状态包含不完整记录")
    return data


def _unique_keys(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in pairs:
        _require(key not in result, f"JSON 字段重复: {key}")
        result[key] = value
    return result


def _invalid_number(value: str) -> None:
    raise ValueError(f"JSON 包含非有限数值: {value}")


def load_capture(path: str | Path) -> dict:
    with Path(path).open(encoding="utf-8") as stream:
        return validate_capture(json.load(stream, object_pairs_hook=_unique_keys, parse_constant=_invalid_number))


def matching_views(data: dict) -> list[dict]:
    """只匹配绝对 Windows 模型路径与原配置名；不以文件名猜测关联。"""
    validate_capture(data)
    document = data["document"]
    if document is None or document["type"] != 1 or not document["path"] or not document["configuration"]:
        return []
    path = document["path"]
    if not ntpath.isabs(path):
        return []
    normalized = ntpath.normcase(ntpath.normpath(path))
    matches = []
    for drawing in data["open_drawings"]:
        for view in drawing["views"]:
            reference = view["referenced_model"]
            if (reference and ntpath.isabs(reference)
                    and ntpath.normcase(ntpath.normpath(reference)) == normalized
                    and view["referenced_configuration"] == document["configuration"]):
                matches.append({"drawing_path": drawing["path"], **view})
    return matches


def inspection_summary(data: dict) -> dict:
    """定位已经读到的标注问题；不把未读范围或未核实字段计为通过。"""
    validate_capture(data)
    target = data["selected_target"]
    matches = matching_views(data)
    instances, findings = [], []
    for drawing in data["open_drawings"]:
        for view in drawing["views"]:
            for annotation in view["display_dimensions"]:
                location = {"drawing_path": drawing["path"], "sheet_name": view["sheet_name"],
                            "view_name": view["view_name"], "annotation_name": annotation["annotation_name"]}
                for field, kind in (("override", "numeric_override"), ("dangling", "dangling_dimension")):
                    if annotation[field] is True:
                        finding = {"kind": kind, **location}
                        if field == "override":
                            finding.update(value=annotation["override_value"], value_unit=annotation["override_value_unit"])
                        findings.append(finding)
                if annotation["status"] == "partial":
                    findings.append({"kind": "annotation_read_incomplete", **location})
    if target is not None and target["full_name"]:
        for view in matches:
            for annotation in view["display_dimensions"]:
                if target["full_name"] in annotation["dimension_full_names"]:
                    instances.append({"drawing_path": view["drawing_path"], "sheet_name": view["sheet_name"],
                                      "view_name": view["view_name"], **annotation})
    changed = data["state_before"] != data["state_after"]
    if changed:
        findings.append({"kind": "observed_state_changed"})
    return {"status": data["status"], "host": data["host"], "document": data["document"],
            "selected_target": target, "dimensions": len(data["dimensions"]), "open_drawings": len(data["open_drawings"]),
            "matching_target_instances": instances, "findings": findings, "issues": data["issues"],
            "drawing_review": "incomplete", "enumeration_completeness": data["enumeration_completeness"],
            "engineering_semantics": data["engineering_semantics"], "state_preservation": data["state_preservation"],
            "unknown": ["枚举覆盖与目标轴段语义", "图纸整段文字覆盖、公差、显示单位及更新状态", "原文件和全部内存手改保持不变：需现场对照"]}


def main() -> None:
    parser = argparse.ArgumentParser(description="检查 SOLIDWORKS 只读采集 JSON；不连接 CAD、不做工程校核。")
    parser.add_argument("capture", type=Path)
    args = parser.parse_args()
    try:
        data = load_capture(args.capture)
    except (OSError, ValueError) as error:
        parser.exit(1, f"采集文件不合格: {error}\n")
    print(json.dumps(inspection_summary(data), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

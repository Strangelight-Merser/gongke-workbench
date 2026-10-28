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
              "engineering_semantics", "dimensions", "open_drawings", "issues")
    data = _object(data, fields, "capture")
    _require(type(data["schema_version"]) is int and data["schema_version"] == 1, "不支持的 schema_version")
    _require(data["capture_kind"] == "solidworks_readonly_inventory", "无效 capture_kind")
    _require(data["prototype_validation"] == "unverified", "本原型尚无 SOLIDWORKS 实机验证")
    _require(data["enumeration_completeness"] == "not_established", "本采集方式不能证明尺寸枚举完整")
    _require(data["engineering_semantics"] == "unmapped", "采集文件不能声称已建立工程语义")
    _require(data["status"] in ("collected", "partial", "unsupported", "error"), "无效采集状态")
    _text(data["captured_at_local"], "captured_at_local")
    _require(data["captured_at_local"] is not None, "缺少采集本地时间")
    for issue in _rows(data["issues"], "issues"):
        _require(isinstance(issue, str) and bool(issue), "issues: 应为非空字符串数组")

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

    dimension_fields = ("full_name", "feature_name", "value_si", "parameter_type", "unit", "driven_state", "read_only")
    names: set[str] = set()
    for index, value in enumerate(_rows(data["dimensions"], "dimensions")):
        location = f"dimensions[{index}]"
        row = _object(value, dimension_fields + ("status",), location)
        for field in ("full_name", "feature_name", "unit"):
            _text(row[field], f"{location}.{field}")
        for field in ("parameter_type", "driven_state"):
            _integer(row[field], f"{location}.{field}")
        _require(row["read_only"] is None or type(row["read_only"]) is bool, f"{location}.read_only: 应为布尔或 null")
        number = row["value_si"]
        _require(number is None or (type(number) in (float, int) and math.isfinite(number)), f"{location}.value_si: 应为有限数值或 null")
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
            view = _object(value, view_fields + ("status",), view_location)
            for field in view_fields:
                _text(view[field], f"{view_location}.{field}")
            _read_status(view, view_fields, view_location)
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


def main() -> None:
    parser = argparse.ArgumentParser(description="检查 SOLIDWORKS 只读采集 JSON；不连接 CAD、不做工程校核。")
    parser.add_argument("capture", type=Path)
    args = parser.parse_args()
    try:
        data = load_capture(args.capture)
    except (OSError, ValueError) as error:
        parser.exit(1, f"采集文件不合格: {error}\n")
    print(json.dumps({"status": data["status"], "document": data["document"],
                      "dimensions": len(data["dimensions"]),
                      "open_drawings": len(data["open_drawings"]),
                      "matching_views": matching_views(data),
                      "issues": data["issues"],
                      "enumeration_completeness": data["enumeration_completeness"],
                      "engineering_semantics": data["engineering_semantics"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

"""只读修订任务的外部身份与尺寸映射；不加载 CAD，也不写入工程属性。"""

from copy import deepcopy
import hashlib
import json
import math
import posixpath
import ntpath


METHOD_VERSION = 1


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     allow_nan=False, separators=(",", ":")).encode()).hexdigest()


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} 必须是非空字符串")


def _path(value):
    _text(value, "document.path")
    # 离线采集的路径属于宿主，不能在检查器机器上 resolve 或查找同名文件。
    drive, tail = ntpath.splitdrive(value)
    if drive and tail.startswith(("/", "\\")):
        return ntpath.normcase(ntpath.normpath(value))
    if value.startswith("/"):
        return posixpath.normpath(value)
    raise ValueError("document.path 必须是宿主中的绝对路径")


def validate_case(case):
    """校验当前 FreeCAD 三段轴的显式映射；不推断尺寸或标注对应关系。"""
    if not isinstance(case, dict) or type(case.get("schema_version")) is not int or case["schema_version"] != 1:
        raise ValueError("修订任务 schema_version 必须为 1")
    _text(case.get("case_id"), "case_id")
    document = case.get("document")
    if not isinstance(document, dict):
        raise ValueError("缺少 document 映射")
    _path(document.get("path"))
    for name in ("body", "sketch", "revolution"):
        _text(document.get(name), f"document.{name}")
    signature = document.get("structure_signature")
    if not isinstance(signature, list) or not signature:
        raise ValueError("document.structure_signature 必须记录原生约束结构")
    if "entity_id" in document:
        _text(document["entity_id"], "document.entity_id")
    target = case.get("target")
    if not isinstance(target, dict):
        raise ValueError("缺少 target 映射")
    _text(target.get("radius_constraint"), "target.radius_constraint")
    if type(target.get("segment_index")) is not int or not 0 <= target["segment_index"] < 3:
        raise ValueError("target.segment_index 必须为 0、1 或 2")
    pages = case.get("pages")
    if not isinstance(pages, list) or not pages:
        raise ValueError("pages 必须明确列出本次检查的 TechDraw 页")
    for name in pages:
        _text(name, "pages 中的页名")
    if len(set(pages)) != len(pages):
        raise ValueError("pages 不能重复")
    annotations = case.get("annotations")
    if not isinstance(annotations, list) or not annotations:
        raise ValueError("annotations 必须明确列出目标直径的标注实例")
    seen = set()
    for item in annotations:
        if not isinstance(item, dict):
            raise ValueError("annotations 中的实例必须是对象")
        for name in ("page", "view", "dimension"):
            _text(item.get(name), f"annotation.{name}")
        if item["page"] not in pages or item.get("target") != "diameter":
            raise ValueError("标注必须属于本次页范围，并显式映射为 diameter")
        locator = (item["page"], item["view"], item["dimension"])
        if locator in seen:
            raise ValueError("同一标注实例不能重复映射")
        seen.add(locator)
    _hash(case)  # 身份与指纹只接受有限数值的 JSON 数据。


def _drawing_fingerprint(drawing):
    """枚举顺序和树展开不是图纸变更；模型状态和未知项仍进入指纹。"""
    value = deepcopy(drawing)

    def model_state(obj):
        if "state" in obj:
            obj["state"] = [state for state in obj["state"] if state != "Expanded"]

    for page in value.get("pages", []):
        model_state(page)
        for view in page.get("views", []):
            model_state(view)
            for dimension in view.get("dimensions", []):
                model_state(dimension)
            view["dimensions"] = sorted(view.get("dimensions", []), key=lambda row: row["name"])
        page["views"] = sorted(page.get("views", []), key=lambda row: row["name"])
    value["pages"] = sorted(value.get("pages", []), key=lambda row: row["name"])
    return _hash(value)


def map_capture(case, capture, conditions=None):
    """核对一次真实采集与外部任务，返回映射和分离的内容指纹。

    annotations 只是用户确认的实例名单。其余被采到的标注保留为 unknown，
    不能因为未列入名单就声称它们与目标无关。结果永不授予写入权限。
    """
    validate_case(case)
    if not isinstance(capture, dict) or capture.get("host") != "freecad":
        raise ValueError("当前修订映射只接收 FreeCAD 原生采集")
    _text(capture.get("session_id"), "capture.session_id")
    document = capture.get("document")
    geometry = capture.get("geometry")
    drawing = capture.get("drawing")
    if not isinstance(document, dict) or not isinstance(geometry, dict) or not isinstance(drawing, dict):
        raise ValueError("采集必须包含 document、geometry 和 drawing 对象")
    expected = case["document"]
    expected_path, actual_path = _path(expected["path"]), _path(document.get("path"))
    identity = {"host": "freecad", "path": expected_path, "body": expected["body"],
                "sketch": expected["sketch"], "revolution": expected["revolution"],
                "structure_signature": expected["structure_signature"]}
    bound_id = geometry.get("entity_id")
    if bound_id is not None:
        _text(bound_id, "geometry.entity_id")
    result = {
        "case_id": case["case_id"], "status": "mapped", "session_id": capture["session_id"],
        "document_id": _hash({"host": "freecad", "path": expected_path}),
        "entity_id": bound_id or "revision:" + _hash({"case_id": case["case_id"], **identity}),
        "method_version": METHOD_VERSION, "issues": [], "can_apply": False,
        "mapping": None,
        "fingerprints": {
            "geometry": _hash(geometry), "conditions": _hash(conditions),
            "mapping": _hash({"document": identity, "target": case["target"],
                              "pages": sorted(case["pages"]),
                              "annotations": sorted(case["annotations"],
                                                    key=lambda a: (a["page"], a["view"], a["dimension"]))}),
            "drawing": _drawing_fingerprint(drawing),
            "document_state": _hash({field: document.get(field)
                                     for field in ("pending_transaction", "needs_rebuild")}),
        },
    }

    def issue(code, location, message):
        result["issues"].append({"code": code, "location": location, "message": message})

    if actual_path != expected_path:
        issue("document_mismatch", "document.path", "当前原生文件与任务不一致，请重新选择；同名文件不能替代。")
        result["status"] = "mismatch"
        return result
    if geometry.get("supported") is not True:
        result["status"] = "unsupported"
        issue("unsupported_geometry", "geometry", geometry.get("reason") or "当前几何无法可靠读取，不能计算目标参数。")
        return result
    for field, observed in (("body", geometry.get("body_name")), ("sketch", geometry.get("sketch")),
                            ("revolution", geometry.get("revolution"))):
        if observed != expected[field]:
            issue("object_mismatch", f"document.{field}", "原生对象定位已变化，需重新确认映射。")
    if geometry.get("structure_signature") != expected["structure_signature"]:
        issue("structure_mismatch", "document.structure_signature", "原生约束结构已变化，不能沿用旧尺寸映射。")
    if "entity_id" in expected and bound_id != expected["entity_id"]:
        issue("entity_mismatch", "document.entity_id", "已有工程实体身份与任务不一致。")
    if result["issues"]:
        result["status"] = "mismatch"
        return result
    segments = geometry.get("segments")
    target = case["target"]
    if not isinstance(segments, list) or len(segments) != 3:
        result["status"] = "unsupported"
        issue("unsupported_geometry", "geometry.segments", "没有读到受支持的三个实际轴段。")
        return result
    segment = segments[target["segment_index"]]
    diameter = segment.get("diameter_m")
    if segment.get("radius_constraint") != target["radius_constraint"]:
        result["status"] = "mismatch"
        issue("target_mismatch", "target.radius_constraint", "选定半径约束与目标轴段不一致，不能按相同数值猜测对应。")
        return result
    if type(diameter) not in (int, float) or not math.isfinite(diameter) or diameter <= 0:
        result["status"] = "unsupported"
        issue("unreadable_dimension", "target", "没有读到有限正值的当前直径。")
        return result

    instances = {}
    selected_pages = set(case["pages"])
    pages_seen = []
    for page in drawing.get("pages", []):
        if page["name"] not in selected_pages:
            continue
        pages_seen.append(page["name"])
        for view in page.get("views", []):
            for dimension in view.get("dimensions", []):
                locator = (page["name"], view["name"], dimension["name"])
                instances.setdefault(locator, []).append(dimension)
    for name in sorted(selected_pages):
        if pages_seen.count(name) != 1:
            issue("page_unavailable", f"pages.{name}", "指定图纸页缺失或身份重复，无法确认检查范围。")
    matched = []
    declared = set()
    for annotation in case["annotations"]:
        locator = tuple(annotation[key] for key in ("page", "view", "dimension"))
        declared.add(locator)
        rows = instances.get(locator, [])
        if len(rows) != 1:
            issue("annotation_unavailable", "/".join(locator), "已确认的目标标注缺失或身份重复，请在原生图纸中重新定位。")
        else:
            matched.append(deepcopy(annotation))
    unmapped = [{"page": p, "view": v, "dimension": d}
                for p, v, d in sorted(instances.keys() - declared)]
    for row in unmapped:
        issue("annotation_unmapped", "/".join(row.values()), "此标注尚未确认与目标参数的关系，保留为未知。")
    if result["issues"]:
        result["status"] = "incomplete"
    result["mapping"] = {"target": {**deepcopy(target), "diameter_m": diameter},
                         "annotations": matched,
                         "coverage": {"scope": "selected_pages", "status": "unknown" if result["issues"] else "declared_instances_matched",
                                      "declared": len(case["annotations"]), "matched": len(matched),
                                      "unmapped": unmapped}}
    return result


def applicability(previous, current):
    """比较已检查结果与最新采集；重开后旧会话结论必须重新检查。"""
    changed = [field for field in ("case_id", "document_id", "entity_id", "session_id", "method_version")
               if previous.get(field) != current.get(field)]
    old, new = previous.get("fingerprints", {}), current.get("fingerprints", {})
    changed.extend(field for field in ("geometry", "conditions", "mapping", "drawing", "document_state")
                   if not old.get(field) or old.get(field) != new.get(field))
    if current.get("status") in ("mismatch", "unsupported"):
        changed.append("unavailable_mapping")
    return {"status": "stale" if changed else "current", "changed": changed}

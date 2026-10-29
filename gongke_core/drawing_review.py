"""检查所选原生图纸页中的目标直径；仅消费快照，不刷新或修改 CAD。"""

import math
import posixpath
import re


_FORMAT = re.compile(r"[⌀Ø]?%\.(\d+)w")
_DISPLAY_MM = re.compile(r"\s*[⌀Ø]?\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*mm\s*")


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def review(capture, mapping_result):
    """按显式映射检查所有显示实例，未知的枚举或测量状态不会变成通过。"""
    issues = []

    def issue(code, severity, message, location=None, next_action=None, **evidence):
        row = {"code": code, "severity": severity, "message": message,
               "location": {"page": None, "view": None, "dimension": None, **(location or {})},
               "next_action": next_action or "在原生 CAD 中核对该位置，修复或确认后重新读取。"}
        if evidence:
            row["evidence"] = evidence
        issues.append(row)

    def observed_issues(rows, location):
        for row in rows:
            if isinstance(row, dict):
                issue(row.get("code", "capture_unknown"), "error" if row.get("severity") == "error" else "unknown",
                      row.get("message", "该项读取未完成。"), location,
                      row.get("next_action"))
            else:
                issue("capture_unknown", "unknown", str(row), location)

    def state_ready(state, location):
        ready = True
        if "Touched" in state:
            issue("needs_rebuild", "unknown", "该对象需要更新，当前读取未执行重算。", location,
                  "在 CAD 中明确执行更新并检查结果，然后重新读取。")
            ready = False
        if any(item in state for item in ("Invalid", "Error")):
            issue("invalid_object", "error", "原生对象处于无效状态。", location)
            ready = False
        unknown = set(state) - {"Up-to-date", "Expanded", "Touched", "Invalid", "Error"}
        if unknown:
            issue("object_state_unknown", "unknown", "原生对象包含尚未核对的状态，暂不使用其测量值。", location,
                  states=sorted(unknown))
            ready = False
        return ready

    drawing = capture.get("drawing", {})
    mapping = mapping_result.get("mapping")
    document_ready = True
    if capture.get("document", {}).get("pending_transaction"):
        issue("pending_transaction", "unknown", "原生文档仍有未结束的编辑事务，当前缓存尺寸不用于比较。",
              next_action="在 CAD 中完成或取消当前编辑事务，检查更新结果后重新读取。")
        document_ready = False
    if capture.get("document", {}).get("needs_rebuild"):
        issue("needs_rebuild", "unknown", "原生模型需要更新，图纸缓存尺寸尚不能代表当前模型。",
              next_action="在 CAD 中明确执行模型和图纸更新并检查结果，然后重新读取。")
        document_ready = False
    source_coverage = drawing.get("coverage", {})
    if source_coverage.get("status") != "complete":
        issue("incomplete_capture", "unknown", "所选图纸页的枚举覆盖尚未确认。",
              next_action="核对未读取的页、视图和标注；补充采集或明确人工检查范围。")
    observed_issues(drawing.get("issues", []), {})
    for row in mapping_result.get("issues", []):
        parts = row.get("location", "").split("/")
        location = dict(zip(("page", "view", "dimension"), parts)) if len(parts) == 3 else {}
        severity = "error" if mapping_result.get("status") == "mismatch" else "unknown"
        issue(row["code"], severity, row["message"], location)
    if mapping is None or mapping_result.get("status") in ("mismatch", "unsupported"):
        if not mapping_result.get("issues"):
            issue("mapping_unavailable", "unknown", "当前工程与目标尺寸的映射不可用。")
        return {"status": "fail" if any(i["severity"] == "error" for i in issues) else "unknown",
                "issues": issues, "coverage": {"scope": "selected_pages", "status": "unknown", "checked": 0}}

    target = mapping["target"]["diameter_m"]
    expected_path = posixpath.normpath(capture["document"]["path"])
    expected_body = capture["geometry"]["body_name"]
    declared = {(row["page"], row["view"], row["dimension"]) for row in mapping["annotations"]}
    checked = set()
    enumerated = set()
    for page in drawing.get("pages", []):
        page_location = {"page": page["name"]}
        page_ready = state_ready(page.get("state", []), page_location) and document_ready
        if page.get("keep_updated") is False:
            issue("page_update_disabled", "unknown", "图纸页关闭了自动更新，尚不能确认投影与当前模型同步。", page_location,
                  "在 CAD 中检查该页的更新设置并明确更新，再重新读取。")
            page_ready = False
        for obj in page.get("unknown_objects", []):
            issue("unmapped_page_object", "unknown", "图纸页包含尚未检查的对象。", page_location,
                  "在 CAD 中核对该对象是否影响目标尺寸，并记录人工确认。", object=obj)
        for view in page.get("views", []):
            view_location = {**page_location, "view": view["name"]}
            view_ready = state_ready(view.get("state", []), view_location) and page_ready
            sources = view.get("sources", [])
            if not sources:
                issue("view_source_unknown", "unknown", "没有读到视图的原生模型引用。", view_location)
                view_ready = False
            elif len(sources) != 1:
                issue("view_source_ambiguous", "unknown", "当前视图引用多个模型源，超出单 Body 检查范围。", view_location)
                view_ready = False
            for source in sources:
                path = source.get("path")
                if not isinstance(path, str) or not path:
                    issue("view_source_unknown", "unknown", "视图引用缺少文档路径。", view_location)
                    view_ready = False
                elif posixpath.normpath(path) != expected_path or source.get("object") != expected_body:
                    issue("view_source_mismatch", "error", "视图引用的文件或 Body 与本次原生轴不一致。", view_location,
                          "在 CAD 中检查视图 Source；确认应使用的原件或副本后重新建立映射。",
                          expected={"path": expected_path, "object": expected_body}, actual=source)
                    view_ready = False
            for dimension in view.get("dimensions", []):
                location = {**view_location, "dimension": dimension["name"]}
                locator = tuple(location[key] for key in ("page", "view", "dimension"))
                enumerated.add(locator)
                ready = state_ready(dimension.get("state", []), location) and view_ready
                observed_issues(dimension.get("issues", []), location)
                reference_status = dimension.get("reference_status")
                if reference_status == "dangling":
                    issue("dangling_reference", "error", "标注的几何引用已失联。", location,
                          "在 CAD 中重新关联该标注，核对其实际含义后重新检查。")
                    ready = False
                elif reference_status != "valid":
                    issue("reference_unknown", "unknown", "尚不能确认标注的几何引用有效，当前读数不用于尺寸比较。", location)
                    ready = False
                if dimension.get("valid") is False:
                    issue("invalid_dimension", "error", "宿主报告此标注无效。", location)
                    ready = False
                elif dimension.get("valid") is not True:
                    issue("dimension_validity_unknown", "unknown", "未读取到标注有效性。", location)
                    ready = False
                refs2d, refs3d = dimension.get("references2d", []), dimension.get("references3d", [])
                if not refs2d and not refs3d:
                    issue("reference_unknown", "unknown", "标注没有可核对的二维或三维原生引用。", location)
                    ready = False
                for reference in refs2d:
                    if (reference.get("object") != view["name"]
                            or posixpath.normpath(reference.get("path", expected_path)) != expected_path):
                        issue("dimension_view_mismatch", "error", "标注的二维引用与映射视图不一致。", location)
                        ready = False
                for reference in refs3d:
                    if (reference.get("object") != expected_body
                            or reference.get("path", expected_path) != expected_path):
                        issue("dimension_model_mismatch", "error", "标注的三维引用与目标轴不一致。", location)
                        ready = False
                if dimension.get("arbitrary") is True:
                    issue("display_override", "error", "该标注启用了任意显示值；显示数字不能代表实际尺寸。", location,
                          "在 CAD 中检查并移除非预期显示覆盖，再核对原生测量值。",
                          display_text=dimension.get("display_text"), format_spec=dimension.get("format_spec"))
                elif dimension.get("arbitrary") is not False:
                    issue("override_unknown", "unknown", "尚未确认标注是否存在显示覆盖。", location)
                if dimension.get("arbitrary_tolerances") is True:
                    issue("tolerance_display_override", "unknown", "标注启用了任意公差显示，尚未核对其与数值公差的关系。", location)
                if locator not in declared:
                    # map_capture 已报告此项时不再重复，但独立使用本检查器也不能忽略它。
                    if not any(i["code"] == "annotation_unmapped" and i["location"] == location for i in issues):
                        issue("annotation_unmapped", "unknown", "此标注尚未确认与目标参数的关系。", location)
                    continue
                if dimension.get("type") != "Diameter":
                    issue("dimension_type_unknown", "unknown", "当前只验证 Diameter 标注与目标直径的对应关系。", location)
                    continue
                if not ready:
                    continue
                if dimension.get("raw_unit") != "mm" or dimension.get("measure_type") != "Projected":
                    issue("measurement_method_unknown", "unknown", "测量单位或方式超出当前已验证的毫米投影尺寸范围。", location)
                    continue
                measured, raw = dimension.get("measurement_m"), dimension.get("raw_value")
                if not _number(measured) or not _number(raw):
                    issue("measurement_unknown", "unknown", "没有读到可比较的原生尺寸。", location)
                    continue
                if not math.isclose(raw / 1000, measured, rel_tol=1e-8, abs_tol=1e-9):
                    issue("measurement_units_mismatch", "error", "原生毫米读数与归一后的米制值不一致。", location)
                    continue
                checked.add(locator)
                if not math.isclose(measured, target, rel_tol=1e-8, abs_tol=1e-9):
                    issue("measurement_mismatch", "error", "图纸实际测量值与当前目标轴段直径不一致。", location,
                          expected_mm=target * 1000, actual_mm=measured * 1000)
                text = dimension.get("display_text")
                spec = dimension.get("format_spec")
                precision = dimension.get("precision")
                format_match = _FORMAT.fullmatch(spec) if isinstance(spec, str) else None
                display_match = _DISPLAY_MM.fullmatch(text) if isinstance(text, str) else None
                if (dimension.get("display_unit") != "mm" or format_match is None or display_match is None
                        or type(precision) is not int or precision < 0 or int(format_match[1]) != precision):
                    issue("display_format_unknown", "unknown", "当前显示单位或格式未验证，不能确认显示值与模型一致。", location,
                          "在 CAD 中核对单位与显示格式；当前检查支持明确的毫米标注及 %.nw 格式。",
                          display_text=text, format_spec=spec)
                else:
                    display_mm = float(display_match[1])
                    half_step = 0.5 * 10.0 ** (-precision)
                    if not math.isfinite(display_mm) or abs(display_mm - measured * 1000) > half_step + 1e-8:
                        issue("display_value_mismatch", "error", "按显示精度核对后，图纸显示值仍与实际测量不一致。", location,
                              display_mm=display_mm, measured_mm=measured * 1000, precision=precision)
    for locator in declared - enumerated:
        issue("annotation_unavailable", "unknown", "本次采集未找到已确认的目标标注。",
              dict(zip(("page", "view", "dimension"), locator)))
    status = "fail" if any(i["severity"] == "error" for i in issues) else "unknown" if issues else "pass"
    return {"status": status, "issues": issues,
            "coverage": {"scope": "selected_pages", "status": "checked" if status == "pass" else "incomplete",
                         "declared": mapping.get("coverage", {}).get("declared", len(declared)), "checked": len(checked)},
            "limitations": ["只检查所选页的显式目标映射；不代替排版、技术要求或制造公差审核。"]}

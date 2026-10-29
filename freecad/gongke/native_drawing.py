"""FreeCAD 1.1.4 主线程的只读修订采集，不刷新、重算、绑定或保存工程。"""

from __future__ import annotations

import math
import re

from freecad.gongke import native_shaft


def _links(links):
    return [{"path": obj.Document.FileName, "object": obj.Name,
             "subelements": list(subs)} for obj, subs in links if obj is not None]


def _dimension(dim):
    references = _links(dim.References2D)
    issues = []
    reference_status = "valid"
    if not references:
        reference_status = "unknown"
        issues.append("标注没有可核对的二维引用")
    for view, subs in dim.References2D:
        if view is None or not subs:
            reference_status = "dangling"
            continue
        if not view.isDerivedFrom("TechDraw::DrawViewPart"):
            if reference_status != "dangling":
                reference_status = "unknown"
            issues.append("引用对象不是本次支持的零件投影视图")
            continue
        # 已保存图纸刚打开时，投影缓存可能尚未生成；getRawValue 此时会返回零。
        if not view.getVisibleEdges():
            if reference_status != "dangling":
                reference_status = "unknown"
            issues.append("视图没有可读投影，请在 CAD 打开图纸并完成更新后再检查")
            continue
        for name in subs:
            if not re.fullmatch(r"Edge[1-9][0-9]*", name):
                if reference_status != "dangling":
                    reference_status = "unknown"
                issues.append("当前仅验证直径标注的投影边引用")
                continue
            try:
                view.getEdgeByIndex(int(name[4:]))
            except (RuntimeError, ValueError):
                reference_status = "dangling"
    state = list(dim.State)
    raw_value = dim.getRawValue() if reference_status == "valid" else None
    if raw_value is not None and not math.isfinite(raw_value):
        raw_value = None
        issues.append("标注测量值不是有限数")
    text = dim.getText() if reference_status == "valid" else None
    format_spec = dim.FormatSpec
    precision = re.search(r"%\.(\d+)w", format_spec)
    return {
        "name": dim.Name, "label": dim.Label, "type": str(dim.Type),
        "measurement_m": raw_value / 1000 if raw_value is not None and dim.Type == "Diameter" else None,
        "raw_value": raw_value, "raw_unit": "mm" if dim.Type == "Diameter" else None,
        "display_text": text,
        "display_unit": "mm" if text is not None and re.search(r"\bmm\s*$", text) else None,
        "precision": int(precision[1]) if precision else None,
        "format_spec": format_spec, "arbitrary": bool(dim.Arbitrary),
        "arbitrary_tolerances": bool(dim.ArbitraryTolerances),
        "over_tolerance_m": dim.OverTolerance.Value / 1000,
        "under_tolerance_m": dim.UnderTolerance.Value / 1000,
        "references2d": references, "references3d": _links(dim.References3D),
        "reference_status": reference_status, "measure_type": str(dim.MeasureType),
        "valid": dim.isValid(), "state": state, "issues": issues,
    }


def capture(doc, body_name, page_names, session_id):
    """显式选择一个 Body 和有限图纸页；不改变选择、显示或正在编辑的事务。"""
    import FreeCAD as App
    import FreeCADGui as Gui

    if not isinstance(page_names, list) or not page_names or any(not isinstance(p, str) for p in page_names):
        raise ValueError("pages 必须明确列出要检查的 TechDraw 图纸页")
    if len(set(page_names)) != len(page_names):
        raise ValueError("pages 不得重复")
    body = doc.getObject(body_name)
    geometry = {"supported": False, "body_name": body_name}
    try:
        description = native_shaft._describe_simple_parts(body)
        sketch = doc.getObject(description["sketch"])
        geometry.update(description, supported=True,
                        structure_signature=native_shaft._constraint_signature(sketch))
        if hasattr(body, "GkEntityId"):
            geometry["entity_id"] = body.GkEntityId
    except (native_shaft.UnsupportedShaft, ValueError, AttributeError, TypeError) as exc:
        geometry["reason"] = str(exc)
    pages = []
    issues = []
    for name in page_names:
        page = doc.getObject(name)
        if page is None or page.TypeId != "TechDraw::DrawPage":
            raise ValueError(f"找不到指定 TechDraw 图纸页：{name}")
        members = list(page.Views)
        part_views = [v for v in members if v.TypeId == "TechDraw::DrawViewPart"]
        dimensions = [d for d in members if d.TypeId == "TechDraw::DrawViewDimension"]
        views = []
        attached = set()
        for view in part_views:
            linked = [d for d in dimensions if any(ref == view for ref, _ in d.References2D)]
            attached.update(d.Name for d in linked)
            views.append({
                "name": view.Name, "label": view.Label, "state": list(view.State),
                "sources": [{"path": obj.Document.FileName, "object": obj.Name} for obj in view.Source],
                "dimensions": [_dimension(d) for d in linked],
            })
        unknown = [{"name": obj.Name, "type": obj.TypeId} for obj in members
                   if obj not in part_views and (obj not in dimensions or obj.Name not in attached)]
        pages.append({"name": name, "label": page.Label, "state": list(page.State),
                      "keep_updated": bool(page.KeepUpdated), "views": views, "unknown_objects": unknown})
        if unknown:
            issues.append(f"{name} 含未映射或当前不支持的标注/视图，需人工核对")
    return {
        "schema_version": 1, "host": "freecad", "host_version": App.Version(),
        "session_id": session_id,
        "document": {"path": doc.FileName, "name": doc.Name,
                     "modified": bool(Gui.getDocument(doc.Name).Modified),
                     "pending_transaction": bool(doc.HasPendingTransaction),
                     "needs_rebuild": any("Touched" in obj.State for obj in doc.Objects)},
        "geometry": geometry,
        "drawing": {"pages": pages, "issues": issues,
                    "coverage": {"status": "partial" if issues else "complete", "scope": "selected_pages"}},
    }

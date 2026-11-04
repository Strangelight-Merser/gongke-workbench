"""图纸独立证据与直线正交轮廓核验。只读 PDF，不加载任何 CAD 内核。"""
from __future__ import annotations

import math
import re
from statistics import median

from gongke_app.drawing_input import read_drawing


class UnknownDrawing(ValueError):
    """不能从图纸唯一确定的事实。"""


def evidence_page(project, reference):
    if project is None:
        raise UnknownDrawing("缺少绑定工程")
    # 分页接口与 read_drawing 共用解析及内容哈希；每页均校验，禁止拼接变更前后的证据。
    items, offset = [], 0
    while True:
        data = read_drawing(project, reference["path"], page=reference["page"], offset=offset, limit=500)
        if data["sha256"] != reference["sha256"]:
            raise UnknownDrawing("图纸已改变，请重新读取依据")
        if data["format"] != "pdf":
            raise UnknownDrawing("独立核验目前只支持矢量 PDF")
        items.extend(data["items"])
        if data["next_offset"] is None:
            break
        offset = data["next_offset"]
    return {**data, "items": items}


def annotation(project, reference):
    data = evidence_page(project, reference)
    found = [r for r in data["items"] if r["source"] == reference["item"] and r["type"] == "text"]
    if len(found) != 1 or not re.fullmatch(r"(?:\d+(?:\.\d+)?)", found[0]["text"]):
        raise UnknownDrawing("标注不是独立的纯数值尺寸；复合标注尚未支持")
    candidates = []
    for width in sorted({r.get("linewidth", 0) for r in data["items"] if r["type"] == "lines"}):
        vertices = [p for r in data["items"] if r["type"] == "lines" and abs(r.get("linewidth", 0)-width) < .01 for p in r["pts"]]
        candidates.extend(a for a in dimension_associations(data["items"], vertices, width) if a["item"] == reference["item"])
    if len(candidates) != 1:
        raise UnknownDrawing("文字未唯一关联尺寸线、界线与几何顶点")
    return float(found[0]["text"]), {**reference, **candidates[0], "kind": "drawing_annotation", "text": found[0]["text"],
                                   "bbox": [found[0][k] for k in ("x0", "top", "x1", "bottom")]}


def distance(a, b):
    return math.dist(a, b)


def inside(p, polygon):
    x, y = p
    hit = False
    for a, b in zip(polygon, polygon[1:] + polygon[:1]):
        if (a[1] > y) != (b[1] > y) and x < (b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0]:
            hit = not hit
    return hit


def bounds(points):
    return [min(p[i] for p in points) for i in range(2)] + [max(p[i] for p in points) for i in range(2)]


def components(rows):
    nodes = {}
    for i, row in enumerate(rows):
        for p in row["pts"]:
            nodes.setdefault(tuple(round(v, 3) for v in p), []).append(i)
    remaining, result = set(range(len(rows))), []
    while remaining:
        pending, found = [min(remaining)], []
        while pending:
            i = pending.pop()
            if i not in remaining:
                continue
            remaining.remove(i)
            found.append(rows[i])
            for p in rows[i]["pts"]:
                pending.extend(nodes[tuple(round(v, 3) for v in p)])
        result.append(found)
    return result


def cycles(rows):
    """只接受端点度数为 2 的闭合线框；不补线，不猜分叉。PDF 点量化为 0.001 pt。"""
    nodes, edges = {}, []
    for row in rows:
        a, b = [tuple(round(v, 3) for v in p) for p in row["pts"]]
        if a == b:
            raise UnknownDrawing("轮廓包含退化边")
        idx = len(edges)
        edges.append((a, b, row))
        nodes.setdefault(a, []).append(idx)
        nodes.setdefault(b, []).append(idx)
    remaining, result = set(range(len(edges))), []
    while remaining:
        start = edges[min(remaining)][0]
        point, polygon, members = start, [], []
        while True:
            if len(nodes[point]) != 2:
                raise UnknownDrawing("轮廓开放或有分叉")
            choices = [e for e in nodes[point] if e in remaining]
            if not choices:
                raise UnknownDrawing("轮廓不能闭合")
            idx = choices[0]
            remaining.remove(idx)
            a, b, row = edges[idx]
            polygon.append(point)
            members.append(row)
            point = b if a == point else a
            if point == start:
                break
        if len(polygon) < 3:
            raise UnknownDrawing("重复边或退化轮廓")
        result.append((polygon, members))
    # 非相邻线段相交意味着自交/重叠；不把这种路径当作可用轮廓。
    for polygon, _ in result:
        segments = list(zip(polygon, polygon[1:]+polygon[:1]))
        for i, (a, b) in enumerate(segments):
            for j, (c, d) in enumerate(segments):
                if j <= i+1 or (i == 0 and j == len(segments)-1):
                    continue
                def side(p, q, r):
                    return (q[0]-p[0])*(r[1]-p[1])-(q[1]-p[1])*(r[0]-p[0])
                if side(a,b,c)*side(a,b,d) < 0 and side(c,d,a)*side(c,d,b) < 0:
                    raise UnknownDrawing("轮廓自交")
    return result


def dimension_associations(items, vertices, width):
    """纯数字文字 + 紧邻尺寸线 + 两端垂直界线；界线起点必须落在轮廓顶点上。"""
    lines = [r for r in items if r["type"] == "lines" and r.get("stroke") and not r.get("dash")
             and 0 < r.get("linewidth", 0) < width - .01]
    associations = []
    for word in items:
        if word["type"] != "text" or not re.fullmatch(r"\d+(?:\.\d+)?", word["text"]) or float(word["text"]) <= 0:
            continue
        rotation = word.get("rotation_degrees", 0)
        if rotation not in (0, 90):
            continue
        axis = 0 if rotation == 0 else 1
        other = 1-axis
        center = [(word["x0"]+word["x1"])/2, (word["top"]+word["bottom"])/2]
        baseline = word["bottom"] if axis == 0 else word["x1"]
        candidates = []
        for line in lines:
            a, b = line["pts"]
            lo, hi = sorted((a[axis], b[axis]))
            if abs(a[other]-b[other]) > .1 or hi-lo < 1 or not lo < center[axis] < hi:
                continue
            if abs(a[other]-baseline) > 1:
                continue
            extensions = []
            for endpoint in (a, b):
                matching = []
                for ext in lines:
                    c, d = ext["pts"]
                    if abs(c[axis]-d[axis]) > .1 or abs(c[axis]-endpoint[axis]) > .15:
                        continue
                    if not min(c[other], d[other])-.15 <= endpoint[other] <= max(c[other], d[other])+.15:
                        continue
                    if any(min(distance(c, v), distance(d, v)) < .2 for v in vertices):
                        matching.append(ext)
                if len(matching) != 1:
                    break
                extensions.append(matching[0]["source"])
            if len(extensions) == 2:
                candidates.append({"text": word["text"], "item": word["source"], "axis": axis,
                                   "bbox": [word[k] for k in ("x0", "top", "x1", "bottom")],
                                   "dimension_line": line["source"], "extension_lines": extensions,
                                   "pt_per_mm": (hi-lo)/float(word["text"])})
        if len(candidates) == 1:
            associations.extend(candidates)
    return associations


def dimension_scales(items, vertices, width):
    associations = dimension_associations(items, vertices, width)
    if {a["axis"] for a in associations} != {0, 1}:
        raise UnknownDrawing("缺少两个正交方向可唯一关联的尺寸标注")
    scale = median(a["pt_per_mm"] for a in associations)
    if any(abs(a["pt_per_mm"]/scale-1) > .005 for a in associations):
        raise UnknownDrawing("尺寸比例不一致；可能存在断裂视图或非等比图纸")
    return scale, associations


def extract_outline(data, seed):
    items = data["items"]
    selected = next((r for r in items if r["source"] == seed), None)
    if not selected or selected["type"] != "lines" or selected.get("dash"):
        raise UnknownDrawing("视图种子必须是实线轮廓边")
    width = selected.get("linewidth", 0)
    # 同线宽的所有线框先建立连通分量；种子只能选完整外轮廓，不接受逐边白名单。
    rows = [r for r in items if r["type"] == "lines" and abs(r.get("linewidth", 0)-width) < .01 and not r.get("dash")]
    groups = components(rows)
    outer_rows = next(group for group in groups if any(r["source"] == seed for r in group))
    connected = {r["source"] for r in outer_rows}
    outer_cycles = cycles(outer_rows)
    if len(outer_cycles) != 1:
        raise UnknownDrawing("视图外轮廓不唯一")
    outer = outer_cycles[0][0]
    box = bounds(outer)
    if any(r["x0"] < box[2] and r["x1"] > box[0] and r["top"] < box[3] and r["bottom"] > box[1]
           for r in data["raster_regions"]):
        raise UnknownDrawing("所选视图与栅格图像重叠")
    def within(p):
        return box[0]-.01 <= p[0] <= box[2]+.01 and box[1]-.01 <= p[1] <= box[3]+.01
    # 拒绝内孔作为视图种子：相同线宽、包围种子的大线框必须也纳入。
    others = [r for r in rows if r["source"] not in connected]
    # 只对与候选包围盒相交的线条要求闭合；其他视图不影响当前视图。
    relevant = [r for r in others if any(within(p) for p in r["pts"])]
    all_rows = outer_rows + relevant
    loops = cycles(all_rows)
    for polygon, _ in loops:
        if polygon != outer and not all(inside(p, outer) for p in polygon):
            raise UnknownDrawing("视图边界相交，不能分离内外轮廓")
    # 完整页面中可能有包围种子的外框，逐个连通分量检查，而非依赖请求裁切。
    for component in components([r for r in others if r not in relevant]):
        try:
            enclosing = cycles(component)
        except UnknownDrawing:
            continue  # 不相交的其他视图无需闭合；不能作为当前视图的证据。
        if any(inside(outer[0], poly) for poly, _ in enclosing):
            raise UnknownDrawing("种子是内轮廓，请选择零件外轮廓")
    # 轮廓线宽不一致时不丢弃内部孔；较细闭合实线是未分类几何，必须未知。
    thin = [r for r in items if r["type"] == "lines" and not r.get("dash")
            and r.get("linewidth", 0) < width-.01 and all(within(p) for p in r["pts"])]
    for component in components(thin):
        try:
            loops_thin = cycles(component)
        except UnknownDrawing:
            continue  # 开放尺寸界线不构成内环。
        if loops_thin:
            raise UnknownDrawing("视图包含不同线宽的闭合几何，不能唯一分类")
    for r in items:
        dash = r.get("dash")
        if dash and r["type"] in ("lines", "curves") and r["x0"] <= box[2] and r["x1"] >= box[0] and r["top"] <= box[3] and r["bottom"] >= box[1]:
            pattern = dash[0]
            centerline = len(pattern) == 4 and pattern[0] > 3*max(pattern[1:]) and r.get("linewidth", 0) < width-.01
            if not centerline:
                raise UnknownDrawing("所选视图含隐藏线或无法分类的虚线")
        if r["type"] not in ("lines", "curves", "rects") or r in all_rows:
            continue
        if (r.get("linewidth", 0) >= width-.01 or r["type"] in ("curves", "rects")) and any(within(p) for p in r.get("pts", [])):
            raise UnknownDrawing("视图含曲线、隐藏线或未分离的几何")
    vertices = [p for polygon, _ in loops for p in polygon]
    scale, dimensions = dimension_scales(items, vertices, width)
    return all_rows, box, scale, dimensions


def uncovered(edge, others, tolerance):
    """线段并集覆盖（允许 CAD 把同一直线拆成多边）；不靠面积或离散点相似度。"""
    a, b = edge
    length = distance(a, b)
    if length <= 1e-12:
        return True
    direction = [(b[i]-a[i])/length for i in range(2)]
    intervals = []
    for c, d in others:
        cross = lambda p: abs((p[0]-a[0])*direction[1]-(p[1]-a[1])*direction[0])
        if max(cross(c), cross(d)) > tolerance:
            continue
        project = lambda p: sum((p[i]-a[i])*direction[i] for i in range(2))
        lo, hi = sorted((project(c), project(d)))
        intervals.append((lo, hi))
    end = 0
    for lo, hi in sorted(intervals):
        if hi < end:
            continue
        if lo > end+tolerance:
            return True
        end = max(end, hi)
        if end >= length-tolerance:
            return False
    return end < length-tolerance


def compare_section(snapshot, cut, data, request):
    result = {"id": "drawing_outline", "source_kind": "drawing_geometry", "status": "unknown",
              "source": request["path"], "evidence": {k: request[k] for k in ("path", "sha256", "page", "outline_seed")},
              "scope": "所选视图与指定截面的直线轮廓；不代表整张图纸或全部三维特征通过",
              "actual": {"locations": []}}
    try:
        if snapshot["state"] != "ready" or cut.get("status") != "ok":
            raise UnknownDrawing("模型或截面未就绪")
        if cut["document"] != snapshot["document"] or cut["object_ref"] != snapshot["object_ref"]:
            raise UnknownDrawing("截面对象或修订与模型不一致")
        if any(abs(a-b) > 1e-10 for a, b in zip(cut["plane"]["origin"], request["plane"]["origin"])):
            raise UnknownDrawing("宿主返回的截面位置与请求不一致")
        cross = [cut["plane"]["normal"][i] for i in range(3)]
        target = request["plane"]["normal"]
        if sum(v*v for v in cross) == 0 or sum(v*v for v in target) == 0 or any(
                abs(cross[i]*target[j]-cross[j]*target[i]) > 1e-10 for i in range(3) for j in range(3)):
            raise UnknownDrawing("宿主返回的截面法向与请求不一致")
        rows, box, scale, dimensions = extract_outline(data, request["outline_seed"])
        axes = request["axes"]
        if len({abs(a) for a in axes}) != 2:
            raise UnknownDrawing("视图两轴必须正交")
        # axes 是页面向右、向上的模型有向坐标轴（±1/±2/±3）。不做最佳拟合或镜像搜索。
        normal_axis = next(i for i in range(3) if i+1 not in {abs(a) for a in axes})
        normal = request["plane"]["normal"]
        if not normal[normal_axis] or any(abs(normal[i]) > 1e-10 for i in range(3) if i != normal_axis):
            raise UnknownDrawing("截面法向与所选视图轴不一致")
        edges = cut.get("edges", [])
        if not edges or any(e["kind"] != "line" for e in edges):
            raise UnknownDrawing("截面为空或包含非直线边")
        def project(p):
            return [p[abs(a)-1]*(1 if a > 0 else -1)*1000 for a in axes]
        actual = [(project(e["start"]), project(e["end"])) for e in edges]
        ab = bounds([p for e in actual for p in e])
        center = [(ab[i]+ab[i+2])/2 for i in range(2)]
        def mapped(p):
            return [(p[0]-(box[0]+box[2])/2)/scale+center[0],
                    ((box[1]+box[3])/2-p[1])/scale+center[1]]
        expected = [tuple(mapped(p) for p in r["pts"]) for r in rows]
        tolerance = .05  # mm；覆盖 PDF 坐标量化误差，不允许调用者放大容差掩盖错误。
        missing = [j for j, e in enumerate(expected) if uncovered(e, actual, tolerance)]
        extra = [j for j, e in enumerate(actual) if uncovered(e, expected, tolerance)]
        def world(p):
            xyz = list(request["plane"]["origin"])
            for i, a in enumerate(axes):
                xyz[abs(a)-1] = p[i]/1000*(1 if a > 0 else -1)
            return xyz
        locations = [{"object_ref": snapshot["object_ref"], "plane": cut["plane"],
                      "edges": [edges[j] for j in extra], "difference": "extra_or_shifted"},
                     {"object_ref": snapshot["object_ref"], "plane": cut["plane"], "difference": "missing_or_shifted",
                      "edges": [{"start": world(expected[j][0]), "end": world(expected[j][1]),
                                 "drawing_item": rows[j]["source"]} for j in missing]}]
        return {**result, "status": "fail" if missing or extra else "pass", "tolerance_mm": tolerance,
                "registration": "以完整外包络中心平移对齐；比例仅来自图纸尺寸，不检查模型全局放置",
                "pt_per_mm": scale, "dimensions": dimensions, "drawing_edge_count": len(rows),
                "drawing_items": [r["source"] for r in rows],
                "drawing_view": {"page": request["page"], "coordinates": data["coordinates"],
                                 "segments": [{"item": rows[j]["source"], "points": rows[j]["pts"],
                                               "world": [world(expected[j][0]), world(expected[j][1])],
                                               "model_edges": [edges[k] for k in extra
                                                               if any(distance(a, b) <= tolerance for a in expected[j] for b in actual[k])]}
                                              for j in missing]},
                "missing_or_shifted": [rows[j]["source"] for j in missing],
                "extra_or_shifted": [edges[j]["native_ref"] for j in extra], "actual": {"locations": locations}}
    except UnknownDrawing as exc:
        return {**result, "reason": str(exc)}


def check_drawing(project, snapshot, section, request):
    try:
        data = evidence_page(project, request)
    except (UnknownDrawing, ValueError, OSError) as exc:
        return {"id": "drawing_outline", "source_kind": "drawing_geometry", "status": "unknown", "reason": str(exc),
                "actual": {"locations": []}}
    cut = section(request["plane"])
    return compare_section(snapshot, cut, data, request)

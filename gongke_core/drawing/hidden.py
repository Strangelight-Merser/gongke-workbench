"""简单的消隐：画在后面的线被前面的圆形或矩形零件挡住的部分不画。

装配图的主视图中，轴承盖、轴承座（沿视线方向是圆）挡住后面的凸缘、箱壁和螺栓；
左视图中各零件的投影都是矩形，按离观察者的远近依次绘制、互相遮挡。
这里只处理这两种遮挡体，足够满足减速器装配图的需要。
"""

from __future__ import annotations

import math

Circle = tuple[float, float, float]  # cx, cy, r
Rect = tuple[float, float, float, float]  # x0, y0, x1, y1


def _subtract(intervals: list[tuple[float, float]], cut: tuple[float, float]) -> list[tuple[float, float]]:
    a, b = cut
    out = []
    for lo, hi in intervals:
        if b <= lo or a >= hi:
            out.append((lo, hi))
            continue
        if a > lo:
            out.append((lo, a))
        if b < hi:
            out.append((b, hi))
    return out


def _seg_circle(p, q, c: Circle) -> tuple[float, float] | None:
    """线段 p + t(q − p) 落在圆内部的参数区间。"""
    (px, py), (qx, qy) = p, q
    cx, cy, r = c
    dx, dy = qx - px, qy - py
    fx, fy = px - cx, py - cy
    a = dx * dx + dy * dy
    if a < 1e-18:
        return None
    b = 2 * (fx * dx + fy * dy)
    cc = fx * fx + fy * fy - r * r
    disc = b * b - 4 * a * cc
    if disc <= 0:
        return None
    s = math.sqrt(disc)
    return (-b - s) / (2 * a), (-b + s) / (2 * a)


def _seg_rect(p, q, rc: Rect) -> tuple[float, float] | None:
    """线段落在矩形内部（开区域）的参数区间（Liang–Barsky）。"""
    (px, py), (qx, qy) = p, q
    x0, y0, x1, y1 = min(rc[0], rc[2]), min(rc[1], rc[3]), max(rc[0], rc[2]), max(rc[1], rc[3])
    eps = 1e-7
    dx, dy = qx - px, qy - py
    t0, t1 = 0.0, 1.0
    for pp, qq in ((-dx, px - (x0 + eps)), (dx, (x1 - eps) - px), (-dy, py - (y0 + eps)), (dy, (y1 - eps) - py)):
        if abs(pp) < 1e-15:
            if qq < 0:
                return None
            continue
        t = qq / pp
        if pp < 0:
            t0 = max(t0, t)
        else:
            t1 = min(t1, t)
    if t0 >= t1:
        return None
    return t0, t1


def visible_segments(p, q, circles: list[Circle] = (), rects: list[Rect] = ()) -> list[tuple[tuple, tuple]]:
    pieces = [(0.0, 1.0)]
    for c in circles:
        iv = _seg_circle(p, q, c)
        if iv:
            pieces = _subtract(pieces, iv)
    for rc in rects:
        iv = _seg_rect(p, q, rc)
        if iv:
            pieces = _subtract(pieces, iv)
    (px, py), (qx, qy) = p, q
    out = []
    for a, b in pieces:
        if b - a > 1e-6:
            out.append(((px + a * (qx - px), py + a * (qy - py)), (px + b * (qx - px), py + b * (qy - py))))
    return out


def _norm(a: float) -> float:
    return a % 360.0


def visible_arcs(cx, cy, r, a0, a1, circles: list[Circle] = ()) -> list[tuple[float, float]]:
    """圆弧（a0 → a1 逆时针，度）在各遮挡圆外的部分。"""
    span = (a1 - a0) % 360.0 or 360.0
    pieces = [(0.0, span)]
    for ox, oy, orr in circles:
        d = math.hypot(ox - cx, oy - cy)
        if d + r <= orr + 1e-9:
            return []
        if d >= r + orr or d + orr <= r or d < 1e-12:
            continue
        cos_t = (r * r + d * d - orr * orr) / (2 * r * d)
        half = math.degrees(math.acos(max(-1.0, min(1.0, cos_t))))
        mid = math.degrees(math.atan2(oy - cy, ox - cx))
        lo = _norm(mid - half - a0)
        for k in (-360.0, 0.0, 360.0):
            pieces = _subtract(pieces, (lo + k, lo + k + 2 * half))
    return [(a0 + lo, a0 + hi) for lo, hi in pieces if hi - lo > 1e-6]

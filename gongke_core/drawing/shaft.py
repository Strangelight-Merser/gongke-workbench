"""轴（含齿轮轴）零件图。

主视图轴线水平，键槽转到朝向观察者；每个键槽在主视图下方配一个移出断面图。
尺寸：各段直径（配合段注公差带代号）、轴向长度（留一个最长的非配合段不注，避免封闭尺寸链）、
总长、键槽长度和位置；断面图注键宽和槽底尺寸 d − t1。
表面结构、基准、圆跳动按课程设计常用要求标注。
"""

from __future__ import annotations

from pathlib import Path

from gongke_core.design import ReducerDesign, ShaftResult
from gongke_core.drawing import material_name
from gongke_core.drawing.sheet import Sheet, TitleInfo, View, pick_scale

FITS = {"端部": "k6", "轴承": "k6", "齿轮": "r6"}
RA = {"端部": "Ra 1.6", "轴承": "Ra 0.8", "齿轮": "Ra 1.6", "密封": "Ra 3.2"}
RUNOUT = {"齿轮": "0.020", "端部": "0.025", "齿轮轴": "0.025"}


def _chamfer(d_mm: float) -> float:
    return 1.0 if d_mm <= 30 else 1.5 if d_mm <= 50 else 2.0


def draw(design: ReducerDesign, sr: ShaftResult, path: str | Path, drawing_no: str = "") -> Sheet:
    lay = sr.layout
    segs = lay.segments
    z_start = segs[0].z0
    S = [((s.z0 - z_start) * 1e3, (s.z1 - z_start) * 1e3, s) for s in segs]  # (x0, x1, seg) in mm
    L = S[-1][1]
    pairs = {"high": design.high, "low": design.low}
    integral = next((g for g in lay.gears if g.integral), None)
    tip_d = integral.tip_d * 1e3 if integral else 0
    d_max = max(max((s.root_d or s.d) * 1e3 for _, _, s in S), tip_d)

    # 选图幅和比例：主视图 + 下方断面图
    for size in ("A3", "A2", "A1"):
        sh = Sheet(size)
        x0, y0, x1, y1 = sh.inner
        avail_w = x1 - x0 - 40 - (85 if integral else 0)  # 齿轮轴右上角留出参数表
        avail_h = (y1 - y0 - 56 - 30) / 2.2
        s = pick_scale(L, d_max, avail_w, avail_h)
        if s >= 0.5 or size == "A1":
            break
    cx = x0 + 20 + (avail_w - L * s) / 2
    cy = y1 - 20 - (y1 - y0 - 56) * 0.32
    v = View(sh, (cx, cy), s)

    # ------------------------------------------------ 主视图外形
    prev_r = None
    for i, (a, b, seg) in enumerate(S):
        r = seg.d * 1e3 / 2
        if seg.role == "齿轮轴":
            g = integral
            pair = pairs[g.pair]
            ra, rf, rp = g.tip_d * 1e3 / 2, g.root_d * 1e3 / 2, pair.d1 * 1e3 / 2
            for sgn in (1, -1):
                v.line((a, sgn * ra), (b, sgn * ra))
                v.line((a, sgn * rf), (b, sgn * rf), "细实线")
                v.line((a - 2 / s, sgn * rp), (b + 2 / s, sgn * rp), "点画线")
            r_draw = ra
        else:
            c = _chamfer(seg.d * 1e3) if i in (0, len(S) - 1) else 0
            aa = a + (c if i == 0 else 0)
            bb = b - (c if i == len(S) - 1 else 0)
            for sgn in (1, -1):
                v.line((aa, sgn * r), (bb, sgn * r))
            if i == 0:
                v.line((a, -(r - c)), (a, r - c))
                for sgn in (1, -1):
                    v.line((a, sgn * (r - c)), (aa, sgn * r))
                v.line((aa, -r), (aa, r), "细实线")
            if i == len(S) - 1:
                v.line((b, -(r - c)), (b, r - c))
                for sgn in (1, -1):
                    v.line((b, sgn * (r - c)), (bb, sgn * r))
                v.line((bb, -r), (bb, r), "细实线")
            r_draw = r
        if prev_r is not None:
            rr = max(prev_r, r_draw)
            v.line((a, -rr), (a, rr))
        prev_r = r_draw
    v.centerline((0, 0), (L, 0), 5)

    # ------------------------------------------------ 键槽（主视图）与断面图
    sections = []
    for a, b, seg in S:
        if not seg.keyway:
            continue
        kb, t1, kl = (x * 1e3 for x in seg.keyway)
        xm = (a + b) / 2
        ka, kz = xm - kl / 2, xm + kl / 2
        v.line((ka + kb / 2, kb / 2), (kz - kb / 2, kb / 2))
        v.line((ka + kb / 2, -kb / 2), (kz - kb / 2, -kb / 2))
        sh.arc(v.P(ka + kb / 2, 0), kb / 2 * s, 90, 270, "粗实线")
        sh.arc(v.P(kz - kb / 2, 0), kb / 2 * s, -90, 90, "粗实线")
        sections.append((xm, seg, kb, t1, kl, ka, kz))

    letters = "ABCDEFG"
    sec_y = cy - (d_max / 2) * s - 62 - max((sec[1].d * 1e3 for sec in sections), default=0) * s / 2
    sec_x = x0 + 40
    for k, (xm, seg, kb, t1, kl, ka, kz) in enumerate(sections):
        letter = letters[k]
        r = seg.d * 1e3 / 2
        sh.cut_marks(v.P(xm, 0)[0], v.P(xm, r)[1] + 3, v.P(xm, -r)[1] - 3, letter)
        # 断面图：放在主视图下方，从左向右排列
        rs = r * s
        c = (max(sec_x + rs + 10, v.P(xm, 0)[0]) if k == 0 else sec_x + rs + 10, sec_y)
        sec_x = c[0] + rs + 25
        import math
        hb = kb / 2 * s
        top = rs - t1 * s
        ang = math.degrees(math.asin(min(hb / rs, 1)))
        sh.arc(c, rs, 90 + ang, 90 - ang + 360, "粗实线")
        sh.line((c[0] - hb, c[1] + math.sqrt(rs**2 - hb**2)), (c[0] - hb, c[1] + top))
        sh.line((c[0] + hb, c[1] + math.sqrt(rs**2 - hb**2)), (c[0] + hb, c[1] + top))
        sh.line((c[0] - hb, c[1] + top), (c[0] + hb, c[1] + top))
        loop = [(c[0] + hb, c[1] + top), (c[0] - hb, c[1] + top)]
        n = 48
        a0, a1 = math.radians(90 + ang), math.radians(90 - ang + 360)
        for j in range(n + 1):
            t = a0 + (a1 - a0) * j / n
            loop.append((c[0] + rs * math.cos(t), c[1] + rs * math.sin(t)))
        sh.hatch([loop])
        sh.cross(c, rs, 3)
        sh.section_label(c[0], c[1] + rs + 13, letter)
        sh.dim((c[0] - hb, c[1] + top), (c[0] + hb, c[1] + top), (c[0], c[1] + rs + 3.5), 0,
               f"<>N9", s, 0)
        sh.dim((c[0], c[1] - rs), (c[0], c[1] + top), (c[0] + rs + 6, c[1]), 90, "<>", s, 1)
        sh.roughness(c[0] + hb, c[1] + top + 1, "Ra 3.2", h=2.5)

    # ------------------------------------------------ 尺寸
    seen = set()
    for a, b, seg in S:
        d = (seg.d if seg.role != "齿轮轴" else integral.tip_d) * 1e3
        key = (round(d, 2), seg.role)
        xm = (a + b) / 2
        if seg.keyway:
            xm = a + (b - a) * 0.2
        if seg.role == "退刀" or key in seen:
            continue
        seen.add(key)
        fit = FITS.get(seg.role, "")
        txt = f"%%c<>{fit}" if seg.role != "齿轮轴" else "%%c<>h11"
        narrow = (b - a) * s < 14
        if seg.keyway or narrow:
            # 文字放不下或与键槽重叠：把文字引到轴的下方
            xm = (a + b) / 2 if narrow else a + (b - a - seg.keyway[2] * 1e3) / 4
            lx, ly = v.P(xm, -d / 2)
            sh.dim(v.P(xm, -d / 2), v.P(xm, d / 2), v.P(xm, 0), 90, txt, s, 1 if d % 1 else 0,
                   location=(lx - 12 if seg.role == "轴承" else lx + 4, ly - 9))  # 轴承段下方有基准符号，文字放左边
        else:
            v.dim((xm, -d / 2), (xm, d / 2), (xm, 0), 90, txt, 1 if d % 1 else 0)
    # 轴向尺寸链（下方），最长的非配合段不注
    fit_roles = set(FITS) | {"齿轮轴"}
    free = max((t for t in S if t[2].role not in fit_roles), key=lambda t: t[1] - t[0], default=None)
    y_chain = -(d_max / 2) - 24 / s
    for a, b, seg in S:
        if free is not None and seg is free[2]:
            continue
        v.dim((a, -(seg.root_d or seg.d) * 1e3 / 2), (b, -(seg.root_d or seg.d) * 1e3 / 2), (a, y_chain), 0, "<>", 0)
    v.dim((0, -S[0][2].d * 1e3 / 2), (L, -S[-1][2].d * 1e3 / 2), (0, y_chain - 10 / s), 0, "<>", 0)
    # 键槽长度与定位（上方）
    for xm, seg, kb, t1, kl, ka, kz in sections:
        r = seg.d * 1e3 / 2
        a = next(t[0] for t in S if t[2] is seg)
        v.dim((ka, kb / 2), (kz, kb / 2), (ka, r + 12 / s), 0, "<>", 0)
        if ka - a > 0.5:
            v.dim((a, r), (ka, kb / 2), (a, r + 12 / s), 0, "<>", 0)

    # ------------------------------------------------ 表面结构、基准、跳动
    datums = []
    for a, b, seg in S:
        r = (seg.d if seg.role != "齿轮轴" else integral.tip_d) * 1e3 / 2
        xm = (a + b) / 2
        if seg.role in RA:
            sh.roughness(*v.P(a + (b - a) * 0.82, r), RA[seg.role], h=3.0)
        if seg.role == "轴承":
            datums.append((xm, r))
    if len(datums) >= 2:
        for (xm, r), letter in zip((datums[0], datums[-1]), "AB"):
            sh.datum(*v.P(xm, -r), letter, "down")
        for a, b, seg in S:
            if seg.role in RUNOUT:
                r = (seg.d if seg.role != "齿轮轴" else integral.tip_d) * 1e3 / 2
                xm = (a + b) / 2
                px, py = v.P(a + (b - a) * 0.3, r)
                fx, fy = px - 6, py + 24
                sh.arrow((fx, fy), (px, py), 2.5, "细实线")
                sh.gtol(fx, fy, "runout", RUNOUT[seg.role], "A-B")

    # ------------------------------------------------ 图框
    is_gear_shaft = integral is not None
    mat = material_name(pairs[integral.pair].inp.material1) if is_gear_shaft else "45"
    name = lay.name.split("（")[0] + ("（齿轮轴）" if is_gear_shaft else "")
    reqs = [f"{'调质处理 241～286HBW' if mat.startswith('40Cr') else '调质处理 217～255HBW'}。",
            "未注倒角 C1.5，未注圆角 R1。",
            "未注尺寸公差按 GB/T 1804-m。",
            "未注几何公差按 GB/T 1184-K。"]
    if is_gear_shaft:
        from gongke_core.drawing.gear import param_table
        param_table(sh, pairs[integral.pair], integral.member)
    sh.frame(TitleInfo(name, mat, s, "1", drawing_no), reqs, "Ra 6.3")
    sh.save(path)
    return sh

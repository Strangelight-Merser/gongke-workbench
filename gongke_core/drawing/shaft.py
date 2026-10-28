"""轴（含齿轮轴）零件图。

主视图轴线水平，键槽转到朝向观察者；每个键槽在主视图下方配一个移出断面图。
尺寸：各段直径（配合段注极限偏差）、轴向长度（留一个最长的非配合段不注，避免封闭尺寸链）、
总长、键槽长度和位置；断面图注键宽和槽底尺寸 d − t1（均带极限偏差）及键槽对称度。
几何公差：配合段对公共轴线 A-B 的径向圆跳动，轴承轴颈圆柱度和轴承定位轴肩端面圆跳动（GB/T 275），
键槽对称度（GB/T 1184 8 级）。
"""

from __future__ import annotations

import math
from pathlib import Path

from gongke_core.calc import tolerance as tol
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
    pairs = {"high": design.high, "low": getattr(design, "low", None), "bevel": getattr(design, "bevel", None),
             "worm": getattr(design, "worm", None)}
    integral = next((g for g in lay.gears if g.integral), None)
    bevel = None  # 锥齿轮轴：齿部轮廓（x, r），x 为图上沿轴线的坐标（mm）
    if integral is not None and integral.pair == "bevel":
        from gongke_core.layout.bevel_blank import blank as bevel_blank

        ps = design.pinion
        gb = bevel_blank(design.bevel, 1, ps.diameters["齿轮"], ps.pinion_length)
        X = lambda p: ((p[0] - z_start) * 1e3, p[1] * 1e3)  # noqa: E731
        bevel = {"tipS": X(gb.tip_small), "tipL": X(gb.tip_large), "rootL": X(gb.root_large),
                 "rootS": X(gb.root_small), "K": X(gb.back_point), "rh": gb.hub_r * 1e3,
                 "R": gb.R * 1e3, "delta": gb.delta, "x_apex": -z_start * 1e3}
    tip_d = integral.tip_d * 1e3 if integral else 0
    d_max = max(max((s.root_d or s.d) * 1e3 for _, _, s in S), tip_d)

    # 选图幅和比例：主视图 + 下方断面图；断面图不得压到标题栏和技术要求
    keyed = [((a + b) / 2, seg.d * 1e3) for a, b, seg in S if seg.keyway]
    d_key = max((dk for _, dk in keyed), default=0)

    def sections_fit(sh, s, cx, cy):
        x0, y0, x1, y1 = sh.inner
        sec_y = cy - (d_max / 2) * s - 62 - d_key * s / 2
        sx = x0 + 40
        for k, (xm, dk) in enumerate(keyed):
            rs = dk / 2 * s
            c = max(sx + rs + 10, cx + xm * s) if k == 0 else sx + rs + 10
            sx = c + rs + 45  # 留出键槽对称度框格
            low = y0 + 64 if c + rs > x1 - 335 else y0 + 5
            if sec_y - rs < low or c + rs > x1 - 5:
                return False
        return True

    from gongke_core.drawing.sheet import SCALES
    for size in ("A3", "A2", "A1"):
        sh = Sheet(size)
        x0, y0, x1, y1 = sh.inner
        avail_w = x1 - x0 - 40 - (85 if integral else 0)  # 齿轮轴右上角留出参数表
        avail_h = (y1 - y0 - 56 - 30) / 2.2
        s = pick_scale(L, d_max, avail_w, avail_h)
        cy = y1 - 20 - (y1 - y0 - 56) * 0.32
        while not sections_fit(sh, s, x0 + 20 + (avail_w - L * s) / 2, cy) and s > SCALES[0]:
            s = max(v for v in SCALES if v < s)
        if s >= 0.5 or size == "A1":
            break
    cx = x0 + 20 + (avail_w - L * s) / 2
    v = View(sh, (cx, cy), s)

    # ------------------------------------------------ 主视图外形
    prev_r = None
    for i, (a, b, seg) in enumerate(S):
        r = seg.d * 1e3 / 2
        if seg.role == "齿轮轴" and bevel is not None:
            tS, tL, rL, rS, K, rh = (bevel[k] for k in ("tipS", "tipL", "rootL", "rootS", "K", "rh"))
            for sgn in (1, -1):
                f = lambda p: (p[0], sgn * p[1])  # noqa: E731
                v.poly([f(rS), f(tS), f(tL), f(rL), f(K), f((K[0], rh)), f((b, rh))])
                v.line(f(rS), f(rL), "细实线")
                # 分度线：分度圆锥母线在齿宽范围内的一段（两端各伸出 2 mm）
                c, sn = math.cos(bevel["delta"]), math.sin(bevel["delta"])
                xa = bevel["x_apex"]
                r0, r1 = bevel["R"] - (tL[0] - tS[0]) / c - 2 / s, bevel["R"] + 2 / s
                v.line((xa + r0 * c, sgn * r0 * sn), (xa + r1 * c, sgn * r1 * sn), "点画线")
            v.line((rS[0], -rS[1]), (rS[0], rS[1]))  # 小端端面
            r_draw = rh
        elif seg.role == "齿轮轴":
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
        sec_x = c[0] + rs + 45
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
               "<>", s, 0, tol=tol.deviations("N9", kb / 1e3))
        sh.dim((c[0], c[1] - rs), (c[0], c[1] + top), (c[0] + rs + 6, c[1]), 90, "<>", s, 1,
               tol=tol.shaft_keyway_depth(kb / 1e3))
        # 槽底的表面结构：断面图小的时候符号会越出断面圆、压在圆上，用引出标注在附近另找空位
        sh.roughness_leader((c[0] + hb, c[1] + top), (c[0] + hb + 8, c[1] + top + 10), "Ra 3.2", 2.5)
        # 键槽对称度（对公共轴线 A-B）：被测要素是中心平面，指引线箭头与键宽尺寸线对齐
        yd = c[1] + rs + 3.5
        val = tol.fmt_mm(tol.keyway_symmetry(kb / 1e3))
        fw_ = 6 + len(val) * 3.0 * 0.6 + 4 + 3 * 3.0 * 0.6 + 4
        sh.arrow((c[0] - hb - 9, yd), (c[0] - hb - 3, yd), 2.0, "细实线")
        sh.gtol(c[0] - hb - 9 - fw_, yd - 3, "symmetry", val, "A-B", 3.0)

    # ------------------------------------------------ 尺寸
    seen = set()
    used_x: list[float] = []
    for a, b, seg in S:
        d = (seg.d if seg.role != "齿轮轴" else integral.tip_d) * 1e3
        key = (round(d, 2), seg.role)
        xm = (a + b) / 2
        if seg.keyway:
            xm = a + (b - a) * 0.2
        if seg.role == "退刀" or key in seen:
            continue
        seen.add(key)
        fit = FITS.get(seg.role, "") if seg.role != "齿轮轴" else "h11"
        txt = "%%c<>"
        dev = tol.deviations(fit, d / 1e3) if fit else None
        narrow = (b - a) * s < 14
        if seg.role == "齿轮轴" and bevel is not None:
            xt, rt = bevel["tipL"]
            v.dim((xt, -rt), (xt, rt), (xt, 0), 90, "%%c<>", 2, tol=tol.deviations("h11", 2 * rt / 1e3))
            continue
        if seg.keyway or narrow:
            # 文字放不下或与键槽重叠：把文字引到轴的下方
            xm = (a + b) / 2 if narrow else a + (b - a - seg.keyway[2] * 1e3) / 4
            lx, ly = v.P(xm, -d / 2)
            tx = lx - (24 if dev else 12) if seg.role == "轴承" else lx + 4  # 轴承段下方有基准符号，文字放左边
            while any(abs(tx - u) < 7 for u in used_x):  # 相邻两段的引出文字（竖排）不得重叠
                tx += 7
            used_x.append(tx)
            sh.dim(v.P(xm, -d / 2), v.P(xm, d / 2), v.P(xm, 0), 90, txt, s, 1 if d % 1 else 0,
                   location=(tx, ly - 9), tol=dev)
        else:
            # 尺寸线沿轴线附近试几个位置，避开齿部轮廓、台阶的粗实线
            v.dim_auto((xm, -d / 2), (xm, d / 2), [(xm + off / s, 0) for off in (0, 3, -3, 6, -6, 10, -10)],
                       90, txt, 1 if d % 1 else 0, tol=dev)
    # 轴向尺寸链（下方），最长的非配合段不注
    fit_roles = set(FITS) | {"齿轮轴"}
    free = max((t for t in S if t[2].role not in fit_roles), key=lambda t: t[1] - t[0], default=None)
    y_chain = -(d_max / 2) - 24 / s
    for a, b, seg in S:
        if free is not None and seg is free[2]:
            continue
        v.dim((a, -(seg.root_d or seg.d) * 1e3 / 2), (b, -(seg.root_d or seg.d) * 1e3 / 2), (a, y_chain), 0, "<>", 0)
    v.dim((0, -S[0][2].d * 1e3 / 2), (L, -S[-1][2].d * 1e3 / 2), (0, y_chain - 10 / s), 0, "<>", 0)
    # 键槽长度与定位（上方）：尺寸线试几个高度，避开上方的表面结构符号和台阶
    for xm, seg, kb, t1, kl, ka, kz in sections:
        r = seg.d * 1e3 / 2
        a = next(t[0] for t in S if t[2] is seg)
        v.dim_auto((ka, kb / 2), (kz, kb / 2), [(ka, r + k / s) for k in (12, 17, 23, 30, 38)], 0, "<>", 0)
        if ka - a > 0.5:
            v.dim_auto((a, r), (ka, kb / 2), [(a, r + k / s) for k in (12, 17, 23, 30, 38)], 0, "<>", 0)

    # ------------------------------------------------ 表面结构、基准、跳动
    datums = []
    for a, b, seg in S:
        r = (seg.d if seg.role != "齿轮轴" else integral.tip_d) * 1e3 / 2
        xm = (a + b) / 2
        if seg.role in RA:
            # 短轴段上符号会越出台肩压到轮廓线，用引出标注在附近另找空位
            p = v.P(a + (b - a) * 0.82, r)
            sh.roughness_leader(p, (p[0] + 6, p[1] + 9), RA[seg.role], 3.0)
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
                if seg.role == "齿轮轴" and bevel is not None:  # 齿顶圆锥中部
                    (x0_, y0_), (x1_, y1_) = bevel["tipS"], bevel["tipL"]
                    px, py = v.P((x0_ + x1_) / 2, (y0_ + y1_) / 2)
                fx, fy = px - 6, py + 24
                sh.gtol_leader((px, py), (fx, fy), "runout", RUNOUT[seg.role], "A-B")
        # 轴承轴颈圆柱度、轴承定位轴肩端面圆跳动（GB/T 275-2015，普通级轴承）
        for i, (a, b, seg) in enumerate(S):
            if seg.role != "轴承":
                continue
            r = seg.d * 1e3 / 2
            px, py = v.P(a + (b - a) * 0.5, r)
            sh.arrow((px, py + 30), (px, py), 2.5, "细实线")
            sh.gtol(px - 7, py + 30, "cylindricity", tol.fmt_mm(tol.journal_cylindricity(seg.d)), "", 3.0)
            for j, face_x in ((i - 1, a), (i + 1, b)):
                if 0 <= j < len(S) and S[j][2].role in ("轴肩", "轴环") and S[j][2].d > seg.d:
                    rr = S[j][2].d * 1e3 / 2
                    qx, qy = v.P(face_x, (r + rr) / 2)
                    out = -1 if j < i else 1  # 框格放在轴肩外侧（远离轴承一侧），避开轴颈上的圆柱度框格
                    fy = v.P(0, rr)[1] + 40
                    sh.arrow((qx + out * 6, fy), (qx, qy), 2.5, "细实线")
                    sh.gtol(qx + out * 6 - (0 if out > 0 else 33), fy, "runout",
                            tol.fmt_mm(tol.shoulder_runout(seg.d)), "A-B", 3.0)

    # ------------------------------------------------ 图框
    is_gear_shaft = integral is not None
    worm = is_gear_shaft and integral.pair == "worm"
    if worm:
        mat, name = "45", "蜗杆"
    else:
        mat = material_name(pairs[integral.pair].inp.material1) if is_gear_shaft else "45"
        name = lay.name.split("（")[0] + ("（齿轮轴）" if is_gear_shaft else "")
    heat = "调质处理 241～286HBW" if mat.startswith("40Cr") else "调质处理 217～255HBW"
    if worm:
        heat += "，螺纹齿面高频淬火 45～55HRC"
    reqs = [f"{heat}。",
            "未注倒角 C1.5，未注圆角 R1。",
            "未注尺寸公差按 GB/T 1804-m。",
            "未注几何公差按 GB/T 1184-K。"]
    if worm:
        from gongke_core.drawing.worm_wheel import param_table
        param_table(sh, design.worm, 1)
        reqs.insert(1, "螺纹两端倒角至齿根，齿面磨削。")
    elif is_gear_shaft and bevel is not None:
        from gongke_core.drawing.bevel_gear import param_table
        param_table(sh, design.bevel, 1)
    elif is_gear_shaft:
        from gongke_core.drawing.gear import param_table
        param_table(sh, pairs[integral.pair], integral.member, abs(lay.bearing_z[1] - lay.bearing_z[0]))
    sh.frame(TitleInfo(name, mat, s, "1", drawing_no), reqs, "Ra 6.3")
    sh.save(path)
    return sh

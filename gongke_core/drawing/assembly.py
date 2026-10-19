"""减速器装配图（俯视图，沿箱座剖分面剖切、去掉箱盖）。

按 GB/T 4459.2、4459.7 和装配图规定画法：
- 实心轴沿轴线剖切按不剖处理，画外形；齿轮、套筒剖开画剖面线，相邻零件剖面线方向相反；
- 啮合区小齿轮轮齿画成可见，大齿轮被遮住的齿顶线画虚线；
- 滚动轴承用通用画法（矩形线框加正十字）；
- 注出两级中心距、外形尺寸和主要配合，配零件序号、明细栏、技术特性表和技术要求。
"""

from __future__ import annotations

from pathlib import Path

from gongke_core.design import ReducerDesign
from gongke_core.drawing.gear import dms
from gongke_core.drawing import material_name
from gongke_core.drawing.sheet import Sheet, TitleInfo, View, pick_scale
from gongke_core.layout.gear_blank import blank

MM = 1e3  # m → mm


def draw(d: ReducerDesign, path: str | Path, drawing_no: str = "GK-00") -> Sheet:
    h = d.housing
    W = h.inner_width * MM
    delta = h.delta * MM
    fw = (h.c1 + h.c2) * MM
    L1 = h.bearing_seat_length * MM
    e = h.cap_thickness * MM
    xs = [s.layout.x * MM for s in d.shafts]  # 各轴在图上的 Y
    ylo, yhi = h.x_range[0] * MM, h.x_range[1] * MM

    # 模型范围
    z_min = min(s.layout.segments[0].z0 for s in d.shafts) * MM - 5
    z_max = max(s.layout.segments[-1].z1 for s in d.shafts) * MM + 5
    y_min, y_max = ylo - delta - fw, yhi + delta + fw
    mw, mh = z_max - z_min, y_max - y_min

    # 视图转 90°：轴线竖直，三根轴自左向右排列（与常见减速器装配图的俯视图一致）
    for size in ("A1", "A0"):
        sh = Sheet(size)
        x0, y0, x1, y1 = sh.inner
        avail_w = x1 - x0 - 190 - 70
        avail_h = y1 - y0 - 120
        s = pick_scale(mh, mw, avail_w, avail_h)
        if s >= 1 / 1.5 or size == "A0":
            break
    # 旋转后：图上 X = s·y，图上 Y = −s·z
    ox = x0 + 50 + (avail_w - mh * s) / 2 - y_min * s
    oy = y0 + 60 + (avail_h - mw * s) / 2 + z_max * s
    v = View(sh, (ox, oy), s, rotate=True)

    # ------------------------------------------------ 箱座（剖分面俯视）
    v.rect(-delta - fw, y_min, W + delta + fw, y_max)
    v.rect(0, ylo, W, yhi)
    v.rect(-delta, ylo - delta, W + delta, yhi + delta, "细实线")
    for sr, x in zip(d.shafts, xs):
        D = sr.layout.bearing.D * MM
        rb = D / 2 + max(0.25 * D, 12)
        for za, zb in ((-L1, -delta - fw), (W + delta + fw, W + L1)):
            v.rect(za, x - rb, zb, x + rb)
        for sgn in (1, -1):
            v.line((-L1, x + sgn * D / 2), (0, x + sgn * D / 2))
            v.line((W, x + sgn * D / 2), (W + L1, x + sgn * D / 2))
        # 轴承旁连接螺栓孔（细实线圆）
        d1 = h.bolt_bearing * MM
        for zc in (-delta - fw / 2, W + delta + fw / 2):
            for sgn in (1, -1):
                yy = x + sgn * (rb + d1)
                if y_min + d1 < yy < y_max - d1:
                    v.circle((zc, yy), d1 / 2 + 1, "细实线")

    parts: list[tuple[str, str, str, str, tuple[float, float]]] = []  # (名称, 数量, 材料, 备注, 引出点)
    parts.append(("箱座", "1", "HT200", "", (W / 2, ylo - delta / 2)))
    hatch_angle = [45]

    def next_angle():
        hatch_angle[0] = 135 if hatch_angle[0] == 45 else 45
        return hatch_angle[0]

    pairs = {"high": d.high, "low": d.low}
    key_count: dict[str, int] = {}
    sleeves = 0
    caps_open, caps_blind = 0, 0
    at_of: dict[str, tuple[float, float]] = {}  # 套筒、端盖、键的引出点（各取第一个）
    for sr, x in zip(d.shafts, xs):
        lay = sr.layout
        brg = lay.bearing
        B, Dd, dd = brg.B * MM, brg.D * MM, brg.d * MM
        # ---------------- 轴（外形）
        prev = None
        for seg in lay.segments:
            a, b = seg.z0 * MM, seg.z1 * MM
            if seg.role == "齿轮轴":
                g = next(g for g in lay.gears if g.integral)
                pair = pairs[g.pair]
                ra, rf, rp = g.tip_d * MM / 2, g.root_d * MM / 2, pair.d1 * MM / 2
                for sgn in (1, -1):
                    v.line((a, x + sgn * ra), (b, x + sgn * ra))
                    v.line((a, x + sgn * rf), (b, x + sgn * rf), "细实线")
                    v.line((a - 2, x + sgn * rp), (b + 2, x + sgn * rp), "点画线")
                r = ra
            else:
                r = seg.d * MM / 2
                for sgn in (1, -1):
                    v.line((a, x + sgn * r), (b, x + sgn * r))
            if prev is not None:
                rr = max(prev, r)
                v.line((a, x - rr), (a, x + rr))
            prev = r
        v.line((lay.segments[-1].z1 * MM, x - prev), (lay.segments[-1].z1 * MM, x + prev))
        v.line((lay.segments[0].z0 * MM, x - lay.segments[0].d * MM / 2), (lay.segments[0].z0 * MM, x + lay.segments[0].d * MM / 2))
        v.centerline((lay.segments[0].z0 * MM, x), (lay.segments[-1].z1 * MM, x), 5)
        shaft_name = lay.name.split("（")[0] + ("（齿轮轴）" if any(g.integral for g in lay.gears) else "")
        ig = next((g for g in lay.gears if g.integral), None)
        mat = material_name(pairs[ig.pair].inp.material1) if ig else "45"
        first = lay.segments[0]
        parts.append((shaft_name, "1", mat, "", (first.z0 * MM + 5, x)))

        # ---------------- 轴承（通用画法）
        for zc in lay.bearing_z:
            zc *= MM
            for sgn in (1, -1):
                y_in, y_out = x + sgn * dd / 2, x + sgn * Dd / 2
                v.rect(zc - B / 2, min(y_in, y_out), zc + B / 2, max(y_in, y_out))
                ym = (y_in + y_out) / 2
                v.line((zc - B * 0.3, ym), (zc + B * 0.3, ym), "细实线")
                v.line((zc, ym - abs(y_out - y_in) * 0.3), (zc, ym + abs(y_out - y_in) * 0.3), "细实线")
        parts.append((f"深沟球轴承 {brg.designation}", "2", "", "GB/T 276-2013",
                      (lay.bearing_z[1] * MM, x + (dd + Dd) / 4)))

        # ---------------- 轴承盖（凸缘式）
        r_cap = Dd / 2 + 2.5 * 8
        for side, zb_face in (("left", -L1), ("right", W + L1)):
            is_open = lay.extension == side
            sgn_z = -1 if side == "left" else 1
            za, zb = sorted((zb_face, zb_face + sgn_z * e))
            seal_r = (lay.diameters["密封"] or dd) * MM / 2 + 1 if is_open else 0
            for sgn in (1, -1):
                v.rect(za, x + sgn * seal_r, zb, x + sgn * r_cap)
            v.hatch([[(za, x + seal_r), (zb, x + seal_r), (zb, x + r_cap), (za, x + r_cap)],
                     [(za, x - r_cap), (zb, x - r_cap), (zb, x - seal_r), (za, x - seal_r)]], next_angle(), 2.0)
            # 止口伸入轴承座孔，顶住轴承外圈
            bz = lay.bearing_z[0 if side == "left" else 1] * MM
            face = bz - B / 2 if side == "left" else bz + B / 2
            sa, sb = sorted((zb_face, face))
            for sgn in (1, -1):
                v.rect(sa, x + sgn * max(Dd / 2 - 8, seal_r), sb, x + sgn * Dd / 2, "细实线")
            at_of.setdefault("透盖" if is_open else "闷盖", ((za + zb) / 2, x + (seal_r + r_cap) / 2))
            if is_open:
                caps_open += 1
            else:
                caps_blind += 1

        # ---------------- 齿轮（剖开）与套筒
        for gg in lay.gears:
            pair = pairs[gg.pair]
            if gg.integral:
                continue
            gb = blank(pair, gg.member, gg.seat_d)
            zc = gg.z * MM
            bw = gb.b * MM
            rb_, rf, ra, rp = gb.bore * MM / 2, gb.df * MM / 2, gb.da * MM / 2, gb.d * MM / 2
            ang = next_angle()
            for sgn in (1, -1):
                if gb.web:
                    rh, r2, c = gb.hub_d * MM / 2, gb.rim_inner_d * MM / 2, gb.web_thickness * MM / 2
                    loop = [(-bw / 2, rb_), (bw / 2, rb_), (bw / 2, rh), (c, rh), (c, r2), (bw / 2, r2), (bw / 2, rf),
                            (-bw / 2, rf), (-bw / 2, r2), (-c, r2), (-c, rh), (-bw / 2, rh)]
                else:
                    loop = [(-bw / 2, rb_), (bw / 2, rb_), (bw / 2, rf), (-bw / 2, rf)]
                pts = [(zc + px, x + sgn * py) for px, py in loop]
                v.poly(pts, close=True)
                v.hatch([pts], ang, 2.5)
                # 轮齿：大齿轮朝向啮合小齿轮一侧的齿顶线被遮住，画虚线
                mate_dir = 0
                if gg.member == 2:
                    mate_x = xs[d.shafts.index(sr) - 1]
                    mate_dir = 1 if mate_x > x else -1
                hidden = gg.member == 2 and sgn == mate_dir
                v.line((zc - bw / 2, x + sgn * rf), (zc - bw / 2, x + sgn * ra))
                v.line((zc + bw / 2, x + sgn * rf), (zc + bw / 2, x + sgn * ra))
                v.line((zc - bw / 2, x + sgn * ra), (zc + bw / 2, x + sgn * ra), "虚线" if hidden else "粗实线")
                v.line((zc - bw / 2 - 2, x + sgn * rp), (zc + bw / 2 + 2, x + sgn * rp), "点画线")
            label = f"{pair.inp.name}{'小' if gg.member == 1 else '大'}齿轮"
            gm = material_name(pair.inp.material1 if gg.member == 1 else pair.inp.material2)
            z = pair.z1 if gg.member == 1 else pair.z2
            parts.append((label, "1", gm, f"mn={pair.mn * MM:g}，z={z}", (zc, x + (rf + rb_) / 2)))
            # 套筒：齿轮装入一侧与轴承之间
            sd_in = lay.diameters["轴承"] * MM / 2
            sd_out = sd_in + max(0.08 * sd_in * 2, 4)
            if gg.mount == "left":
                s0, s1 = lay.bearing_z[0] * MM + B / 2, zc - bw / 2
            else:
                s0, s1 = zc + bw / 2, lay.bearing_z[1] * MM - B / 2
            if s1 - s0 > 1:
                ang2 = next_angle()
                for sgn in (1, -1):
                    pts = [(s0, x + sgn * sd_in), (s1, x + sgn * sd_in), (s1, x + sgn * sd_out), (s0, x + sgn * sd_out)]
                    v.poly(pts, close=True)
                    v.hatch([pts], ang2, 1.5)
                at_of.setdefault("套筒", ((s0 + s1) / 2, x + (sd_in + sd_out) / 2))
                sleeves += 1
        for k in sr.keys:
            name = f"键 {k.size.b * MM:g}×{k.length * MM:g}"
            key_count[name] = key_count.get(name, 0) + k.count
        for seg in lay.segments:
            if seg.keyway:
                kb, _, kl = (v_ * MM for v_ in seg.keyway)
                at_of.setdefault(f"键 {kb:g}×{kl:g}", ((seg.z0 + seg.z1) / 2 * MM + kl / 4, x))

        # ---------------- 联轴器（双点画线示意外形省略，画半联轴器轮廓）
        if lay.extension:
            end = next(sg for sg in lay.segments if sg.role == "端部")
            a, b = end.z0 * MM, end.z1 * MM
            rh = end.d * MM
            for sgn in (1, -1):
                v.line((a, x + sgn * rh), (b, x + sgn * rh), "细实线")
            v.line((a, x - rh), (a, x + rh), "细实线")
            v.line((b, x - rh), (b, x + rh), "细实线")

    parts.append(("套筒", str(sleeves), "Q235", "", at_of.get("套筒")))
    parts.append(("轴承透盖", str(caps_open), "HT200", "", at_of.get("透盖")))
    parts.append(("轴承闷盖", str(caps_blind), "HT200", "", at_of.get("闷盖")))
    for name, n in key_count.items():
        parts.append((name, str(n), "45", "GB/T 1096-2003", at_of.get(name)))

    # ------------------------------------------------ 零件序号与明细栏
    # 序号引到装配体左右两侧，按高度排序后等距排列，避免引线交叉；
    # 编号按 GB/T 4458.2 沿逆时针方向顺次排列（左侧自上而下，右侧自下而上），明细栏同序
    left_x = v.P(0, y_min)[0] - 45
    right_x = v.P(0, y_max)[0] + 40
    mid = (left_x + right_x) / 2
    groups = {"L": [], "R": []}
    for part in parts:
        if part[4] is not None:
            tx, ty = v.P(*part[4])
            groups["L" if tx < mid else "R"].append((ty, tx, part))
    placed = []
    for side, items in groups.items():
        items.sort(key=lambda t: -t[0])
        y_prev = None
        for ty, tx, part in items:
            y = ty if y_prev is None else min(ty, y_prev - 10)
            y_prev = y
            placed.append((side, y, tx, ty, part))
    order = sorted(placed, key=lambda t: (t[0] == "R", -t[1] if t[0] == "L" else t[1]))
    numbered = [t[4] for t in order] + [p for p in parts if p[4] is None]
    for i, (name, qty, mat, note, _) in enumerate(numbered, 1):
        sh.add_part(i, name, qty, mat, note)
    for i, (side, y, tx, ty, _) in enumerate(order, 1):
        sh.balloon((tx, ty), (left_x if side == "L" else right_x, y), i)

    # ------------------------------------------------ 尺寸
    zr = z_min - 5
    v.dim((zr, xs[0]), (zr, xs[1]), (zr - 10 / s, xs[0]), 90, "<>", 0)
    v.dim((zr, xs[1]), (zr, xs[2]), (zr - 10 / s, xs[1]), 90, "<>", 0)
    v.dim((-delta - fw, y_min), (W + delta + fw, y_min), (-delta - fw, y_min - 14 / s), 0, "<>", 0)
    v.dim((-delta - fw, y_min), (-delta - fw, y_max), (-delta - fw - 30 / s, y_min), 90, "<>", 0)
    v.dim((0, y_max), (W, y_max), (0, y_max + 14 / s), 0, "<>", 0)
    # 配合尺寸（引出标注）
    fits = []
    for sr, x in zip(d.shafts, xs):
        lay = sr.layout
        zb = lay.bearing_z[0] * MM
        D, dd = lay.bearing.D * MM, lay.bearing.d * MM
        fits.append(((zb, x - D / 2), f"%%c{D:g}H7"))
        fits.append(((zb - lay.bearing.B * MM / 2 - 1, x - dd / 2), f"%%c{dd:g}k6"))
        for gg in lay.gears:
            if not gg.integral:
                fits.append(((gg.z * MM, x - gg.seat_d * MM / 2), f"%%c{gg.seat_d * MM:g}H7/r6"))
        if lay.extension:
            end = next(sg for sg in lay.segments if sg.role == "端部")
            fits.append((((end.z0 + end.z1) / 2 * MM, x - end.d * MM / 2), f"%%c{end.d * MM:g}k6"))
    for (pt, txt) in fits:
        tx, ty = v.P(*pt)
        sh.leader_text((tx, ty), (tx + 6, ty - 9), txt.replace("%%c", "Ø"), 3.0)

    # ------------------------------------------------ 技术特性、技术要求
    k = d.kin
    rows = [["技术特性", ""],
            ["输入功率", f"{k.shafts[1].power / 1e3:.2f} kW"],
            ["输入转速", f"{k.shafts[1].speed_rpm:.0f} r/min"],
            ["总传动比", f"{d.actual_ratio:.2f}"],
            ["总效率", f"{k.eta_total:.3f}"]]
    for p in (d.high, d.low):
        rows.append([p.inp.name, f"mn={p.mn * MM:g}  z={p.z1}/{p.z2}  β={dms(p.beta)}  {p.inp.grade}级"])
    sh.table(x0 + 10, y1 - 10, rows, [30, 95], 8)
    sh.tech_requirements([
        "装配前所有零件用煤油清洗，箱体内壁涂耐油油漆。",
        "啮合侧隙用铅丝检验，高速级不小于 0.14 mm，低速级不小于 0.16 mm。",
        "用涂色法检验接触斑点，沿齿高不小于 40%，沿齿长不小于 50%。",
        "深沟球轴承两端固定，轴向游隙调整为 0.25～0.4 mm。",
        "剖分面、各接触面及密封处不允许漏油，剖分面允许涂密封胶，不允许使用垫片。",
        "箱内装 L-CKC 220 工业闭式齿轮油至规定油面高度。",
        "外表面涂灰色油漆。",
    ], x0 + 10, y0 + 12 + 7 * 7)
    sh.frame(TitleInfo("二级圆柱齿轮减速器", "", s, "1", drawing_no))
    sh.save(path)
    return sh

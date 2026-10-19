"""减速器装配图：主视图（外形）、俯视图（沿剖分面剖切、去掉箱盖）、左视图（外形）。

按 GB/T 4459.2、4459.7 和装配图规定画法：
- 实心轴沿轴线剖切按不剖处理，画外形；齿轮、套筒剖开画剖面线，相邻零件剖面线方向相反；
- 啮合区小齿轮轮齿画成可见，大齿轮被遮住的齿顶线画虚线；
- 滚动轴承用通用画法（矩形线框加正十字）；
- 主视图、左视图画外形，被轴承盖、轴承座等挡住的线不画（见 `hidden`）；
- 零件序号沿图形四周按逆时针顺次排列，配明细栏、技术特性表和技术要求。

视图按第一角投影配置：俯视图在主视图下方（下方为前），左视图在主视图右方（右方为前）。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from gongke_core.design import ReducerDesign
from gongke_core.drawing import hidden, material_name
from gongke_core.drawing.gear import dms
from gongke_core.drawing.sheet import SCALES, Sheet, TitleInfo, View
from gongke_core.layout.gear_blank import blank
from gongke_core.layout.housing_detail import Arc, HousingDetail, detail, envelope_height

MM = 1e3  # m → mm

PIN_D = [6, 8, 10, 12, 16]
PIN_L = [20, 24, 26, 28, 30, 32, 35, 40, 45, 50, 55, 60]
SCREW_L = [10, 12, 16, 20, 25, 30, 35, 40, 45, 50]


def _std(v: float, table: list[int]) -> int:
    return next((x for x in table if x >= v - 1e-9), table[-1])


@dataclass
class Part:
    name: str
    qty: str
    material: str
    note: str
    target: tuple[float, float] | None = None  # 图纸坐标
    group: str = ""  # 序号所在的一排：FL/FT/FR（主视图左、上、右），TL/TR（俯视图左、右）


def draw(d: ReducerDesign, path: str | Path, drawing_no: str = "GK-00") -> Sheet:
    t = detail(d)
    h = d.housing
    W = h.inner_width * MM
    delta = h.delta * MM
    fw = t.flange_w * MM
    b, b1 = h.flange_base * MM, h.flange_cover * MM
    xs = [s.layout.x * MM for s in d.shafts]
    xo0, xo1 = (v * MM for v in t.x_outer)

    # ------------------------------------------------ 各视图的模型范围（mm）
    z_min = min(s.layout.segments[0].z0 for s in d.shafts) * MM - 5
    z_max = max(s.layout.segments[-1].z1 for s in d.shafts) * MM + 5
    eye_top = max(envelope_height(t.cover_outer, x) for x in t.eyebolts) * MM + 4.6 * t.eyebolt_d * MM
    fy0, fy1 = t.y_bottom * MM, max(eye_top, t.cover_top * MM + 30)
    cx0, cx1 = xo0 - fw - 2, xo1 + fw + 40  # 右端有油标、放油螺塞
    front_w, front_h = cx1 - cx0, fy1 - fy0
    top_h = z_max - z_min
    left_w = z_max - z_min
    n_rows = 42  # 明细栏行数的估计上限
    n_cont = 18  # 标题栏左方续表的最多行数

    for size in ("A1", "A0"):
        sh = Sheet(size)
        x0, y0, x1, y1 = sh.inner
        s = None
        for sc in reversed(SCALES):
            if sc > 1:
                continue
            w_need = 40 + front_w * sc + 40 + left_w * sc + 30
            h_need = 25 + front_h * sc + 32 + top_h * sc + 30
            right_free = (x1 - x0) - 180 - (40 + front_w * sc + 45)  # 俯视图右侧放技术特性表、技术要求
            front_bottom = y1 - 25 - front_h * sc
            left_right = x0 + 40 + front_w * sc + 40 + left_w * sc + 30
            first_rows = int((front_bottom - 22 - (y0 + 56)) / 7) - 1 if left_right > x1 - 180 else 99
            if (w_need <= x1 - x0 and h_need <= y1 - y0 and right_free >= 135
                    and first_rows + n_cont >= n_rows and front_bottom - 30 - 130 >= y0 + 7 * (n_cont + 1)):
                s = sc
                break
        if s is not None or size == "A0":
            s = s or 1 / 5
            break
    sh.parts_first_rows = max(first_rows, 10) if s is not None else None

    ox = x0 + 40 - cx0 * s  # 模型 x = 0 在图纸上的 X（主视图、俯视图共用）
    oy_f = y1 - 25 - fy1 * s  # 模型 y = 0（剖分面）在主视图中的 Y
    front_bottom = oy_f + fy0 * s
    oy_t = front_bottom - 32 + z_min * s  # 俯视图：图上 Y = oy_t − z·s
    front_right = ox + cx1 * s
    ox_l = front_right + 40 - z_min * s  # 左视图：图上 X = ox_l + z·s
    fv = View(sh, (ox, oy_f), s)
    tv = View(sh, (ox, oy_t), s, rotate=True)  # 模型 (z, x) → 图上 (x, −z)
    lv = View(sh, (ox_l, oy_f), s)

    parts: list[Part] = []
    by_name: dict[str, Part] = {}

    def add(name, qty, mat, note="", target=None, group=""):
        if name in by_name:
            p = by_name[name]
            if p.target is None and target is not None:
                p.target, p.group = target, group
            return p
        p = Part(name, str(qty), mat, note, target, group)
        parts.append(p)
        by_name[name] = p
        return p

    _top_view(d, t, tv, sh, add)
    _front_view(d, t, fv, sh, add)
    _left_view(d, t, lv, sh)
    _standard_parts(d, t, add)

    # ------------------------------------------------ 零件序号与明细栏
    col_fl = min(ox + cx0 * s, ox + (h.x_range[0] * MM - delta - fw) * s) - 22
    col_tr = ox + (xo1 + fw) * s + 30
    col_fr = front_right + 14
    row_ft = oy_f + fy1 * s + 12
    _place_balloons(sh, parts, {
        "FL": ("col", col_fl, (front_bottom - 5, y1 - 8)),
        "TL": ("col", col_fl, (y0 + 10, front_bottom - 12)),
        "TR": ("col", col_tr, (y0 + 10, front_bottom - 12)),
        "FR": ("col", col_fr, (front_bottom + 2, y1 - 8)),
        "FT": ("row", row_ft, (ox + cx0 * s, front_right)),
    })

    # ------------------------------------------------ 尺寸
    zr = z_min - 5
    tv.dim((zr, xs[0]), (zr, xs[1]), (zr - 10 / s, xs[0]), 90, "<>", 0)
    tv.dim((zr, xs[1]), (zr, xs[2]), (zr - 10 / s, xs[1]), 90, "<>", 0)
    tv.dim((-delta - fw, xo0 - fw), (W + delta + fw, xo0 - fw), (-delta - fw, xo0 - fw - 14 / s), 0, "<>", 0)
    tv.dim((z_max - 5, xo0 - fw), (z_max - 5, xo1 + fw), (z_max + 2 / s, xo0 - fw), 90, "<>", 0)
    tv.dim((0, xo1 + fw), (W, xo1 + fw), (0, xo1 + fw + 14 / s), 0, "<>", 0)
    # 中心高、总高（左视图右侧）
    zl = z_max
    lv.dim((zl, fy0), (zl, 0), (zl + 10 / s, fy0), 90, "<>", 0)
    top_y = t.cover_top * MM
    lv.dim((zl, fy0), (zl, top_y), (zl + 20 / s, fy0), 90, "<>", 0)
    _fits(d, tv, sh)

    # ------------------------------------------------ 技术特性、技术要求
    k = d.kin
    rows = [["技术特性", ""],
            ["输入功率", f"{k.shafts[1].power / 1e3:.2f} kW"],
            ["输入转速", f"{k.shafts[1].speed_rpm:.0f} r/min"],
            ["总传动比", f"{d.actual_ratio:.2f}"],
            ["总效率", f"{k.eta_total:.3f}"]]
    for p in (d.high, d.low):
        rows.append([p.inp.name, f"mn={p.mn * MM:g}  z={p.z1}/{p.z2}  β={dms(p.beta)}  {p.inp.grade}级"])
    tx = col_tr + 22
    sh.table(tx, front_bottom - 30, rows, [30, 95], 8)
    reqs = [
        "装配前所有零件用煤油清洗，箱体内壁涂耐油油漆。",
        "啮合侧隙用铅丝检验，高速级不小于 0.14 mm，低速级不小于 0.16 mm。",
        "用涂色法检验接触斑点，沿齿高不小于 40%，沿齿长不小于 50%。",
        "深沟球轴承两端固定，用调整垫片调整轴向游隙为 0.25～0.4 mm。",
        "剖分面、各接触面及密封处不允许漏油，剖分面允许涂密封胶，不允许使用垫片。",
        f"箱内装 L-CKC 220 工业闭式齿轮油至油标规定高度（大齿轮浸油约 {(t.oil_level + d.low.da2 / 2) * MM:.0f} mm）。",
        "外表面涂灰色油漆。",
    ]
    sh.tech_requirements(reqs, tx, front_bottom - 30 - 8 * len(rows) - 22 - 0)
    for i, p in enumerate(parts, 1):
        sh.add_part(i, p.name, p.qty, p.material, p.note)
    sh.frame(TitleInfo("二级圆柱齿轮减速器", "", s, "1", drawing_no))
    sh.save(path)
    return sh


# ====================================================================== 俯视图

def _top_view(d: ReducerDesign, t: HousingDetail, v: View, sh: Sheet, add):
    h = d.housing
    W = h.inner_width * MM
    delta = h.delta * MM
    fw = t.flange_w * MM
    L1 = h.bearing_seat_length * MM
    e = h.cap_thickness * MM
    xs = [s.layout.x * MM for s in d.shafts]
    ylo, yhi = h.x_range[0] * MM, h.x_range[1] * MM
    y_min, y_max = ylo - delta - fw, yhi + delta + fw
    group_of = lambda x: "TL" if x < (xs[0] + xs[2]) / 2 else "TR"

    def tadd(name, qty, mat, note, at):
        add(name, qty, mat, note, v.P(*at), group_of(at[1]))

    # 箱座（剖分面俯视）
    v.rect(-delta - fw, y_min, W + delta + fw, y_max)
    v.rect(0, ylo, W, yhi)
    v.rect(-delta, ylo - delta, W + delta, yhi + delta, "细实线")
    for x, rb, cap in zip(xs, t.boss_r, t.caps):
        rb, D = rb * MM, cap.D * MM
        for za, zb in ((-L1, -delta - fw), (W + delta + fw, W + L1)):
            v.rect(za, x - rb, zb, x + rb)
        for sgn in (1, -1):
            v.line((-L1, x + sgn * D / 2), (0, x + sgn * D / 2))
            v.line((W, x + sgn * D / 2), (W + L1, x + sgn * D / 2))
    # 凸缘上的螺栓孔、定位销
    zf = (-delta - fw / 2, W + delta + fw / 2)
    for xb, dd in [(x, h.bolt_bearing) for x in t.bearing_bolts] + [(x, h.bolt_flange) for x in t.flange_bolts]:
        for zc in zf:
            v.circle((zc, xb * MM), dd * MM / 2 + 1, "细实线")
            sh.cross(v.P(zc, xb * MM), (dd * MM / 2 + 1) * v.s, 1.5)
    pin_d = _std(t.pin_d * MM, PIN_D)
    for px, pz in t.pins:
        v.circle((pz * MM, px * MM), pin_d / 2)
        sh.cross(v.P(pz * MM, px * MM), pin_d / 2 * v.s, 1.5)
    pin_l = _std(b_total(h) + 8, PIN_L)
    px, pz = t.pins[0]
    tadd(f"圆锥销 A{pin_d}×{pin_l}", len(t.pins), "35", "GB/T 117-2000", (pz * MM, px * MM))
    tadd("箱座", "1", "HT200", "", (W / 2, ylo - delta / 2))

    hatch_angle = [45]

    def next_angle():
        hatch_angle[0] = 135 if hatch_angle[0] == 45 else 45
        return hatch_angle[0]

    pairs = {"high": d.high, "low": d.low}
    key_count: dict[str, int] = {}
    key_at: dict[str, tuple[float, float]] = {}
    sleeves = 0
    sleeve_at = None
    for sr, x, cap in zip(d.shafts, xs, t.caps):
        lay = sr.layout
        brg = lay.bearing
        B, Dd, dd = brg.B * MM, brg.D * MM, brg.d * MM
        # 轴（外形）
        prev = None
        for seg in lay.segments:
            a, bb = seg.z0 * MM, seg.z1 * MM
            if seg.role == "齿轮轴":
                g = next(g for g in lay.gears if g.integral)
                pair = pairs[g.pair]
                ra, rf, rp = g.tip_d * MM / 2, g.root_d * MM / 2, pair.d1 * MM / 2
                for sgn in (1, -1):
                    v.line((a, x + sgn * ra), (bb, x + sgn * ra))
                    v.line((a, x + sgn * rf), (bb, x + sgn * rf), "细实线")
                    v.line((a - 2, x + sgn * rp), (bb + 2, x + sgn * rp), "点画线")
                r = ra
            else:
                r = seg.d * MM / 2
                for sgn in (1, -1):
                    v.line((a, x + sgn * r), (bb, x + sgn * r))
            if prev is not None:
                rr = max(prev, r)
                v.line((a, x - rr), (a, x + rr))
            prev = r
        v.line((lay.segments[-1].z1 * MM, x - prev), (lay.segments[-1].z1 * MM, x + prev))
        v.line((lay.segments[0].z0 * MM, x - lay.segments[0].d * MM / 2), (lay.segments[0].z0 * MM, x + lay.segments[0].d * MM / 2))
        v.centerline((lay.segments[0].z0 * MM, x), (lay.segments[-1].z1 * MM, x), 5)
        ig = next((g for g in lay.gears if g.integral), None)
        shaft_name = lay.name.split("（")[0] + ("（齿轮轴）" if ig else "")
        mat = material_name(pairs[ig.pair].inp.material1) if ig else "45"
        first = lay.segments[0]
        tadd(shaft_name, "1", mat, "", (first.z0 * MM + 5, x))

        # 轴承（通用画法）
        for zc in lay.bearing_z:
            zc *= MM
            for sgn in (1, -1):
                y_in, y_out = x + sgn * dd / 2, x + sgn * Dd / 2
                v.rect(zc - B / 2, min(y_in, y_out), zc + B / 2, max(y_in, y_out))
                ym = (y_in + y_out) / 2
                v.line((zc - B * 0.3, ym), (zc + B * 0.3, ym), "细实线")
                v.line((zc, ym - abs(y_out - y_in) * 0.3), (zc, ym + abs(y_out - y_in) * 0.3), "细实线")
        tadd(f"深沟球轴承 {brg.designation}", "2", "", "GB/T 276-2013", (lay.bearing_z[1] * MM, x + (dd + Dd) / 4))

        # 轴承盖（凸缘式）、调整垫片、毡圈
        r_cap = cap.D2 * MM / 2
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
            if is_open:
                # 毡圈：嵌在透盖的梯形槽内（简化为矩形，交叉细线表示）
                sd = lay.diameters["密封"] * MM
                fz0, fz1 = za + e * 0.25, zb - e * 0.25
                for sgn in (1, -1):
                    v.rect(fz0, x + sgn * sd / 2, fz1, x + sgn * (sd / 2 + 5), "细实线")
                    v.line((fz0, x + sgn * sd / 2), (fz1, x + sgn * (sd / 2 + 5)), "细实线")
                tadd(f"毡圈 {sd:g}", "1", "半粗羊毛毡", "JB/ZQ 4606-1997", ((fz0 + fz1) / 2, x - sd / 2 - 2.5))
            tadd("轴承透盖" if is_open else "轴承闷盖", "", "HT200", "", ((za + zb) / 2, x + (seal_r + r_cap) / 2 + 2))
            if side == "right" and sr is d.shafts[1]:
                tadd("调整垫片", "6组", "08F", "", (zb_face, x - r_cap + 3))

        # 齿轮（剖开）与套筒
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
                hid = gg.member == 2 and sgn == mate_dir
                v.line((zc - bw / 2, x + sgn * rf), (zc - bw / 2, x + sgn * ra))
                v.line((zc + bw / 2, x + sgn * rf), (zc + bw / 2, x + sgn * ra))
                v.line((zc - bw / 2, x + sgn * ra), (zc + bw / 2, x + sgn * ra), "虚线" if hid else "粗实线")
                v.line((zc - bw / 2 - 2, x + sgn * rp), (zc + bw / 2 + 2, x + sgn * rp), "点画线")
            label = f"{pair.inp.name}{'小' if gg.member == 1 else '大'}齿轮"
            gm = material_name(pair.inp.material1 if gg.member == 1 else pair.inp.material2)
            z = pair.z1 if gg.member == 1 else pair.z2
            tadd(label, "1", gm, f"mn={pair.mn * MM:g}，z={z}", (zc, x + (rf + rb_) / 2))
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
                sleeves += 1
                sleeve_at = sleeve_at or ((s0 + s1) / 2, x + (sd_in + sd_out) / 2)
        for k in sr.keys:
            name = f"键 {k.size.b * MM:g}×{k.length * MM:g}"
            key_count[name] = key_count.get(name, 0) + k.count
        for seg in lay.segments:
            if seg.keyway:
                kb, _, kl = (v_ * MM for v_ in seg.keyway)
                key_at.setdefault(f"键 {kb:g}×{kl:g}", ((seg.z0 + seg.z1) / 2 * MM + kl / 4, x))

        # 联轴器（相邻零件，细实线画外形）
        if lay.extension:
            end = next(sg for sg in lay.segments if sg.role == "端部")
            a, bb = end.z0 * MM, end.z1 * MM
            rh = end.d * MM
            for sgn in (1, -1):
                v.line((a, x + sgn * rh), (bb, x + sgn * rh), "细实线")
            v.line((a, x - rh), (a, x + rh), "细实线")
            v.line((bb, x - rh), (bb, x + rh), "细实线")

    if sleeve_at:
        tadd("套筒", str(sleeves), "Q235", "", sleeve_at)
    for name, n in key_count.items():
        tadd(name, str(n), "45", "GB/T 1096-2003", key_at.get(name, (0, 0)))
    n_open = sum(1 for s in d.shafts if s.layout.extension)
    by_count = {"轴承透盖": n_open, "轴承闷盖": 2 * len(d.shafts) - n_open}
    return by_count


def b_total(h) -> float:
    return (h.flange_base + h.flange_cover) * MM


# ====================================================================== 主视图

def _front_view(d: ReducerDesign, t: HousingDetail, v: View, sh: Sheet, add):
    h = d.housing
    W = h.inner_width * MM
    fw = t.flange_w * MM
    b, b1 = h.flange_base * MM, h.flange_cover * MM
    xs = [s.layout.x * MM for s in d.shafts]
    xo0, xo1 = (val * MM for val in t.x_outer)
    yb = t.y_bottom * MM
    b2 = h.flange_foot * MM
    mid_x = (xo0 + xo1) / 2

    def fadd(name, qty, mat, note, at):
        if at[1] > b1 + 2:
            g = "FT"
        else:
            g = "FL" if at[0] < mid_x else "FR"
        add(name, qty, mat, note, v.P(*at), g)

    caps = [(x, 0.0, c.D2 * MM / 2) for x, c in zip(xs, t.caps)]
    bosses = [(x, 0.0, r * MM) for x, r in zip(xs, t.boss_r)]
    occ = caps + bosses

    def seg(p, q, layer="粗实线", circles=None):
        for a, bb in hidden.visible_segments(p, q, occ if circles is None else circles):
            v.line(a, bb, layer)

    def arc(cx, cy, r, a0, a1, layer="粗实线", circles=None):
        for a, bb in hidden.visible_arcs(cx, cy, r, a0, a1, occ if circles is None else circles):
            v.arc((cx, cy), r, a, bb, layer)

    def rect(x0, y0, x1, y1, layer="粗实线"):
        for p, q in (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))):
            seg(p, q, layer)

    # ---------------- 轴承盖（最前面）
    for k, (sr, x, cap) in enumerate(zip(d.shafts, xs, t.caps)):
        r2 = cap.D2 * MM / 2
        v.circle((x, 0), r2)
        r0 = cap.D0 * MM / 2
        d3 = cap.d3 * MM
        for j in range(cap.n):
            a = math.radians(45 + 360 * j / cap.n if cap.n == 4 else 30 + 360 * j / cap.n)
            c = (x + r0 * math.cos(a), r0 * math.sin(a))
            v.circle(c, 0.85 * d3)
            v.circle(c, 0.5 * d3, "细实线")
        v.centerline((x - r2, 0), (x + r2, 0), 3)
        v.centerline((x, -r2), (x, r2), 3)
        lay = sr.layout
        if lay.extension == "right":  # 伸出端朝向观察者：画轴端和联轴器
            end = next(sg for sg in lay.segments if sg.role == "端部")
            v.circle((x, 0), end.d * MM / 2)
            v.circle((x, 0), end.d * MM, "细实线")
        tag = "轴承透盖" if lay.extension == "right" else "轴承闷盖"
        fadd(tag, "", "HT200", "", (x + r2 * 0.75, -r2 * 0.55))
        fadd(f"螺钉 M{d3:g}×{_std(h.cap_thickness * MM + 1.5 * d3, SCREW_L)}", "", "Q235", "GB/T 5783-2016",
             (x + r0 * math.cos(math.radians(-45 if cap.n == 4 else -30)) * 1.0,
              r0 * math.sin(math.radians(-45 if cap.n == 4 else -30))))
    # ---------------- 轴承座（被轴承盖挡住一部分）
    for x, rb in zip(xs, t.boss_r):
        arc(x, 0, rb * MM, 0, 360, circles=caps)

    # ---------------- 凸缘、箱壁、底座
    rect(xo0 - fw, -b, xo1 + fw, 0)
    rect(xo0 - fw, 0, xo1 + fw, b1)
    seg((xo0, yb + b2), (xo0, -b))
    seg((xo1, yb + b2), (xo1, -b))
    rect(xo0 - fw, yb, xo1 + fw, yb + b2)
    # 箱盖外形：凸缘以上部分
    for e in t.cover_outer:
        if isinstance(e, Arc):
            r = e.r * MM
            cut = math.degrees(math.asin(min(b1 / r, 1.0)))
            a0, a1 = max(e.a0, cut), min(e.a1, 180 - cut)
            if a1 > a0:
                arc(e.cx * MM, 0, r, a0, a1)
        else:
            seg((e.p[0] * MM, e.p[1] * MM), (e.q[0] * MM, e.q[1] * MM))
    xc = (xs[1] + t.caps[1].D2 * MM / 2 + xs[2] - t.caps[2].D2 * MM / 2) / 2
    fadd("箱盖", "1", "HT200", "", (xc, 0.55 * envelope_height(t.cover_outer, xc / MM) * MM))

    # ---------------- 吊钩（箱座两端铸出）
    for xe in t.hooks:
        xe *= MM
        sg = 1 if xe > mid_x else -1
        yt = -b - 1.6 * h.bolt_bearing * MM  # 让开凸缘下的螺母
        pts = [(xe, yt), (xe + sg * fw * 0.9, yt), (xe + sg * fw * 0.9, yt - 0.7 * fw), (xe, yt - 2.0 * fw)]
        for p, q in zip(pts, pts[1:]):
            seg(p, q)
        arc(xe + sg * fw * 0.45, yt - 0.4 * fw, 0.2 * fw, 0, 360)

    # ---------------- 连接螺栓（前侧凸缘一排）、起盖螺钉
    def bolt(x, dd, length, head_only=False):
        seg((x, b1 + 0.7 * dd + 3), (x, b1 - length - 3), "点画线")
        rect(x - dd, b1, x + dd, b1 + 0.7 * dd)
        seg((x - dd / 2, b1), (x - dd / 2, b1 + 0.7 * dd), "粗实线")
        seg((x + dd / 2, b1), (x + dd / 2, b1 + 0.7 * dd), "粗实线")
        if head_only:
            return
        yw = -b - 0.25 * dd
        rect(x - 0.75 * dd, yw, x + 0.75 * dd, -b)
        yn = yw - 0.8 * dd
        rect(x - dd, yn, x + dd, yw)
        seg((x - dd / 2, yn), (x - dd / 2, yw))
        seg((x + dd / 2, yn), (x + dd / 2, yw))
        y_end = b1 - length
        if y_end < yn:
            rect(x - dd / 2, y_end, x + dd / 2, yn)

    d1, d2 = h.bolt_bearing * MM, h.bolt_flange * MM
    L1b, L2b = t.bolt_length_d1 * MM, t.bolt_length_d2 * MM
    for xb in t.bearing_bolts:
        bolt(xb * MM, d1, L1b)
    for xb in t.flange_bolts:
        bolt(xb * MM, d2, L2b)
    xj = t.jack_screw[0] * MM
    lj = _std(b1 + d2, SCREW_L)
    bolt(xj, d2, lj, head_only=True)
    n1 = 2 * len(t.bearing_bolts)
    n2 = 2 * len(t.flange_bolts)
    xb1 = t.bearing_bolts[0] * MM
    fadd(f"螺栓 M{d1:g}×{L1b:g}", n1, "Q235", "GB/T 5782-2016", (xb1 - d1 * 0.6, b1 + 0.35 * d1))
    fadd(f"螺母 M{d1:g}", n1, "Q235", "GB/T 6170-2015", (xb1 - d1 * 0.6, -b - 0.65 * d1))
    fadd(f"弹簧垫圈 {d1:g}", n1, "65Mn", "GB/T 93-1987", (xb1 + d1 * 0.5, -b - 0.12 * d1))
    if t.flange_bolts:
        xb2 = t.flange_bolts[-1] * MM
        fadd(f"螺栓 M{d2:g}×{L2b:g}", n2, "Q235", "GB/T 5782-2016", (xb2 + d2 * 0.6, b1 + 0.35 * d2))
        fadd(f"螺母 M{d2:g}", n2, "Q235", "GB/T 6170-2015", (xb2 + d2 * 0.6, -b - 0.65 * d2))
        fadd(f"弹簧垫圈 {d2:g}", n2, "65Mn", "GB/T 93-1987", (xb2 - d2 * 0.5, -b - 0.12 * d2))
    fadd(f"起盖螺钉 M{d2:g}×{lj}", 1, "Q235", "GB/T 5783-2016", (xj, b1 + 0.35 * d2))

    # ---------------- 视孔盖、通气器
    ins = t.inspection
    cx, cy = ins.center[0] * MM, ins.center[1] * MM
    a = math.radians(ins.angle)
    ux, uy = math.cos(a), math.sin(a)
    nx, ny = -uy, ux
    L, th = ins.length * MM, ins.thickness * MM
    P = lambda s_, n_: (cx + ux * s_ + nx * n_, cy + uy * s_ + ny * n_)
    v.poly([P(-L / 2, 0), P(L / 2, 0), P(L / 2, th), P(-L / 2, th)], close=True)
    v.poly([P(-L / 2, -1.5), P(L / 2, -1.5)])  # 垫片
    sd = ins.screw_d * MM
    for s_ in (-L / 2 + 10, L / 2 - 10):
        v.poly([P(s_ - 0.85 * sd, th), P(s_ + 0.85 * sd, th), P(s_ + 0.85 * sd, th + 0.7 * sd), P(s_ - 0.85 * sd, th + 0.7 * sd)], close=True)
    vd = ins.vent_d * MM
    stack = [(0.6 * vd, th, th + 0.5 * vd), (0.9 * vd, th + 0.5 * vd, th + 0.9 * vd), (0.45 * vd, th + 0.9 * vd, th + 1.4 * vd)]
    for hw, n0, n1_ in stack:
        v.poly([P(-hw, n0), P(hw, n0), P(hw, n1_), P(-hw, n1_)], close=True)
    v.line(P(0, -3), P(0, th + 1.4 * vd + 3), "点画线")
    fadd("视孔盖", "1", "Q235", "", P(-L / 2 + 22, th / 2))
    fadd("视孔盖垫片", "1", "石棉橡胶纸", "", P(-L / 2 + 30, -0.8))
    fadd(f"螺钉 M{sd:g}×16", "4", "Q235", "GB/T 5783-2016", P(L / 2 - 10, th + 0.35 * sd))
    fadd(f"通气器 M{vd:g}×1.5", "1", "Q235", "", P(0.3 * vd, th + 1.15 * vd))

    # ---------------- 吊环螺钉
    ed = t.eyebolt_d * MM
    for k, xe in enumerate(t.eyebolts):
        ye = envelope_height(t.cover_outer, xe) * MM
        xe *= MM
        v.rect(xe - 1.1 * ed, ye - 2, xe + 1.1 * ed, ye + 0.4 * ed)  # 凸台
        v.rect(xe - 0.9 * ed, ye + 0.4 * ed, xe + 0.9 * ed, ye + 0.9 * ed)  # 台肩
        rc = ye + 0.9 * ed + 1.6 * ed
        v.circle((xe, rc), 1.6 * ed)
        v.circle((xe, rc), 0.8 * ed)
        v.line((xe, ye - 4), (xe, rc + 1.6 * ed + 3), "点画线")
        if k == 0:
            fadd(f"吊环螺钉 M{ed:g}", len(t.eyebolts), "20", "GB/T 825-1988", (xe - 1.2 * ed, rc))

    # ---------------- 油标（杆式，45° 斜插）、放油螺塞
    (ox_, oy_), ang = t.dipstick
    ox_, oy_ = ox_ * MM, oy_ * MM
    a = math.radians(ang)
    ux, uy = math.cos(a), math.sin(a)
    nx, ny = -uy, ux
    P = lambda s_, n_: (ox_ + ux * s_ + nx * n_, oy_ + uy * s_ + ny * n_)
    v.poly([P(0, -11), P(14, -11), P(14, 11), P(0, 11)])  # 油标座
    v.poly([P(14, -6), P(34, -6), P(34, 6), P(14, 6)])
    v.poly([P(34, -10), P(42, -10), P(42, 10), P(34, 10)], close=True)
    v.line(P(-6, 0), P(46, 0), "点画线")
    fadd("杆式油标 M12", "1", "Q235", "组合件", P(38, 4))
    dx, dy = t.drain[0] * MM, t.drain[1] * MM
    ddr = t.drain_d * MM
    v.rect(dx, dy - 0.9 * ddr, dx + 4, dy + 0.9 * ddr)  # 封油垫
    v.rect(dx + 4, dy - 0.8 * ddr, dx + 14, dy + 0.8 * ddr)  # 六角头
    v.line((dx + 4, dy - 0.4 * ddr), (dx + 14, dy - 0.4 * ddr))
    v.line((dx + 4, dy + 0.4 * ddr), (dx + 14, dy + 0.4 * ddr))
    v.line((dx - 4, dy), (dx + 18, dy), "点画线")
    fadd(f"放油螺塞 M{ddr:g}×1.5", "1", "Q235", "JB/ZQ 4450-2006", (dx + 9, dy + 0.6 * ddr))
    fadd(f"封油垫 {ddr:g}", "1", "石棉橡胶纸", "", (dx + 2, dy - 0.6 * ddr))
    # 油面（点画线示意，看不见的内部，用细点画线在油标处标出高度）
    v.line((xo1 - 12, t.oil_level * MM), (xo1 + 30, t.oil_level * MM), "点画线")


# ====================================================================== 左视图

def _left_view(d: ReducerDesign, t: HousingDetail, v: View, sh: Sheet):
    """从左向右看：图上 X = z，Y = y。各零件投影为矩形，按离观察者（−x 方向）由近到远绘制并消隐。"""
    h = d.housing
    W = h.inner_width * MM
    delta = h.delta * MM
    fw = t.flange_w * MM
    b, b1 = h.flange_base * MM, h.flange_cover * MM
    L1 = h.bearing_seat_length * MM
    e = h.cap_thickness * MM
    xs = [s.layout.x * MM for s in d.shafts]
    xo0, xo1 = (val * MM for val in t.x_outer)
    yb = t.y_bottom * MM
    b2 = h.flange_foot * MM
    top = t.cover_top * MM

    items: list[tuple[float, tuple[float, float, float, float], str]] = []  # (深度 x, 矩形 (z0,y0,z1,y1), 图层)
    items.append((xo0 - fw, (-delta - fw, yb, W + delta + fw, yb + b2), "粗实线"))
    items.append((xo0 - fw, (-delta - fw, -b, W + delta + fw, 0), "粗实线"))
    items.append((xo0 - fw, (-delta - fw, 0, W + delta + fw, b1), "粗实线"))
    items.append((xo0, (-delta, yb + b2, W + delta, -b), "粗实线"))
    cover_near = min(x - r * MM for x, r in zip(xs, t.cover_r))
    items.append((cover_near, (-delta, b1, W + delta, top), "粗实线"))
    for xe in t.hooks[:1]:
        yt = -b - 1.6 * h.bolt_bearing * MM
        items.append((xe * MM - fw, (W / 2 - delta, yt - 2.0 * fw, W / 2 + delta, yt), "粗实线"))
    for sr, x, rb, cap in zip(d.shafts, xs, t.boss_r, t.caps):
        rb = rb * MM
        r2 = cap.D2 * MM / 2
        items.append((x - rb, (-L1, -rb, -delta, rb), "粗实线"))
        items.append((x - rb, (W + delta, -rb, W + L1, rb), "粗实线"))
        items.append((x - r2, (-L1 - e, -r2, -L1, r2), "粗实线"))
        items.append((x - r2, (W + L1, -r2, W + L1 + e, r2), "粗实线"))
        lay = sr.layout
        if lay.extension:
            for seg in lay.segments:
                z0, z1 = seg.z0 * MM, seg.z1 * MM
                if lay.extension == "left" and z1 <= -L1 - e + 1e-6 or lay.extension == "right" and z0 >= W + L1 + e - 1e-6:
                    r = seg.d * MM / 2
                    items.append((x - r, (z0, -r, z1, r), "粗实线"))
                elif lay.extension == "left" and z0 < -L1 - e:
                    r = seg.d * MM / 2
                    items.append((x - r, (z0, -r, -L1 - e, r), "粗实线"))
                elif lay.extension == "right" and z1 > W + L1 + e:
                    r = seg.d * MM / 2
                    items.append((x - r, (W + L1 + e, -r, z1, r), "粗实线"))
    # 吊环螺钉、视孔盖、通气器
    ed = t.eyebolt_d * MM
    for xe in t.eyebolts:
        ye = envelope_height(t.cover_outer, xe) * MM
        xe *= MM
        items.append((xe - 1.1 * ed, (W / 2 - 1.1 * ed, ye - 2, W / 2 + 1.1 * ed, ye + 0.4 * ed), "粗实线"))
        items.append((xe - 0.9 * ed, (W / 2 - 0.9 * ed, ye + 0.4 * ed, W / 2 + 0.9 * ed, ye + 0.9 * ed), "粗实线"))
        items.append((xe - 1.6 * ed, (W / 2 - 0.4 * ed, ye + 0.9 * ed, W / 2 + 0.4 * ed, ye + 0.9 * ed + 3.2 * ed), "粗实线"))
    ins = t.inspection
    a = math.radians(ins.angle)
    L, Bw, th = ins.length * MM, ins.width * MM, ins.thickness * MM
    cx, cy = ins.center[0] * MM, ins.center[1] * MM
    y_lo = cy - L / 2 * abs(math.sin(a))
    y_hi = cy + L / 2 * abs(math.sin(a)) + th * math.cos(a)
    items.append((cx - L / 2, (W / 2 - Bw / 2, y_lo, W / 2 + Bw / 2, y_hi), "粗实线"))
    vd = ins.vent_d * MM
    yv = cy + th
    items.append((cx - 0.9 * vd, (W / 2 - 0.9 * vd, yv + 0.5 * vd, W / 2 + 0.9 * vd, yv + 0.9 * vd), "粗实线"))
    items.append((cx - 0.6 * vd, (W / 2 - 0.6 * vd, yv, W / 2 + 0.6 * vd, yv + 0.5 * vd), "粗实线"))
    items.append((cx - 0.45 * vd, (W / 2 - 0.45 * vd, yv + 0.9 * vd, W / 2 + 0.45 * vd, yv + 1.4 * vd), "粗实线"))

    items.sort(key=lambda it: it[0])
    drawn: list[tuple[float, float, float, float]] = []
    for _, (z0, y0, z1, y1), layer in items:
        for p, q in (((z0, y0), (z1, y0)), ((z1, y0), (z1, y1)), ((z1, y1), (z0, y1)), ((z0, y1), (z0, y0))):
            for a_, b_ in hidden.visible_segments(p, q, rects=drawn):
                v.line(a_, b_, layer)
        drawn.append((z0, y0, z1, y1))
    # 轴线、对称中心线
    zl = [min(s.layout.segments[0].z0 for s in d.shafts) * MM, max(s.layout.segments[-1].z1 for s in d.shafts) * MM]
    v.centerline((zl[0], 0), (zl[1], 0), 4)
    v.centerline((W / 2, yb), (W / 2, top + 4.6 * ed), 4)


# ====================================================================== 标准件、配合、序号

def _standard_parts(d: ReducerDesign, t: HousingDetail, add):
    """补齐没有画出序号引线的数量（轴承盖、螺钉的总数等）。"""
    n_open = sum(1 for s in d.shafts if s.layout.extension)
    for name, qty in (("轴承透盖", n_open), ("轴承闷盖", 2 * len(d.shafts) - n_open)):
        p = add(name, qty, "HT200")
        p.qty = str(qty)
    # 轴承盖螺钉按规格汇总
    counts: dict[str, int] = {}
    for cap in t.caps:
        d3 = cap.d3 * MM
        name = f"螺钉 M{d3:g}×{_std(d.housing.cap_thickness * MM + 1.5 * d3, SCREW_L)}"
        counts[name] = counts.get(name, 0) + 2 * cap.n
    for name, n in counts.items():
        p = add(name, n, "Q235", "GB/T 5783-2016")
        p.qty = str(n)


def _fits(d: ReducerDesign, v: View, sh: Sheet):
    fits = []
    for sr in d.shafts:
        lay = sr.layout
        x = lay.x * MM
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


def _place_balloons(sh: Sheet, parts: list[Part], lanes: dict):
    """按 FL（上→下）、TL（上→下）、TR（下→上）、FR（下→上）、FT（右→左）的顺序编号，即沿图形四周逆时针。"""
    groups: dict[str, list[Part]] = {k: [] for k in lanes}
    for p in parts:
        if p.target is not None and p.group in groups:
            groups[p.group].append(p)
    placed: dict[str, list[tuple[Part, tuple[float, float]]]] = {}
    for g, items in groups.items():
        kind, pos, (lo, hi) = lanes[g]
        if kind == "col":
            items.sort(key=lambda p: -p.target[1])
            ys = []
            for p in items:
                y = min(p.target[1], hi) if not ys else min(p.target[1], ys[-1] - 10)
                ys.append(y)
            if ys and ys[-1] < lo:  # 超出下边界：整体上移
                shift = lo - ys[-1]
                ys = [y + shift for y in ys]
                for k in range(len(ys) - 2, -1, -1):
                    ys[k] = max(ys[k], ys[k + 1] + 10)
            placed[g] = [(p, (pos, y)) for p, y in zip(items, ys)]
        else:
            items.sort(key=lambda p: p.target[0])
            xs_: list[float] = []
            for p in items:
                xs_.append(max(p.target[0], lo) if not xs_ else max(p.target[0], xs_[-1] + 12))
            if xs_ and xs_[-1] > hi:
                shift = xs_[-1] - hi
                xs_ = [x - shift for x in xs_]
                for k in range(1, len(xs_)):
                    xs_[k] = max(xs_[k], xs_[k - 1] + 12)
            placed[g] = [(p, (x, pos)) for p, x in zip(items, xs_)]
    order: list[tuple[Part, tuple[float, float]]] = []
    order += placed.get("FL", [])
    order += placed.get("TL", [])
    order += list(reversed(placed.get("TR", [])))
    order += list(reversed(placed.get("FR", [])))
    order += list(reversed(placed.get("FT", [])))
    ballooned = [p for p, _ in order]
    rest = [p for p in parts if p not in ballooned]
    parts[:] = ballooned + rest
    for i, (p, at) in enumerate(order, 1):
        sh.balloon(p.target, at, i)

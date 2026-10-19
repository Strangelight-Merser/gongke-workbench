"""箱体细部：箱盖外形、轴承盖、连接螺栓、视孔盖、通气器、吊环螺钉、吊钩、油标、放油螺塞、定位销、起盖螺钉。

三维模型和装配图共用这里的尺寸，坐标系与 `layout.reducer` 相同（单位 m）：
x 沿三根轴的中心连线，y 向上（剖分面 y = 0），z 沿轴线（箱体内壁 z = 0 … W）。

尺寸按《机械设计课程设计》指导书"减速器附件"一节的经验关系取值，均为设计底稿用的常用值，
定稿时应按手册核对附件标准（JB/ZQ 4450 视孔盖、GB/T 825 吊环螺钉、JB/ZQ 4450 放油螺塞等）。

箱盖外形取"包络各轴大齿轮和轴承座的圆的上凸包"：每根轴一个圆，半径
R = max(齿顶圆半径 + Δ1 + δ, 轴承座半径)，相邻圆之间用外公切线连接。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from gongke_core.layout.reducer import MM, SPANNER_CLEARANCE_MM, Housing, ceil_to


# ---------------------------------------------------------------- 包络（圆的上凸包）

@dataclass
class Arc:
    cx: float
    cy: float
    r: float
    a0: float  # 起止角（度，逆时针）
    a1: float


@dataclass
class Seg:
    p: tuple[float, float]
    q: tuple[float, float]


def _upper_hull_order(circles: list[tuple[float, float]]) -> list[int]:
    """返回在上凸包上出现的圆（按 x 从左到右）。圆心都在 y = 0 上。"""
    pts = []
    for i, (cx, r) in enumerate(circles):
        for k in range(181):
            a = math.radians(k)
            pts.append((cx + r * math.cos(a), r * math.sin(a), i))
    pts.sort(key=lambda p: (p[0], p[1]))
    hull: list[tuple[float, float, int]] = []
    for p in pts:
        while len(hull) >= 2:
            (x1, y1, _), (x2, y2, _) = hull[-2], hull[-1]
            if (x2 - x1) * (p[1] - y1) - (y2 - y1) * (p[0] - x1) >= 0:
                hull.pop()
            else:
                break
        hull.append(p)
    order: list[int] = []
    for _, _, i in hull:
        if not order or order[-1] != i:
            order.append(i)
    return order


def upper_envelope(circles: list[tuple[float, float]],
                   left_wall: tuple[float, float] | None = None) -> list[Arc | Seg]:
    """圆心在 y = 0 上的若干圆的上凸包：圆弧 + 外公切线，从左端 (x−R, 0) 到右端 (x+R, 0)。

    left_wall = (x_w, h_w) 时左端改为竖直端壁：从 (x_w, 0) 竖直向上到 h_w，再作切线接到第一个圆
    （圆心须在 x_w 右侧；端壁顶点落在圆内时，端壁只升到与圆相交处）。
    """
    order = _upper_hull_order(circles)
    if left_wall is not None:
        return _with_left_wall(circles, order, left_wall)
    # 相邻两圆的上外公切线：法向 n = (cos φ, sin φ)，cos φ = (R1 − R2)/d
    phis = []
    for i, j in zip(order, order[1:]):
        (x1, r1), (x2, r2) = circles[i], circles[j]
        phis.append(math.degrees(math.acos(max(-1.0, min(1.0, (r1 - r2) / (x2 - x1))))))
    out: list[Arc | Seg] = []
    for k, i in enumerate(order):
        cx, r = circles[i]
        a_left = 180.0 if k == 0 else phis[k - 1]
        a_right = 0.0 if k == len(order) - 1 else phis[k]
        if a_left - a_right > 1e-6:
            out.append(Arc(cx, 0.0, r, a_right, a_left))
        if k < len(order) - 1:
            phi = math.radians(phis[k])
            cx2, r2 = circles[order[k + 1]]
            out.append(Seg((cx + r * math.cos(phi), r * math.sin(phi)), (cx2 + r2 * math.cos(phi), r2 * math.sin(phi))))
    return out


def _with_left_wall(circles, order, wall) -> list[Arc | Seg]:
    xw, hw = wall
    env = upper_envelope([circles[i] for i in order])
    arcs = [k for k, e in enumerate(env) if isinstance(e, Arc)]
    for n, k in enumerate(arcs):
        arc = env[k]
        cx, r = arc.cx, arc.r
        dx = xw - cx
        seg: list[Arc | Seg] = []
        if math.hypot(dx, hw) <= r + 1e-12:
            y = math.sqrt(max(r * r - dx * dx, 0.0))
            seg.append(Seg((xw, 0.0), (xw, y)))
            a_start = math.degrees(math.atan2(y, dx))
        else:
            seg.append(Seg((xw, 0.0), (xw, hw)))
            a_start = math.degrees(math.atan2(hw, dx) - math.acos(r / math.hypot(dx, hw)))
            t = math.radians(a_start)
            seg.append(Seg((xw, hw), (cx + r * math.cos(t), r * math.sin(t))))
        # 切点越过本段圆弧的右端时，说明端壁顶点直接与后面的圆相切
        if a_start <= arc.a0 + 1e-9 and n < len(arcs) - 1:
            continue
        a_start = max(a_start, arc.a0)
        if a_start - arc.a0 > 1e-6:
            seg.append(Arc(cx, 0.0, r, arc.a0, a_start))
        return seg + env[k + 1:]
    raise AssertionError("unreachable")


def envelope_points(env: list[Arc | Seg], step_deg: float = 3.0) -> list[tuple[float, float]]:
    """把包络离散成从左到右的折线点（三维建模用）。"""
    pts: list[tuple[float, float]] = []
    for e in env:
        if isinstance(e, Arc):
            n = max(2, int(math.ceil((e.a1 - e.a0) / step_deg)))
            for k in range(n + 1):
                a = math.radians(e.a1 - (e.a1 - e.a0) * k / n)  # 从左向右：角度从大到小
                pts.append((e.cx + e.r * math.cos(a), e.cy + e.r * math.sin(a)))
        else:
            pts.extend([e.p, e.q])
    clean = [pts[0]]
    for p in pts[1:]:
        if math.hypot(p[0] - clean[-1][0], p[1] - clean[-1][1]) > 1e-7:
            clean.append(p)
    return clean


def envelope_height(env: list[Arc | Seg], x: float) -> float:
    for e in env:
        if isinstance(e, Arc):
            xa, xb = e.cx + e.r * math.cos(math.radians(e.a1)), e.cx + e.r * math.cos(math.radians(e.a0))
            if xa - 1e-9 <= x <= xb + 1e-9:
                return e.cy + math.sqrt(max(e.r**2 - (x - e.cx) ** 2, 0.0))
        else:
            if e.p[0] - 1e-9 <= x <= e.q[0] + 1e-9:
                t = (x - e.p[0]) / (e.q[0] - e.p[0])
                return e.p[1] + t * (e.q[1] - e.p[1])
    return 0.0


# ---------------------------------------------------------------- 附件

@dataclass
class BearingCap:
    """凸缘式轴承盖：螺钉 d3、数量 n，外径 D2 = D + 5d3，螺钉分布圆 D0 = D + 2.5d3。"""

    D: float
    d3: float
    n: int

    @property
    def D2(self) -> float:
        return self.D + 5 * self.d3

    @property
    def D0(self) -> float:
        return self.D + 2.5 * self.d3


def cap_screw(D: float) -> tuple[float, int]:
    """轴承盖螺钉直径和数目（按轴承外径，指导书常用值）。"""
    Dm = D / MM
    if Dm <= 65:
        return 6 * MM, 4
    if Dm <= 100:
        return 8 * MM, 4
    if Dm <= 140:
        return 10 * MM, 6
    return 12 * MM, 6


def boss_radius(D: float) -> float:
    """轴承座外圆半径（与三维模型一致）。"""
    return D / 2 + max(0.25 * D, 12 * MM)


@dataclass
class InspectionCover:
    """视孔盖：贴在箱盖外表面的一段公切线上。"""

    center: tuple[float, float]  # 盖板底面中点
    angle: float  # 盖板方向（度）
    length: float  # 沿切线方向
    width: float  # 沿 z
    thickness: float
    hole_length: float
    hole_width: float
    screw_d: float
    vent_d: float  # 通气器螺纹规格


@dataclass
class SideBore:
    """圆锥-圆柱减速器Ⅰ轴穿过 −x 端壁的轴承座孔（装套杯），轴线沿 −x、在剖分面上 z 处。"""

    z: float
    D: float  # 座孔直径（套杯外径）
    boss_r: float
    x_face: float  # 轴承座外端面（套杯凸缘贴合面）的 x
    cap: BearingCap  # 套杯凸缘与轴承盖的螺钉


@dataclass
class WormBore:
    """蜗杆轴穿过左右端壁的轴承座孔，轴线沿 x、在 (y, z) 处。座孔从内凸台端面 |x| = x_inner 通到外端面 x_face。"""

    y: float
    z: float
    D: float
    boss_r: float
    x_inner: float
    x_face: float
    cap: BearingCap


@dataclass
class HousingDetail:
    h: Housing
    shaft_x: list[float]
    caps: list[BearingCap]
    boss_r: list[float]
    cover_r: list[float]  # 箱盖外形各圆半径
    cover_outer: list[Arc | Seg]
    cover_inner: list[Arc | Seg]
    x_outer: tuple[float, float]  # 箱座外壁
    flange_w: float  # 凸缘伸出外壁的宽度 c1 + c2
    y_bottom: float  # 箱座底面
    foot_w: float  # 底座凸缘伸出外壁的宽度
    bearing_bolts: list[float]  # 轴承旁螺栓 d1 的 x 位置（两侧凸缘各一排）
    flange_bolts: list[float]  # 箱盖箱座连接螺栓 d2 的 x 位置
    bolt_length_d1: float
    bolt_length_d2: float
    pins: list[tuple[float, float]]  # 定位销 (x, z)
    pin_d: float
    jack_screw: tuple[float, float]  # 起盖螺钉 (x, z)
    foot_bolts: list[tuple[float, float]]  # 地脚螺栓 (x, z)
    inspection: InspectionCover
    eyebolts: list[float]  # 吊环螺钉 x 位置（装在箱盖顶部）
    eyebolt_d: float
    oil_level: float  # 油面 y
    dipstick: tuple[tuple[float, float], float]  # 油标座在右端壁的位置 (x, y)、倾角（度）
    drain: tuple[float, float]  # 放油螺塞中心 (x, y)
    drain_d: float
    hooks: list[float] = field(default_factory=list)  # 吊钩所在端壁 x
    side_bore: SideBore | None = None
    worm_bore: WormBore | None = None
    accessory_wall: str = "x"  # 油标和放油螺塞所在的壁："x" 为右端壁，"z" 为前侧壁（z = W + δ）
    hook_drop: float = 0.0  # 吊钩自上缘向下的高度

    def hook_shape(self, xe: float) -> tuple[list[tuple[float, float]], tuple[float, float], float]:
        """箱座端壁 xe 处铸出的吊钩（在中间平面 z = W/2 的外形）：(轮廓折线, 吊孔中心, 吊孔半径)，单位 m。
        上缘让开凸缘下的螺母，下方不碰端壁上的油标座。"""
        fw = self.flange_w
        sg = 1 if xe > sum(self.x_outer) / 2 else -1
        yt = -self.h.flange_base - 1.6 * self.h.bolt_bearing
        drop = self.hook_drop or 2 * fw
        y2 = yt - max(0.35 * drop, 0.5 * fw)
        r = 0.18 * fw
        pts = [(xe, yt), (xe + sg * 0.9 * fw, yt), (xe + sg * 0.9 * fw, y2), (xe, yt - drop)]
        return pts, (xe + sg * 0.45 * fw, yt - max(r + 3e-3, 0.2 * min(drop, 2 * fw))), r

    @property
    def z_range(self) -> tuple[float, float]:
        return -self.h.delta, self.h.inner_width + self.h.delta

    @property
    def cover_top(self) -> float:
        return max(self.cover_r)


BOLT_LENGTHS_MM = [20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 80, 90, 100, 110, 120, 130, 140, 150]  # GB/T 5782 常用长度


def bolt_length(h: Housing, d: float) -> float:
    """穿过箱盖、箱座凸缘的螺栓长度：两凸缘厚 + 弹簧垫圈 0.25d + 螺母 0.8d + 伸出 0.3d，取标准长度。"""
    need = (h.flange_base + h.flange_cover + 1.35 * d) / MM
    return next((v for v in BOLT_LENGTHS_MM if v >= need - 1e-9), BOLT_LENGTHS_MM[-1]) * MM


def _fill(a: float, b: float, max_pitch: float) -> list[float]:
    n = int(math.ceil((b - a) / max_pitch - 1e-9))
    return [a + (b - a) * k / n for k in range(1, n)]


def detail(d) -> HousingDetail:
    """由设计结果（`design.ReducerDesign`）确定箱体细部。"""
    h = d.housing
    bevel = getattr(d, "bevel", None)
    ws = getattr(d, "worm_shaft", None)
    # 轴线沿 z 的各轴（圆锥-圆柱减速器的Ⅰ轴、蜗杆轴沿 x，单独处理）
    zs = d.shafts[1:] if bevel or ws else d.shafts
    xs = [s.layout.x for s in zs]
    Ds = [s.layout.bearing.D for s in zs]
    caps = [BearingCap(D, *cap_screw(D)) for D in Ds]
    boss = [boss_radius(D) for D in Ds]
    xo = (h.x_range[0] - h.delta, h.x_range[1] + h.delta)
    # 各轴上最大的齿轮齿顶圆
    if bevel:
        tips = [max(bevel.da2, d.low.da1) / 2, d.low.da2 / 2]
    elif ws:
        tips = [d.worm.de2 / 2]
    else:
        tips = [d.high.da1 / 2, max(d.high.da2, d.low.da1) / 2, d.low.da2 / 2]
    cover_r = [max(t + h.gap_radial + h.delta, b) for t, b in zip(tips, boss)]
    worm_bore = None
    if ws:
        # 蜗杆减速器的箱盖是一个半圆拱，两端落在箱座端壁外表面上
        cover_r = [max(cover_r[0], xo[1])]
        from gongke_core.layout.worm_reducer import boss_radius as worm_boss

        D = ws.bearing.D
        worm_bore = WormBore(-d.worm.a, h.inner_width / 2, D, worm_boss(D), ws.seat_inner, ws.seat_outer,
                             BearingCap(D, *cap_screw(D)))
    side = None
    wall_o = wall_i = None
    if bevel:
        from gongke_core.layout.bevel_reducer import cup

        c = cup(d.pinion)
        side = SideBore(d.positions.z_apex, c.D_out, boss_radius(c.D_out), -c.u_flange,
                        BearingCap(c.D_out, c.screw_d, c.screws))
        hw = max(side.boss_r, bevel.da1 / 2 + h.gap_radial + h.delta1)
        wall_o, wall_i = (xo[0], hw), (h.x_range[0], hw - h.delta1)
    outer = upper_envelope(list(zip(xs, cover_r)), wall_o)
    inner = upper_envelope([(x, r - h.delta1) for x, r in zip(xs, cover_r)], wall_i)
    fw = h.c1 + h.c2
    y_bottom = h.y_range[0] - h.delta
    cf = SPANNER_CLEARANCE_MM.get(round(h.bolt_foot / MM), (26, 24))
    foot_w = (cf[0] + cf[1]) * MM

    # 轴承旁螺栓：尽量靠近轴承孔，S ≈ D2；相邻两轴的螺栓太近时合并为一个
    bb: list[float] = []
    for x, cap, rb in zip(xs, caps, boss):
        s = max(cap.D2 / 2, cap.D / 2 + h.bolt_bearing)
        bb.extend([x - s, x + s])
    bb.sort()
    merged: list[float] = []
    for x in bb:
        if merged and x - merged[-1] < 2.5 * h.bolt_bearing:
            merged[-1] = (merged[-1] + x) / 2
        else:
            merged.append(x)
    # 箱盖箱座连接螺栓：两端各一个（离轴承旁螺栓太近时省去），中间间距不大于 150 mm
    ends = [e for e in (xo[0] - fw / 2, xo[1] + fw / 2) if min(abs(e - x) for x in merged) > 3 * h.bolt_flange]
    stations = sorted(ends + merged)
    fb = list(ends)
    for a, b in zip(stations, stations[1:]):
        fb.extend(_fill(a, b, 150 * MM))
    fb.sort()

    W = h.inner_width
    if side:  # 左端壁上有Ⅰ轴轴承座，定位销改放在凸缘的对角上
        pins = [(xo[0] - fw / 2, -h.delta - fw / 2), (xo[1] + fw / 2, W + h.delta + fw / 2)]
    else:
        pins = [(xo[0] - fw / 2, W * 0.25), (xo[1] + fw / 2, W * 0.75)]
    # 起盖螺钉：装在前侧凸缘上，离各螺栓最远、且不被轴承盖挡住（主视图中可见）的位置
    xs_all = merged + fb
    best, jx = -1.0, xo[0] - fw / 2
    n = 400
    for k in range(n + 1):
        x = xo[0] - fw + h.bolt_flange + (xo[1] - xo[0] + 2 * fw - 2 * h.bolt_flange) * k / n
        if any(abs(x - xc) < cap.D2 / 2 + h.bolt_flange for xc, cap in zip(xs, caps)):
            continue
        if side and x < xo[0] + h.bolt_flange:
            continue
        score = min(abs(x - b) for b in xs_all)
        if score > best:
            best, jx = score, x
    jack = (jx, W + h.delta + fw / 2)
    zfoot = (-h.delta - foot_w / 2, W + h.delta + foot_w / 2)
    foot_bolts = [(x, z) for x in (xo[0] + 0.15 * (xo[1] - xo[0]), xo[1] - 0.1 * (xo[1] - xo[0])) for z in zfoot]

    # 视孔盖：放在低速级啮合区上方那段公切线上（没有公切线时放在最高圆顶部）
    x_mesh = 0.0 if ws else xs[-2] + d.low.d1 / 2
    seg = None
    for e in outer:
        if isinstance(e, Seg) and e.p[0] - 1e-9 <= x_mesh <= e.q[0] + 1e-9:
            seg = e
    if seg is None:
        segs = [e for e in outer if isinstance(e, Seg)]
        seg = max(segs, key=lambda e: math.dist(e.p, e.q)) if segs else None
    hole_w = ceil_to(min(0.5 * W, 100 * MM), 5 * MM)
    if seg is not None:
        L = math.dist(seg.p, seg.q)
        length = ceil_to(min(max(0.45 * L, 90 * MM), 160 * MM, L - 10 * MM), 5 * MM)
        ang = math.degrees(math.atan2(seg.q[1] - seg.p[1], seg.q[0] - seg.p[0]))
        t = (x_mesh - seg.p[0]) / (seg.q[0] - seg.p[0])
        t = min(max(t, length / 2 / L + 0.02), 1 - length / 2 / L - 0.02)
        c = (seg.p[0] + t * (seg.q[0] - seg.p[0]), seg.p[1] + t * (seg.q[1] - seg.p[1]))
    else:
        i = max(range(len(xs)), key=lambda k: cover_r[k])
        length, ang, c = 120 * MM, 0.0, (xs[i], cover_r[i])
    insp = InspectionCover(c, ang, length, hole_w + 40 * MM, 6 * MM, length - 40 * MM, hole_w, 6 * MM, 16 * MM)

    # 吊环螺钉：装在箱盖两端的顶部（高速轴、低速轴上方）
    if bevel:
        eye_d = 10 * MM if d.low.a + bevel.d2 / 2 <= 350 * MM else 12 * MM
        eyebolts = [(xo[0] + xs[0]) / 2, xs[-1]]
    elif ws:
        eye_d = 10 * MM if d.worm.a <= 200 * MM else 12 * MM
        eyebolts = [-0.6 * cover_r[0], 0.6 * cover_r[0]]
    else:
        eye_d = 10 * MM if d.high.a + d.low.a <= 350 * MM else 12 * MM
        eyebolts = [xs[0] + 0.3 * (xs[1] - xs[0]), xs[2]]
    if ws:
        # 蜗杆下置：油面到蜗杆最低滚动体中心，且蜗杆至少浸入一个模数
        w = d.worm
        brg = ws.bearing
        oil = max(-w.a - (brg.d + brg.D) / 4, -w.a - w.da1 / 2 + w.m)
    else:
        # 油面：低速级大齿轮浸油 1～2 个齿高且不小于 10 mm
        immerse = max(10 * MM, 2 * 2.25 * d.low.mn)
    # 同时保证高速级大齿轮浸到约一个齿高（与 design 中的浸油深度校核一致）
    if ws:
        pass
    elif bevel:  # 大锥齿轮浸入 0.7 倍齿宽（与 bevel_design 的浸油校核一致）
        oil = max(-d.low.da2 / 2 + immerse, -bevel.da2 / 2 + 0.7 * bevel.b * math.sin(bevel.delta2))
    else:
        oil = max(-d.low.da2 / 2 + immerse, -d.high.da2 / 2 + 2.25 * d.high.mn)
    dip = ((xo[1], oil + 20 * MM), 45.0)  # 油标座在油面以上，油标杆斜插入油池
    drain = (xo[1], y_bottom + h.flange_foot + 0.9 * 16 * MM + 3 * MM)  # 紧贴底座凸缘上方，尽量低
    wall = "x"
    if ws:  # 端壁被蜗杆轴承座占满，油标和放油螺塞装在前侧壁上，避开中间的蜗杆
        wall = "z"
        xa = 0.5 * (xo[1] + max(w.b1 / 2, 0.0))
        dip = ((xa, oil + 20 * MM), 45.0)
        drain = (xa, drain[1])
    # 吊钩高度：下端离端壁上的油标座至少 5 mm
    drop = 2 * fw
    if wall == "x":
        dip_top = dip[0][1] + 11 * MM * math.sqrt(2)
        yt = -h.flange_base - 1.6 * h.bolt_bearing
        drop = max(min(drop, yt - dip_top - 5 * MM), 0.8 * fw)
    return HousingDetail(
        h, xs, caps, boss, cover_r, outer, inner, xo, fw, y_bottom, foot_w,
        merged, fb, bolt_length(h, h.bolt_bearing), bolt_length(h, h.bolt_flange),
        pins, max(0.75 * h.bolt_flange, 6 * MM), jack, foot_bolts, insp, eyebolts, eye_d, oil, dip, drain,
        16 * MM, [xo[1]] if side else [xo[0], xo[1]], side, worm_bore, wall, drop,
    )

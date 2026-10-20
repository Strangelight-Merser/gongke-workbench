"""齿根弯曲应力的二维有限元模型：取三个齿的扇形（平面应力，厚 1 mm），中间齿的齿顶加载，求齿根最大拉应力，
与教材公式 σF = Ft·YFa·YSa/(b·m) 中的 YFa·YSa 对照。

齿廓由 `calc.tooth_profile` 按齿条刀具展成（含齿根过渡曲线）；网格由 Gmsh（GPL，独立进程）划分，
二次三角形单元，过渡曲线处加密；求解用 CalculiX（CPS6 单元）。模数取 1 mm、Ft = 1 N、b = 1 mm，
这样齿根最大拉应力（MPa）在数值上就等于 YFa·YSa。

载荷作用在齿顶（与教材 YFa 的定义一致）：法向力 Fn = Ft / cos α，沿齿顶处齿廓法线指向齿内。
轮缘取齿根圆以下 3.5m，内圆和两侧剖切边固定。
"""

from __future__ import annotations

import math
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from gongke_core.calc import tooth_profile
from gongke_core.fem import ccx

E_MPA = 206000.0
NU = 0.3


class GmshNotFound(RuntimeError):
    pass


def find_gmsh() -> Path:
    env = os.environ.get("GONGKE_GMSH")
    if env and Path(env).is_file():
        return Path(env)
    p = shutil.which("gmsh")
    if p:
        return Path(p)
    # FreeCAD 安装目录自带 gmsh，通常和 ccx 在同一个 bin 目录
    try:
        exe = ccx.find()
        cand = exe.parent / ("gmsh.exe" if sys.platform.startswith("win") else "gmsh")
        if cand.is_file():
            return cand
    except ccx.CcxNotFound:
        pass
    raise GmshNotFound("没有找到网格划分程序 gmsh：请安装 FreeCAD（自带 gmsh）或 gmsh，也可以用环境变量 GONGKE_GMSH 指定路径。")


def _rot(p, a):
    c, s = math.cos(a), math.sin(a)
    return (p[0] * c - p[1] * s, p[0] * s + p[1] * c)


@dataclass
class ToothModel:
    z: float
    nodes: dict[int, tuple[float, float]]
    elements: list[tuple[int, ...]]  # 6 节点三角形
    fixed: set[int]
    fillet_nodes: set[int]  # 中间齿两侧过渡曲线上的节点
    load_node: int
    load: tuple[float, float]  # (Fx, Fy)，N


def write_geo(path: Path, z: float, h_global: float = 0.12, h_fillet: float = 0.02, rim: float = 3.5) -> dict:
    """写 Gmsh 几何脚本（m = 1）。返回加载点坐标和载荷方向等信息。"""
    prof = tooth_profile.generate(z)
    pitch = 2 * math.pi / z
    parts = ("root", "fillet", "involute", "tip")
    pts: list[tuple[float, float]] = []
    pid: dict[tuple[float, float], int] = {}
    lines: list[str] = ["// GongKe gear tooth model (m = 1 mm)"]

    def point(p):
        key = (round(p[0], 8), round(p[1], 8))
        if key not in pid:
            pts.append(p)
            pid[key] = len(pts)
            lines.append(f"Point({len(pts)}) = {{{p[0]:.10f}, {p[1]:.10f}, 0, {h_global}}};")
        return pid[key]

    curves: list[tuple[str, int]] = []  # (种类, 曲线号)

    def spline(kind, seq):
        ids = [point(p) for p in seq]
        ids = [i for k, i in enumerate(ids) if k == 0 or i != ids[k - 1]]
        if len(ids) < 2:
            return
        n = len(curves) + 1
        lines.append(f"{'Line' if len(ids) == 2 else 'Spline'}({n}) = {{{', '.join(map(str, ids))}}};")
        curves.append((kind, n))

    load_pt = None
    # 从右侧剖切边开始逆时针：齿 k = −1, 0, 1（中心角 π/2 + k·pitch）
    for k in (-1, 0, 1):
        a = k * pitch
        right = {name: [_rot(p, a) for p in getattr(prof, name)] for name in parts}
        left = {name: [_rot((-p[0], p[1]), a) for p in reversed(getattr(prof, name))] for name in parts}
        for name in parts:
            spline(f"{name}{'_mid_r' if k == 0 else ''}", right[name])
        for name in reversed(parts):
            spline(f"{name}{'_mid_l' if k == 0 else ''}", left[name])
        if k == 0:
            inv = prof.involute
            load_pt = inv[-1]
            tx, ty = inv[-1][0] - inv[-2][0], inv[-1][1] - inv[-2][1]
            tl = math.hypot(tx, ty)
            n_in = (-ty / tl, tx / tl)  # 右齿廓（向上走）外法线为 (ty, −tx)，取反指向齿内
    # 两侧剖切边和轮缘内圆
    ri = prof.rf - rim
    a_r, a_l = math.pi / 2 - 3 * math.pi / z, math.pi / 2 + 3 * math.pi / z
    first = pts[0]
    last = _rot((-prof.root[0][0], prof.root[0][1]), pitch)  # 齿 1 左侧齿槽中线处的齿根圆点
    p_ir = (ri * math.cos(a_r), ri * math.sin(a_r))
    p_il = (ri * math.cos(a_l), ri * math.sin(a_l))
    spline("side", [last, p_il])
    c0 = point((0.0, 0.0))
    il, ir = point(p_il), point(p_ir)
    n = len(curves) + 1
    lines.append(f"Circle({n}) = {{{il}, {c0}, {ir}}};")
    curves.append(("inner", n))
    spline("side", [p_ir, first])
    lines.append(f"Curve Loop(1) = {{{', '.join(str(c) for _, c in curves)}}};")
    lines.append("Plane Surface(1) = {1};")
    fil = [c for kind, c in curves if kind.startswith("fillet_mid")]
    fixed = [c for kind, c in curves if kind in ("side", "inner")]
    lines += [f"Physical Curve(\"fixed\", 1) = {{{', '.join(map(str, fixed))}}};",
              f"Physical Curve(\"fillet\", 2) = {{{', '.join(map(str, fil))}}};",
              "Physical Surface(\"tooth\", 3) = {1};",
              # 过渡曲线附近加密
              "Field[1] = Distance;", f"Field[1].CurvesList = {{{', '.join(map(str, fil))}}};", "Field[1].Sampling = 200;",
              "Field[2] = Threshold;", "Field[2].InField = 1;", f"Field[2].SizeMin = {h_fillet};",
              f"Field[2].SizeMax = {h_global};", "Field[2].DistMin = 0.05;", "Field[2].DistMax = 0.6;",
              "Background Field = 2;", "Mesh.MeshSizeExtendFromBoundary = 0;", "Mesh.ElementOrder = 2;",
              "Mesh.SecondOrderLinear = 0;", "Mesh.MshFileVersion = 2.2;", ""]
    path.write_text("\n".join(lines), encoding="ascii")
    return {"load_point": load_pt, "load_dir": n_in, "profile": prof}


def read_msh(path: Path):
    """读 Gmsh 2.2 ASCII 网格：节点、6 节点三角形、按物理组分的 3 节点线单元。"""
    nodes, tris, lines_by_tag = {}, [], {}
    it = iter(path.read_text().splitlines())
    for line in it:
        if line.startswith("$Nodes"):
            for _ in range(int(next(it))):
                i, x, y, _z = next(it).split()
                nodes[int(i)] = (float(x), float(y))
        elif line.startswith("$Elements"):
            for _ in range(int(next(it))):
                f = [int(v) for v in next(it).split()]
                etype, ntag = f[1], f[2]
                tags, conn = f[3:3 + ntag], f[3 + ntag:]
                if etype == 9:
                    tris.append(tuple(conn))
                elif etype == 8:
                    lines_by_tag.setdefault(tags[0], []).append(tuple(conn))
    return nodes, tris, lines_by_tag


def build(z: float, workdir: Path, name: str = "tooth", **mesh) -> ToothModel:
    workdir.mkdir(parents=True, exist_ok=True)
    geo = workdir / f"{name}.geo"
    info = write_geo(geo, z, **mesh)
    msh = workdir / f"{name}.msh"
    # 在工作目录中用相对文件名调用：Windows 上用户目录常含中文，避免外部程序处理非 ASCII 路径
    r = subprocess.run([str(find_gmsh()), geo.name, "-2", "-o", msh.name, "-v", "2"], cwd=workdir,
                       capture_output=True, text=True, errors="replace", timeout=300)
    if r.returncode != 0 or not msh.exists():
        raise RuntimeError(f"gmsh 划分网格失败：\n{(r.stdout + r.stderr)[-1500:]}")
    nodes, tris, lines_by_tag = read_msh(msh)
    fixed = {n for ln in lines_by_tag.get(1, []) for n in ln}
    fillet = {n for ln in lines_by_tag.get(2, []) for n in ln}
    lp = info["load_point"]
    load_node = min(nodes, key=lambda i: math.dist(nodes[i], lp))
    fn = 1.0 / math.cos(math.radians(20))  # Ft = 1 N
    d = info["load_dir"]
    return ToothModel(z, nodes, tris, fixed, fillet, load_node, (fn * d[0], fn * d[1]))


def write_inp(path: Path, m: ToothModel) -> None:
    lines = ["** GongKe gear tooth root stress model (mm, N, MPa), plane stress, t = 1 mm", "*NODE, NSET=NALL"]
    lines += [f"{i}, {x:.10f}, {y:.10f}" for i, (x, y) in sorted(m.nodes.items())]
    lines.append("*ELEMENT, TYPE=CPS6, ELSET=EALL")
    lines += [f"{k}, " + ", ".join(map(str, c)) for k, c in enumerate(m.elements, 1)]
    lines += ["*NSET, NSET=NFIX"] + [", ".join(map(str, sorted(m.fixed)[k:k + 16])) for k in range(0, len(m.fixed), 16)]
    lines += ["*MATERIAL, NAME=STEEL", "*ELASTIC", f"{E_MPA:.1f}, {NU}", "*SOLID SECTION, ELSET=EALL, MATERIAL=STEEL", "1.0",
              "*BOUNDARY", "NFIX, 1, 2, 0.0", "*STEP", "*STATIC", "*CLOAD",
              f"{m.load_node}, 1, {m.load[0]:.8e}", f"{m.load_node}, 2, {m.load[1]:.8e}",
              "*NODE FILE, OUTPUT=2D", "S", "*END STEP", ""]
    path.write_text("\n".join(lines), encoding="ascii")


def read_frd_stress(frd: Path) -> dict[int, tuple[float, ...]]:
    """读 .frd 中的节点应力 (SXX, SYY, SZZ, SXY, SYZ, SZX)。"""
    out, on = {}, False
    for line in frd.read_text(errors="replace").splitlines():
        if line.startswith(" -4  STRESS"):
            on = True
            continue
        if on:
            if line.startswith(" -3"):
                break
            if line.startswith(" -1"):
                node = int(line[3:13])
                vals = [float(line[13 + 12 * k:25 + 12 * k]) for k in range(6)]
                out[node] = tuple(vals)
    return out


def principal_2d(s) -> float:
    sxx, syy, sxy = s[0], s[1], s[3]
    c = 0.5 * (sxx + syy)
    return c + math.hypot(0.5 * (sxx - syy), sxy)


def _dominant(s) -> float:
    """绝对值较大的主应力（带符号），用于云图区分受拉、受压。"""
    sxx, syy, sxy = s[0], s[1], s[3]
    c, r = 0.5 * (sxx + syy), math.hypot(0.5 * (sxx - syy), sxy)
    return c + r if c >= 0 else c - r


@dataclass
class ToothResult:
    z: float
    yfs_fem: float  # 齿根最大拉应力（Ft = 1 N、b = m = 1 mm 时，MPa），即有限元得到的 YFa·YSa
    point: tuple[float, float]  # 最大拉应力位置（m = 1）
    angle_deg: float  # 该点处过渡曲线法线与齿对称线的夹角（30° 切线法的对照）
    n_nodes: int
    inp: Path
    nodes: dict[int, tuple[float, float]] = field(default_factory=dict, repr=False)
    triangles: list[tuple[int, int, int]] = field(default_factory=list, repr=False)  # 角点
    principal: dict[int, float] = field(default_factory=dict, repr=False)  # 节点主应力（取绝对值较大者，带符号），MPa


def solve(z: float, workdir: Path, name: str = "tooth", **mesh) -> ToothResult:
    m = build(z, workdir, name, **mesh)
    inp = workdir / f"{name}.inp"
    write_inp(inp, m)
    ccx.run(inp)
    stress = read_frd_stress(inp.with_suffix(".frd"))
    cand = [n for n in m.fillet_nodes if n in stress]
    best = max(cand, key=lambda n: principal_2d(stress[n]))
    p = m.nodes[best]
    # 用相邻过渡曲线节点估计切线方向，求该点法线与齿对称线（y 轴）的夹角
    near = sorted((n for n in m.fillet_nodes if n != best), key=lambda n: math.dist(m.nodes[n], p))[:2]
    (x1, y1), (x2, y2) = m.nodes[near[0]], m.nodes[near[1]]
    ang = math.degrees(math.atan2(abs(y2 - y1), abs(x2 - x1)))
    for ext in (".msh", ".geo"):
        (workdir / f"{name}{ext}").unlink(missing_ok=True)
    sp = {n: _dominant(v) for n, v in stress.items()}
    return ToothResult(z, principal_2d(stress[best]), p, ang, len(m.nodes), inp, m.nodes, [e[:3] for e in m.elements], sp)

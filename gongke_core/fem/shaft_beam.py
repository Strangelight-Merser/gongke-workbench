"""轴的梁单元有限元模型（CalculiX U1 梁单元），用于复核解析法算出的挠度和偏转角。

U1 是 ccx 2.21 起可用的两节点 Timoshenko 梁单元，按梁理论求解，节点有 3 个位移和 3 个转角。
没有用 B31/B32：ccx 会把它们展开成三维实体单元，在支点和集中力作用点出现局部变形，
细长轴的挠度反而偏小 20% 以上，不适合拿来复核。
模型：沿轴线（z）划分单元，每段按该段直径取圆截面（齿轮轴的轮齿段按齿根圆，与解析法一致）；
两轴承中心为铰支（左端还限制轴向位移和绕轴线转动）；齿轮啮合力作为集中力加在齿宽中点，
轴向力对轴线的偏距产生的力偶作为节点力矩。单位制 mm、N、MPa。
"""

from __future__ import annotations

import bisect
import math
from dataclasses import dataclass
from pathlib import Path

from gongke_core.calc.shaft import Segment, ShaftLoadCase
from gongke_core.calc.shaft_stiffness import E_STEEL
from gongke_core.fem import ccx

MM = 1e-3


@dataclass
class BeamResult:
    z: list[float]  # 节点 z，m，递增
    ux: list[float]  # m
    uy: list[float]
    rx: list[float]  # 截面绕 x、y 轴的转角，rad
    ry: list[float]

    def _interp(self, arr, z):
        i = min(max(bisect.bisect_left(self.z, z), 1), len(self.z) - 1)
        z0, z1 = self.z[i - 1], self.z[i]
        w = 0.0 if z1 == z0 else (z - z0) / (z1 - z0)
        return arr[i - 1] + w * (arr[i] - arr[i - 1])

    def deflection(self, z: float) -> float:
        return math.hypot(self._interp(self.ux, z), self._interp(self.uy, z))

    def slope(self, z: float) -> float:
        """截面偏转角（两平面合成）。"""
        return math.hypot(self._interp(self.rx, z), self._interp(self.ry, z))


def _diameter(segments: list[Segment], z: float) -> float:
    seg = next((s for s in segments if s.z0 <= z <= s.z1), segments[0] if z < segments[0].z0 else segments[-1])
    return seg.root_d or seg.d


def write_inp(path: Path, segments: list[Segment], case: ShaftLoadCase, E: float = E_STEEL, nu: float = 0.3,
              h_max: float = 2e-3) -> list[float]:
    """写出 CalculiX 输入文件，返回各节点的 z（m，按节点号顺序）。"""
    z0, z1 = segments[0].z0, segments[-1].z1
    za, zb = case.supports
    brk = {round(v, 9) for v in [z0, z1, za, zb] + [s.z0 for s in segments] + [s.z1 for s in segments]
           + [p.z for p in case.loads]}
    brk = sorted(v for v in brk if z0 - 1e-9 <= v <= z1 + 1e-9)
    nodes = [brk[0]]
    for a, b in zip(brk, brk[1:]):
        if b - a < 1e-7:
            continue
        n = max(int(math.ceil((b - a) / h_max)), 1)
        nodes += [a + (b - a) * (k + 1) / n for k in range(n)]
    # 按直径分组（单元 k 连接节点 k、k+1）
    groups: dict[float, list[int]] = {}
    for k in range(1, len(nodes)):
        d = round(_diameter(segments, 0.5 * (nodes[k - 1] + nodes[k])) / MM, 4)
        groups.setdefault(d, []).append(k)

    def node_at(z):
        return min(range(len(nodes)), key=lambda i: abs(nodes[i] - z)) + 1

    kappa = 6 * (1 + nu) / (7 + 6 * nu)  # 实心圆截面剪切系数（Cowper）
    lines = ["** GongKe shaft beam model (mm, N, MPa), U1 Timoshenko beam elements", "*NODE, NSET=NALL"]
    lines += [f"{i}, 0.0, 0.0, {z / MM:.6f}" for i, z in enumerate(nodes, 1)]
    lines += ["*USER ELEMENT, TYPE=U1, INTEGRATION POINTS=2, MAXDOF=6, NODES=2", "*ELEMENT, TYPE=U1, ELSET=EALL"]
    lines += [f"{k}, {k}, {k + 1}" for k in range(1, len(nodes))]
    lines += ["*MATERIAL, NAME=STEEL", "*ELASTIC", f"{E / 1e6:.1f}, {nu}"]
    for j, (d, ids) in enumerate(sorted(groups.items()), 1):
        lines.append(f"*ELSET, ELSET=D{j}")
        lines += [", ".join(str(i) for i in ids[k:k + 16]) for k in range(0, len(ids), 16)]
        area, inertia = math.pi * d * d / 4, math.pi * d**4 / 64
        # SECTION=GENERAL 数据行：A, I11, I12, I22, 剪切系数；第二行为截面 1 方向
        lines += [f"*BEAM SECTION, ELSET=D{j}, MATERIAL=STEEL, SECTION=GENERAL",
                  f"{area:.6e}, {inertia:.6e}, 0.0, {inertia:.6e}, {kappa:.6f}", "1.0, 0.0, 0.0"]
    na, nb = node_at(za), node_at(zb)
    lines += ["*BOUNDARY", f"{na}, 1, 3, 0.0", f"{na}, 6, 6, 0.0", f"{nb}, 1, 2, 0.0"]
    lines += ["*STEP", "*STATIC", "*CLOAD"]
    for p in case.loads:
        n = node_at(p.z)
        # 轴向力偏距 (x0, y0) 产生的力矩 M = r × F = (y0·Fz, −x0·Fz, 0)
        for dof, val in ((1, p.fx), (2, p.fy), (3, p.fz), (4, p.y0 * p.fz / MM), (5, -p.x0 * p.fz / MM)):
            if abs(val) > 1e-12:
                lines.append(f"{n}, {dof}, {val:.6e}")
    lines += ["*NODE PRINT, NSET=NALL", "U", "*END STEP", ""]
    path.write_text("\n".join(lines), encoding="ascii")
    return nodes


def read_displacements(dat: Path) -> dict[int, tuple[float, ...]]:
    """读 .dat 中的节点位移（mm）和转角（rad，梁单元才有）。"""
    out = {}
    on = False
    for line in dat.read_text(errors="replace").splitlines():
        if line.strip().startswith("displacements"):
            on = True
            continue
        if on:
            parts = line.split()
            if len(parts) in (4, 7):  # 节点号 + 3 个位移（+ 3 个转角）
                try:
                    out[int(parts[0])] = tuple(float(v) for v in parts[1:])  # type: ignore[assignment]
                except ValueError:
                    pass
    return out


def solve(segments: list[Segment], case: ShaftLoadCase, workdir: Path, name: str = "shaft", E: float = E_STEEL) -> BeamResult:
    workdir.mkdir(parents=True, exist_ok=True)
    inp = workdir / f"{name}.inp"
    nodes = write_inp(inp, segments, case, E)
    u = read_displacements(ccx.run(inp))
    order = sorted(range(len(nodes)), key=lambda i: nodes[i])
    col = lambda j, f=1.0: [u[i + 1][j] * f for i in order]  # noqa: E731
    return BeamResult([nodes[i] for i in order], col(0, MM), col(1, MM), col(3), col(4))

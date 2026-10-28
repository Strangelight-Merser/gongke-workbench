"""轴的疲劳强度精确校核（安全系数法）。

按濮良贵《机械设计》（第八版）第 15 章"按疲劳强度条件进行精确校核"：

    Sσ = σ−1 / (Kσ σa + ψσ σm)，Sτ = τ−1 / (Kτ τa + ψτ τm)，
    Sca = Sσ Sτ / √(Sσ² + Sτ²) ≥ S

弯曲应力按对称循环（σa = M/W，σm = 0），单向转动的扭转切应力按脉动循环（τa = τm = T / 2WT）。
综合影响系数 Kσ = kσ/εσ + 1/βσ − 1（未作表面强化处理，βq = 1）。

教材中 kσ、εσ、βσ 都要查图表，这里用公开的解析拟合代替，计算结果与查表值接近，说明书中注明"近似"：
- 轴肩圆角的理论应力集中系数 ασ、ατ：Peterson 阶梯圆轴的曲线拟合（Pilkey《Peterson's Stress
  Concentration Factors》第 3 章）；
- 敏感系数 q：Kuhn–Hardrath 公式 q = 1/(1 + √a/√r)，Neuber 常数取 Shigley《机械工程设计》中对钢的拟合；
  有效应力集中系数 k = 1 + q(α − 1)；
- 键槽（端铣）：α 取 Shigley 表 7-1 的 2.14（弯曲）、3.0（扭转），再按 q 折算；
- 尺寸系数 ε 与表面质量系数 β：Shigley 的 kb、ka 公式（配合表面按磨削，其余按车削）。
过盈配合处的应力集中只能查表，程序默认不计；在任务书 shaft: k_sigma_fit 中填入教材附表查得的 kσ/εσ 后一并校核。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from gongke_core.calc.shaft import Segment, ShaftLoadCase, bending_moments, torque_at

MPA = 1e6


@dataclass(frozen=True)
class ShaftMaterial:
    name: str
    sigma_b: float  # 抗拉强度
    sigma_m1: float  # 弯曲疲劳极限 σ−1
    tau_m1: float  # 剪切疲劳极限 τ−1
    psi_sigma: float  # 等效系数 ψσ
    psi_tau: float


# 濮良贵《机械设计》第八版 表 15-1（调质，毛坯直径 ≤ 200 mm）；ψ 取 §3 中碳钢、合金钢的推荐值
MATERIALS = {
    "45": ShaftMaterial("45 钢调质", 640 * MPA, 275 * MPA, 155 * MPA, 0.1, 0.05),
    "40Cr": ShaftMaterial("40Cr 调质", 735 * MPA, 355 * MPA, 200 * MPA, 0.2, 0.1),
}


# ---------------------------------------------------------------- 应力集中、尺寸、表面

def kt_shoulder_bending(D: float, d: float, r: float) -> float:
    """阶梯圆轴轴肩圆角处弯曲的理论应力集中系数（Peterson 拟合，0.1 ≤ t/r ≤ 20）。"""
    t = (D - d) / 2
    if t <= 0:
        return 1.0
    x = min(max(t / r, 0.1), 20.0)
    s = math.sqrt(x)
    if x <= 2.0:
        c = (0.947 + 1.206 * s - 0.131 * x, 0.022 - 3.405 * s + 0.915 * x,
             0.869 + 1.777 * s - 0.555 * x, -0.810 + 0.422 * s - 0.260 * x)
    else:
        c = (1.232 + 0.832 * s - 0.008 * x, -3.813 + 0.968 * s - 0.260 * x,
             7.423 - 4.868 * s + 0.869 * x, -3.839 + 3.070 * s - 0.600 * x)
    u = 2 * t / D
    return max(1.0, c[0] + c[1] * u + c[2] * u**2 + c[3] * u**3)


def kt_shoulder_torsion(D: float, d: float, r: float) -> float:
    """阶梯圆轴轴肩圆角处扭转的理论应力集中系数（Peterson 拟合，0.25 ≤ t/r ≤ 4，超出时取边界值）。"""
    t = (D - d) / 2
    if t <= 0:
        return 1.0
    x = min(max(t / r, 0.25), 4.0)
    s = math.sqrt(x)
    c = (0.905 + 0.783 * s - 0.075 * x, -0.437 - 1.969 * s + 0.553 * x,
         1.557 + 1.073 * s - 0.578 * x, -1.061 + 0.171 * s + 0.086 * x)
    u = 2 * t / D
    return max(1.0, c[0] + c[1] * u + c[2] * u**2 + c[3] * u**3)


KT_KEYWAY = (2.14, 3.0)  # 端铣键槽，r/d ≈ 0.02（Shigley 表 7-1）


def notch_sensitivity(sigma_b: float, r: float, torsion: bool = False) -> float:
    """敏感系数 q = 1/(1 + √a/√r)，√a 为 Neuber 常数（Shigley 对钢的拟合，扭转时 Sut 加 20 kpsi）。"""
    sut = sigma_b / 6.894757e6 + (20 if torsion else 0)  # kpsi
    sqrt_a = 0.246 - 3.08e-3 * sut + 1.51e-5 * sut**2 - 2.67e-8 * sut**3  # √in
    r_in = r / 0.0254
    return 1 / (1 + sqrt_a / math.sqrt(r_in))


def size_factor(d: float) -> float:
    """尺寸系数 ε（Shigley kb：d ≤ 51 mm 时 1.24 d^−0.107，51～254 mm 时 1.51 d^−0.157）。"""
    dm = d * 1e3
    if dm <= 51:
        return min(1.0, 1.24 * max(dm, 2.79) ** -0.107)
    return 1.51 * min(dm, 254) ** -0.157


def surface_factor(sigma_b: float, ground: bool) -> float:
    """表面质量系数 β（Shigley ka = a·Sut^b，Sut 用 MPa；磨削 a=1.58, b=−0.085，车削 a=4.51, b=−0.265）。"""
    sut = sigma_b / MPA
    a, b = (1.58, -0.085) if ground else (4.51, -0.265)
    return min(1.0, a * sut**b)


# ---------------------------------------------------------------- 校核

@dataclass
class FatigueSection:
    label: str  # 截面位置说明
    z: float
    d: float
    feature: str  # 轴肩圆角 / 键槽
    m: float
    t: float
    k_sigma: float  # 有效应力集中系数
    k_tau: float
    eps: float
    beta: float
    K_sigma: float  # 综合影响系数
    K_tau: float
    sigma_a: float
    tau_a: float
    S_sigma: float
    S_tau: float
    S_ca: float
    r: float = 0.0  # 圆角半径


@dataclass
class FatigueCheck:
    material: ShaftMaterial
    S_required: float
    sections: list[FatigueSection] = field(default_factory=list)
    unsupported_sections: list[dict] = field(default_factory=list)

    @property
    def critical(self) -> FatigueSection | None:
        return min(self.sections, key=lambda s: s.S_ca) if self.sections else None

    @property
    def ok(self) -> bool:
        return not self.unsupported_sections and (self.critical is None or self.critical.S_ca >= self.S_required)


def fillet_radius(small: Segment, large: Segment) -> float:
    """轴肩圆角半径：靠轴承的轴肩取 1 mm（须小于轴承内圈倒角），其余约 0.04d，取 1～2.5 mm。"""
    if "轴承" in (small.role, large.role):
        return 1.0e-3
    r = round(0.04 * small.d * 1e3 * 2) / 2
    return min(max(r, 1.0), 2.5) * 1e-3


def _section(label, z, d, feature, m, t, kt_b, kt_t, r, keyway, mat: ShaftMaterial, ground: bool,
             fit_k: float | None = None) -> FatigueSection:
    eps = size_factor(d)
    beta = surface_factor(mat.sigma_b, ground)
    if fit_k is not None:
        # 过盈配合：kσ/εσ 由教材附表查得（任务书给出），kτ/ετ = 0.8 kσ/εσ
        k_s, k_t = fit_k * eps, 0.8 * fit_k * eps
    else:
        if feature == "键槽":
            r = 0.02 * d
        q_b = notch_sensitivity(mat.sigma_b, r)
        q_t = notch_sensitivity(mat.sigma_b, r, torsion=True)
        k_s = 1 + q_b * (kt_b - 1)
        k_t = 1 + q_t * (kt_t - 1)
    K_s = k_s / eps + 1 / beta - 1
    K_t = k_t / eps + 1 / beta - 1
    if m < 1e-6 * max(abs(t), 1.0):
        m = 0.0
    W = math.pi * d**3 / 32
    WT = math.pi * d**3 / 16
    if keyway:
        b, t1, _ = keyway
        cut = b * t1 * (d - t1) ** 2 / (2 * d)
        W -= cut
        WT -= cut
    sa = m / W
    ta = tm = abs(t) / (2 * WT)
    S_s = mat.sigma_m1 / (K_s * sa) if sa > 0 else math.inf
    S_t = mat.tau_m1 / (K_t * ta + mat.psi_tau * tm) if ta > 0 else math.inf
    if math.isinf(S_s) and math.isinf(S_t):
        S = math.inf
    elif math.isinf(S_s):
        S = S_t
    elif math.isinf(S_t):
        S = S_s
    else:
        S = S_s * S_t / math.hypot(S_s, S_t)
    return FatigueSection(label, z, d, feature, m, t, k_s, k_t, eps, beta, K_s, K_t, sa, ta, S_s, S_t, S, r)


def check(segments: list[Segment], case: ShaftLoadCase, material: ShaftMaterial,
          S_required: float = 1.5, fit_k: float | None = None, *,
          shoulder_radii: dict[int, float] | None = None) -> FatigueCheck:
    """在每个轴肩（直径变化处，取小直径一侧）和每个键槽处计算安全系数。

    fit_k 为齿轮过盈配合（H7/r6）处的 kσ/εσ（教材附表查得）；给出时再校核齿轮轮毂两端截面。
    shoulder_radii 给出当前轴肩实际圆角，键为相邻右段的索引（1..n−1）、值为 m。
    显式圆角必须完整；超出当前拟合标注范围的截面只记录缺口，不用夹紧值计算。
    未传入时仍采用批处理设计的角色推定圆角，调用者不得将该近似当作实形校核。
    """
    out = FatigueCheck(material, S_required)
    fits = {"轴承", "齿轮", "端部", "密封"}

    def loads(z):
        mx, my = bending_moments(case, z)
        return math.hypot(mx, my), torque_at(case, z)

    def within_bounds(value, lower, upper):
        # 仅容纳 SI 换算和相减产生的舍入误差，不修改原始 t/r，也不扩大工程适用范围。
        return (lower <= value <= upper
                or math.isclose(value, lower, rel_tol=1e-12, abs_tol=1e-14)
                or math.isclose(value, upper, rel_tol=1e-12, abs_tol=1e-14))

    eps = 1e-6
    for index, (a, b) in enumerate(zip(segments, segments[1:]), 1):
        da, db = a.root_d or a.d, b.root_d or b.d
        if abs(da - db) < 1e-6:
            continue
        if shoulder_radii is not None:
            r = shoulder_radii.get(index)
            if isinstance(r, bool) or not isinstance(r, (int, float)) or not math.isfinite(r) or r <= 0:
                raise ValueError(f"轴肩 {index} 缺少有限正数的实际圆角半径")
        small, large = (a, b) if da < db else (b, a)
        z = b.z0 - eps if small is a else b.z0 + eps
        m, t = loads(z)
        if m <= 0 and t == 0:
            continue
        D, d = max(da, db), min(da, db)
        if shoulder_radii is None:
            r = fillet_radius(small, large)
        label = f"{small.role}段与{large.role}段之间的轴肩"
        if shoulder_radii is not None:
            ratio = (D - d) / (2 * r)
            unsupported = []
            if m > 0 and not within_bounds(ratio, 0.1, 20.0):
                unsupported.append("弯曲拟合要求 0.1 ≤ t/r ≤ 20")
            if t != 0 and not within_bounds(ratio, 0.25, 4.0):
                unsupported.append("扭转拟合要求 0.25 ≤ t/r ≤ 4")
            if unsupported:
                out.unsupported_sections.append({"label": label, "z": b.z0, "d": d, "r": r,
                                                 "right_segment_index": index, "t_over_r": ratio,
                                                 "status": "blocked", "reason": "；".join(unsupported)})
                continue
        out.sections.append(_section(label, b.z0, d, "轴肩圆角", m, t, kt_shoulder_bending(D, d, r),
                                     kt_shoulder_torsion(D, d, r), r, None, material, small.role in fits))
    for s in segments:
        if not s.keyway:
            continue
        kl = s.keyway[2]
        zm = (s.z0 + s.z1) / 2
        best = max((loads(zm - kl / 2 + kl * k / 20) + (zm - kl / 2 + kl * k / 20,) for k in range(21)),
                   key=lambda v: v[0])
        m, t, z = best
        if t == 0:
            t = max(abs(torque_at(case, zm - kl / 2)), abs(torque_at(case, zm + kl / 2)))
        if m <= 0 and t == 0:
            continue
        out.sections.append(_section(f"{s.role}段键槽", z, s.d, "键槽", m, t, KT_KEYWAY[0], KT_KEYWAY[1],
                                     0.0, s.keyway, material, s.role in fits))
    if fit_k:
        for s in segments:
            if s.role != "齿轮":
                continue
            for z in (s.z0 + eps, s.z1 - eps):
                m, t = loads(z)
                if m <= 0 and t == 0:
                    continue
                out.sections.append(_section("齿轮轮毂端（过盈配合）", z, s.d, "过盈配合", m, t, 1, 1, 0.0,
                                             None, material, True, fit_k))
    return out

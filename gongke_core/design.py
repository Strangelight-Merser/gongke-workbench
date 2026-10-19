"""减速器设计总流程：从设计任务书到全部计算结果和结构尺寸。"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from gongke_core import standards
from gongke_core.calc import bearing as bearing_calc
from gongke_core.calc import fatigue as fatigue_calc
from gongke_core.calc import gear as gear_calc
from gongke_core.calc import key as key_calc
from gongke_core.calc import kinematics
from gongke_core.calc import shaft as shaft_calc
from gongke_core.calc import vbelt as vbelt_calc
from gongke_core.layout import reducer as lay

MM = 1e-3


# ---------------------------------------------------------------- 任务书


@dataclass
class ReducerTask:
    title: str
    conveyor: kinematics.ConveyorTask
    bearing_life_hours: float
    high: dict = field(default_factory=dict)  # 传给 GearPairInput 的附加参数
    low: dict = field(default_factory=dict)
    shaft_material: str = "45 钢 调质"
    shaft_sigma_allow: float = 60e6  # [σ−1b]
    key_sigma_allow: float = 110e6
    load_factor_bearing: float = 1.1
    coupling_service_factor: float = 1.5
    shaft_S_required: float = 1.5  # 疲劳强度许用安全系数 [S]
    shaft_fit_k: float | None = None  # 齿轮过盈配合处 kσ/εσ（教材附表查得，未给出时不校核该截面）
    belt: dict = field(default_factory=dict)  # V 带方案的附加参数（section、dd1_mm、a0_mm、KA）
    hours_per_day: float = 16

    @property
    def scheme(self) -> str:
        return self.conveyor.scheme

    @classmethod
    def from_dict(cls, d: dict) -> "ReducerTask":
        c = d["conveyor"]
        life = d.get("life", {})
        hours_per_year = life.get("days_per_year", 300) * life.get("shifts", 2) * 8
        conveyor = kinematics.ConveyorTask(
            belt_pull=float(c["belt_pull_N"]),
            belt_speed=float(c["belt_speed_m_s"]),
            drum_diameter=float(c["drum_diameter_mm"]) * MM,
            life_hours=life.get("years", 10) * hours_per_year,
            sync_speed_rpm=float(d.get("motor_sync_speed_rpm", 1500)),
            ratio_split=float(d.get("ratio_split", 1.3)),
            scheme=str(d.get("scheme", "coupling")),
            belt_ratio=float((d.get("vbelt") or {}).get("ratio", 2.5)),
        )
        if conveyor.scheme not in ("coupling", "vbelt", "bevel"):
            raise ValueError(f"未知的传动方案 scheme: {conveyor.scheme}（可选 coupling、vbelt、bevel）")
        gears = d.get("gears", {})
        shaft = d.get("shaft", {}) or {}
        return cls(
            title=d.get("title", "带式输送机传动装置设计"),
            conveyor=conveyor,
            bearing_life_hours=d.get("bearing_life_years", 3) * hours_per_year,
            high=dict(gears.get("high", {})),
            low=dict(gears.get("low", {})),
            shaft_S_required=float(shaft.get("S_required", 1.5)),
            shaft_fit_k=float(shaft["k_sigma_fit"]) if shaft.get("k_sigma_fit") else None,
            belt=dict(d.get("vbelt") or {}),
            hours_per_day=life.get("shifts", 2) * 8,
        )

    @classmethod
    def from_yaml(cls, path: str | Path) -> "ReducerTask":
        with open(path, encoding="utf-8") as f:
            return cls.from_dict(yaml.safe_load(f))


# ---------------------------------------------------------------- 结果


@dataclass
class ShaftResult:
    layout: lay.ShaftLayout
    load_case: shaft_calc.ShaftLoadCase
    strength: shaft_calc.ShaftCheck
    bearings: bearing_calc.BearingCheck
    keys: list[key_calc.KeyCheck]
    fatigue: fatigue_calc.FatigueCheck
    power: float
    speed_rpm: float
    torque: float

    @property
    def ok(self) -> bool:
        return self.strength.ok and self.bearings.ok and all(k.ok for k in self.keys) and self.fatigue.ok


@dataclass
class Coupling:
    location: str
    torque: float  # 计算转矩 Tca = KA T
    bores: tuple[float, float]  # 两侧轴孔直径
    hub_length: float


@dataclass
class ReducerDesign:
    task: ReducerTask
    kin: kinematics.Kinematics
    high: gear_calc.GearPair
    low: gear_calc.GearPair
    housing: lay.Housing
    shafts: list[ShaftResult]
    couplings: list[Coupling]
    checks: list[tuple[str, bool, str]]  # (项目, 是否满足, 说明)
    warnings: list[str]
    belt: vbelt_calc.BeltDrive | None = None

    @property
    def actual_ratio(self) -> float:
        return (self.belt.ratio if self.belt else 1.0) * self.high.u * self.low.u

    @property
    def output_speed_error(self) -> float:
        n_out = self.kin.motor.speed_rpm / self.actual_ratio
        return (n_out - self.kin.drum_speed_rpm) / self.kin.drum_speed_rpm

    @property
    def ok(self) -> bool:
        return all(ok for _, ok, _ in self.checks)


# ---------------------------------------------------------------- 受力


def gear_loads(pair: gear_calc.GearPair, member: int, z: float) -> shaft_calc.PointLoad:
    """啮合力。Ⅰ轴逆时针（沿 +z 看）转动，高速级小齿轮轴向力取 +z，其余按啮合关系和
    中间轴轴向力相互抵消的要求确定方向（见 docs/architecture.md 受力约定）。
    """
    ft, fr, fa = pair.tangential_force, pair.radial_force, pair.axial_force
    high = pair.inp.name.startswith("高速")
    if high and member == 1:  # Ⅰ轴小齿轮，主动，啮合点在 +x 侧
        return shaft_calc.PointLoad(z, fx=-fr, fy=-ft, fz=+fa, x0=+pair.d1 / 2, label="高速级小齿轮")
    if high and member == 2:  # Ⅱ轴大齿轮，从动，啮合点在 −x 侧
        return shaft_calc.PointLoad(z, fx=+fr, fy=+ft, fz=-fa, x0=-pair.d2 / 2, label="高速级大齿轮")
    if member == 1:  # Ⅱ轴小齿轮，主动，啮合点在 +x 侧
        return shaft_calc.PointLoad(z, fx=-fr, fy=+ft, fz=+fa, x0=+pair.d1 / 2, label="低速级小齿轮")
    return shaft_calc.PointLoad(z, fx=+fr, fy=-ft, fz=-fa, x0=-pair.d2 / 2, label="低速级大齿轮")


# ---------------------------------------------------------------- 主流程


def _end_failed(strength: shaft_calc.ShaftCheck, fat: fatigue_calc.FatigueCheck) -> bool:
    """强度不足的截面在轴伸（端部或密封段）上：只加大轴承处直径没有用，需要加大轴伸直径。"""
    if not strength.ok and strength.critical.role in ("端部", "密封"):
        return True
    c = fat.critical
    return (not fat.ok) and c is not None and c.label.startswith(("端部", "密封"))


def pulley_hub_length(d: float, rim_width: float) -> float:
    """带轮轮毂长度 L = (1.5～2)d，且不小于轮缘宽度 B（轮缘不悬出轮毂，免得碰到轴承盖）。"""
    return lay.ceil_to(max(1.5 * d, rim_width), MM)


def _shaft(idx: int, task: ReducerTask, kin: kinematics.Kinematics, h: lay.Housing,
           high: gear_calc.GearPair, low: gear_calc.GearPair, z_high: float, z_low: float,
           belt: vbelt_calc.BeltDrive | None = None) -> ShaftResult:
    st = kin.shafts[idx]
    d_min = shaft_calc.min_diameter(st.power, st.speed_rpm)
    name = st.name
    ext = {1: "left", 2: None, 3: "right"}[idx]
    on_belt = idx == 1 and belt is not None
    if idx == 1 and not on_belt:
        d_end0 = lay.std_diameter(max(1.05 * d_min, 0.8 * kin.motor.shaft_d))
    elif idx in (1, 3):
        d_end0 = lay.std_diameter(1.05 * d_min)
    else:
        d_end0 = None

    gear_specs = {
        1: [(high, 1, z_high)],
        2: [(low, 1, z_low), (high, 2, z_high)],
        3: [(low, 2, z_low)],
    }[idx]

    last = None
    d_end = d_end0
    for _ in range(8):
        d_seal = lay.std_diameter(1.14 * d_end) if d_end else None
        d_b0 = lay.ceil_to((d_seal + 1 * MM) if d_seal else max(1.05 * d_min, 20 * MM), 5 * MM)
        if on_belt:
            hub = pulley_hub_length(d_end, belt.width)
        else:
            hub = lay.coupling_hub_length(d_end) if d_end else None
        end_failed = False
        for step in range(8):
            d_b = d_b0 + step * 5 * MM
            for brg in standards.bearings_with_bore(d_b):
                dia = lay.diameters(d_b, brg.D, d_end, d_seal)
                gears = []
                for pair, member, z in gear_specs:
                    width = pair.b1 if member == 1 else pair.b2
                    df = pair.df1 if member == 1 else pair.df2
                    da = pair.da1 if member == 1 else pair.da2
                    integral = member == 1 and lay.gear_shaft_needed(df, dia.seat, pair.mn)
                    mount = "left" if (len(gear_specs) == 2 and z == min(g[2] for g in gear_specs)) or (
                        len(gear_specs) == 1 and z < h.inner_width / 2) else "right"
                    gears.append(lay.GearOnShaft("high" if pair is high else "low", member, z, width,
                                                 integral, None if integral else dia.seat, mount, df, da))
                segs = lay.build_segments(h, brg, dia, gears, ext, hub)
                za = -h.gap_bearing - brg.B / 2
                zb = h.inner_width + h.gap_bearing + brg.B / 2
                loads = [gear_loads(pair, member, z) for pair, member, z in gear_specs]
                z_ext = lay.shaft_extension_z(segs)
                if on_belt:
                    # 压轴力沿两带轮中心连线指向电动机（电动机放在Ⅰ轴外侧，带近似水平）
                    loads.append(shaft_calc.PointLoad(z_ext, fx=-belt.fp, label="带轮压轴力"))
                if idx == 1:
                    tp = [(z_ext, st.torque), (z_high, -st.torque)]
                elif idx == 2:
                    tp = [(z_high, st.torque), (z_low, -st.torque)]
                else:
                    tp = [(z_low, st.torque), (z_ext, -st.torque)]
                case = shaft_calc.ShaftLoadCase((za, zb), loads, tp)

                # 键
                keys = []
                for g in gears:
                    if not g.integral:
                        seg = next(s for s in segs if s.role == "齿轮" and s.z0 <= g.z <= s.z1)
                        kc = key_calc.select(f"{name}齿轮处", st.torque, g.seat_d, g.width, task.key_sigma_allow)
                        seg.keyway = (kc.size.b, kc.size.t1, kc.length)
                        keys.append(kc)
                if d_end:
                    seg = next(s for s in segs if s.role == "端部")
                    where = "带轮处" if on_belt else "联轴器处"
                    kc = key_calc.select(f"{name}{where}", st.torque, d_end, hub, task.key_sigma_allow)
                    seg.keyway = (kc.size.b, kc.size.t1, kc.length)
                    keys.append(kc)

                strength = shaft_calc.check(segs, case, task.shaft_sigma_allow)
                r = strength.reactions
                bc = bearing_calc.check_pair(brg, r.radial_a, r.radial_b, r.axial, st.speed_rpm,
                                             task.bearing_life_hours, task.load_factor_bearing)
                sl = lay.ShaftLayout(idx, name, [0.0, high.a, high.a + low.a][idx - 1], d_min, brg, (za, zb),
                                     gears, segs, ext, hub,
                                     {"端部": d_end, "密封": d_seal, "轴承": d_b, "齿轮": dia.seat,
                                      "轴环": dia.collar, "轴肩": dia.shoulder})
                integral = any(g.integral for g in gears)
                mat_key = (high.inp.material1 if idx == 1 else low.inp.material1).split("_")[0] if integral else "45"
                fat = fatigue_calc.check(segs, case, fatigue_calc.MATERIALS.get(mat_key, fatigue_calc.MATERIALS["45"]),
                                         task.shaft_S_required, task.shaft_fit_k)
                last = ShaftResult(sl, case, strength, bc, keys, fat, st.power, st.speed_rpm, st.torque)
                if strength.ok and bc.ok and fat.ok:
                    return last
                if d_end and _end_failed(strength, fat):
                    end_failed = True
                    break
                if not strength.ok or not fat.ok:
                    break  # 轴的强度不够，直接加大轴径
            if end_failed:
                break
        if not end_failed:
            break
        d_end = lay.std_diameter(d_end + 1 * MM)
    if last is None:
        raise standards.SelectionError(f"{name}：轴承内径 {d_b0 / MM:.0f} mm 以上没有可选的深沟球轴承（超出本程序的数据范围）")
    return last


def _belt(task: ReducerTask, kin: kinematics.Kinematics) -> vbelt_calc.BeltDrive:
    b = task.belt
    ka = float(b.get("KA") or vbelt_calc.service_factor(task.hours_per_day))
    return vbelt_calc.design(vbelt_calc.BeltInput(
        kin.required_power, kin.motor.speed_rpm, task.conveyor.belt_ratio, ka, kin.motor.shaft_d,
        b.get("section"), b["dd1_mm"] * MM if b.get("dd1_mm") else None, b["a0_mm"] * MM if b.get("a0_mm") else None))


def run(task: ReducerTask) -> ReducerDesign:
    if task.scheme == "bevel":
        from gongke_core import bevel_design

        return bevel_design.run(task)
    kin = kinematics.solve(task.conveyor)
    t = task.conveyor
    belt = None
    if task.scheme == "vbelt":
        belt = _belt(task, kin)
        kin = kinematics.solve(task.conveyor, belt.ratio)  # 按圆整后带轮直径的实际传动比重新分配
    high = gear_calc.design(gear_calc.GearPairInput(
        "高速级", kin.shafts[1].torque, kin.shafts[1].speed_rpm, kin.i_high, t.life_hours, **task.high))
    # 低速级齿数比按总传动比修正，抵消高速级齿数圆整的误差
    u_low = kin.reducer_ratio / high.u
    low = gear_calc.design(gear_calc.GearPairInput(
        "低速级", kin.shafts[2].torque, kin.shafts[2].speed_rpm, u_low, t.life_hours, **task.low))
    h = lay.housing(high, low)
    z_low = h.gap_axial + low.b1 / 2
    z_high = h.gap_axial + low.b1 + h.gap_gears + high.b1 / 2
    shafts = [_shaft(i, task, kin, h, high, low, z_high, z_low, belt) for i in (1, 2, 3)]

    couplings = [] if belt else [
        Coupling("电动机—Ⅰ轴", task.coupling_service_factor * kin.shafts[1].torque,
                 (kin.motor.shaft_d, shafts[0].layout.diameters["端部"]), shafts[0].layout.coupling_hub)]
    couplings += [
        Coupling("Ⅲ轴—卷筒轴", task.coupling_service_factor * kin.shafts[3].torque,
                 (shafts[2].layout.diameters["端部"], shafts[2].layout.diameters["端部"]), shafts[2].layout.coupling_hub),
    ]

    checks: list[tuple[str, bool, str]] = []
    warnings: list[str] = []
    err = (kin.motor.speed_rpm / (kin.i_belt * high.u * low.u) - kin.drum_speed_rpm) / kin.drum_speed_rpm
    checks.append(("输送带速度误差", abs(err) <= 0.05, f"{err*100:+.2f}%，允许 ±5%"))
    if belt:
        checks.append(("V 带带速", 5 <= belt.v <= 25, f"v = {belt.v:.2f} m/s，应在 5～25 m/s"))
        checks.append(("小带轮包角", belt.alpha1 >= 120, f"α1 = {belt.alpha1:.1f}° ≥ 120°"))
        checks.append(("V 带根数", belt.z <= 5, f"z = {belt.z} ≤ 5"))
    for p in (high, low):
        c = p.check
        checks.append((f"{p.inp.name}齿面接触疲劳强度", c.sigma_h <= c.sigma_h_allow,
                       f"σH = {c.sigma_h/1e6:.1f} MPa ≤ [σH] = {c.sigma_h_allow/1e6:.1f} MPa"))
        for i in (0, 1):
            checks.append((f"{p.inp.name}{'小' if i == 0 else '大'}齿轮齿根弯曲疲劳强度",
                           c.sigma_f[i] <= c.sigma_f_allow[i],
                           f"σF = {c.sigma_f[i]/1e6:.1f} MPa ≤ [σF] = {c.sigma_f_allow[i]/1e6:.1f} MPa"))
    for s in shafts:
        sc = s.strength
        checks.append((f"{s.layout.name}弯扭合成强度", sc.ok,
                       f"σca = {sc.critical.sigma_ca/1e6:.1f} MPa ≤ [σ−1b] = {sc.sigma_allow/1e6:.0f} MPa"))
        fc = s.fatigue
        if fc.critical is not None:
            c = fc.critical
            checks.append((f"{s.layout.name}疲劳强度安全系数", fc.ok,
                           f"Sca = {c.S_ca:.2f} ≥ [S] = {fc.S_required:g}（{c.label}，近似）"))
        b = s.bearings
        checks.append((f"{s.layout.name}轴承 {b.bearing.designation} 寿命", b.ok,
                       f"L10h = {min(b.life):.0f} h ≥ {b.required:.0f} h"))
        for k in s.keys:
            checks.append((f"{k.location}平键挤压强度", k.ok,
                           f"σp = {k.sigma_p/1e6:.1f} MPa ≤ [σp] = {k.sigma_allow/1e6:.0f} MPa"
                           + ("（双键）" if k.count == 2 else "")))
    # 高速级大齿轮不得碰到低速轴
    d3_max = max(seg.d for seg in shafts[2].layout.segments
                 if seg.z0 <= z_high + high.b2 / 2 and seg.z1 >= z_high - high.b2 / 2)
    gap = low.a - high.da2 / 2 - d3_max / 2
    checks.append(("高速级大齿轮与低速轴间隙", gap >= 10 * MM, f"{gap/MM:.1f} mm ≥ 10 mm"))
    # 浸油润滑：高速级大齿轮浸油约一个齿高，低速级大齿轮浸油不超过其半径的 1/3
    dip = low.da2 / 2 - high.da2 / 2 + 2.25 * high.mn
    dip_ok = dip <= low.da2 / 2 / 3
    checks.append(("浸油润滑深度", dip_ok, f"低速级大齿轮浸油 {dip/MM:.0f} mm ≤ R/3 = {low.da2/6/MM:.0f} mm"))
    if not dip_ok:
        warnings.append("两级大齿轮直径相差较大，可适当增大高速级传动比分配系数（ratio_split）或改用带油轮润滑。")
    for p in (high, low):
        if p.check.k_v and any(k in p.inp.overrides for k in ("k_v", "k_hn1", "k_fn1")):
            warnings.append(f"{p.inp.name}使用了手工覆盖的系数：{p.inp.overrides}")
    warnings.append("Kv、KHN、KFN 采用解析近似代替教材查图，正式提交前可在任务书 overrides 中填入教材查得的值。")
    if belt:
        warnings.append("V 带的 P0、KL 数据待人工核对；带型按 z ≤ 4 自动试选，也可在任务书 vbelt 中指定 section、dd1_mm。")
    warnings.append("联轴器只给出计算转矩和轴孔直径，型号请按 GB/T 5014（LX 型弹性柱销联轴器）核对。")
    d = ReducerDesign(task, kin, high, low, h, shafts, couplings, checks, warnings, belt)
    if belt:
        from gongke_core.layout import housing_detail
        H = -housing_detail.detail(d).y_bottom
        checks.append(("大带轮尺寸", belt.dd2 / 2 < H,
                       f"大带轮半径 {belt.dd2 / 2 / MM:.0f} mm < 减速器中心高 H = {H / MM:.0f} mm（否则会碰到地基）"))
    return d

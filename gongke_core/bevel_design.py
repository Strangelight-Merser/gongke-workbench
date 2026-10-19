"""圆锥-圆柱齿轮减速器（任务书 scheme: bevel）的设计总流程。

电动机 → 联轴器 → 直齿锥齿轮（高速级）→ 斜齿圆柱齿轮（低速级）→ 联轴器 → 卷筒。
结构布置见 `layout/bevel_reducer.py`；Ⅲ轴与展开式减速器的低速轴相同，直接复用 `design._shaft`。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from types import SimpleNamespace

from gongke_core import standards
from gongke_core.calc import bearing as bearing_calc
from gongke_core.calc import bevel as bevel_calc
from gongke_core.calc import fatigue as fatigue_calc
from gongke_core.calc import gear as gear_calc
from gongke_core.calc import key as key_calc
from gongke_core.calc import kinematics
from gongke_core.calc import shaft as shaft_calc
from gongke_core.design import Coupling, ReducerTask, ShaftResult, _end_failed, _shaft, gear_loads
from gongke_core.layout import bevel_reducer as blay
from gongke_core.layout import reducer as lay

MM = 1e-3


@dataclass
class BevelReducerDesign:
    task: ReducerTask
    kin: kinematics.Kinematics
    bevel: bevel_calc.BevelPair
    low: gear_calc.GearPair
    housing: lay.Housing
    positions: blay.BevelPositions
    pinion: blay.PinionShaft
    shafts: list[ShaftResult]
    couplings: list[Coupling]
    checks: list[tuple[str, bool, str]]
    warnings: list[str]
    belt: None = None

    @property
    def high(self) -> bevel_calc.BevelPair:
        return self.bevel

    @property
    def actual_ratio(self) -> float:
        return self.bevel.u * self.low.u

    @property
    def output_speed_error(self) -> float:
        n_out = self.kin.motor.speed_rpm / self.actual_ratio
        return (n_out - self.kin.drum_speed_rpm) / self.kin.drum_speed_rpm

    @property
    def ok(self) -> bool:
        return all(ok for _, ok, _ in self.checks)


def _mat(code: str) -> fatigue_calc.ShaftMaterial:
    return fatigue_calc.MATERIALS.get(code.split("_")[0], fatigue_calc.MATERIALS["45"])


def _pinion_shaft(task: ReducerTask, kin: kinematics.Kinematics, h: lay.Housing,
                  bevel: bevel_calc.BevelPair) -> tuple[ShaftResult, blay.PinionShaft]:
    """Ⅰ轴：悬臂小锥齿轮，一对圆锥滚子轴承反装。局部坐标：z 为自锥顶向外的 u，x 对应总体 z，y 不变。"""
    st = kin.shafts[1]
    d_min = shaft_calc.min_diameter(st.power, st.speed_rpm)
    d_end = lay.std_diameter(max(1.05 * d_min, 0.8 * kin.motor.shaft_d))
    last = None
    for _ in range(6):
        d_seal = lay.std_diameter(1.14 * d_end)
        hub = lay.coupling_hub_length(d_end)
        d_b0 = lay.ceil_to(d_seal + 1 * MM, 5 * MM)
        end_failed = False
        for step in range(8):
            d_b = d_b0 + step * 5 * MM
            for brg in standards.tapered_with_bore(d_b):
                ps = blay.pinion_shaft(h, bevel, brg, d_end, d_seal, d_b, hub)
                segs = ps.segments
                # 小锥齿轮受力：啮合点在总体 −z 一侧（局部 x0 = −dm1/2），径向力指向轴线（局部 +x），
                # 轴向力指向大端（向外，局部 +z），切向力与大锥齿轮所受的相反（局部 −y）
                loads = [shaft_calc.PointLoad(ps.u_mean, fx=+bevel.radial_force1, fy=-bevel.tangential_force,
                                              fz=+bevel.axial_force1, x0=-bevel.dm1 / 2, label="小锥齿轮")]
                z_ext = lay.shaft_extension_z(segs)
                case = shaft_calc.ShaftLoadCase(ps.bearing_u, loads, [(z_ext, st.torque), (ps.u_mean, -st.torque)])
                keys = []
                if not ps.integral:
                    seg = next(s for s in segs if s.role == "齿轮")
                    kc = key_calc.select(f"{st.name}小锥齿轮处", st.torque, ps.seat_d, seg.length, task.key_sigma_allow)
                    seg.keyway = (kc.size.b, kc.size.t1, kc.length)
                    keys.append(kc)
                seg = next(s for s in segs if s.role == "端部")
                kc = key_calc.select(f"{st.name}联轴器处", st.torque, d_end, hub, task.key_sigma_allow)
                seg.keyway = (kc.size.b, kc.size.t1, kc.length)
                keys.append(kc)
                strength = shaft_calc.check(segs, case, task.shaft_sigma_allow)
                r = strength.reactions
                bc = bearing_calc.check_tapered_pair(brg, r.radial_a, r.radial_b, r.axial, st.speed_rpm,
                                                     task.bearing_life_hours, task.load_factor_bearing, "反装")
                gear = lay.GearOnShaft("bevel", 1, ps.u_mean, ps.pinion_length, ps.integral, ps.seat_d, "left",
                                       bevel.df1, bevel.da1)
                sl = lay.ShaftLayout(1, st.name, 0.0, d_min, brg, ps.bearing_u, [gear], segs, "right", hub,
                                     dict(ps.diameters))
                mat = _mat(bevel.inp.material1) if ps.integral else fatigue_calc.MATERIALS["45"]
                fat = fatigue_calc.check(segs, case, mat, task.shaft_S_required, task.shaft_fit_k)
                last = (ShaftResult(sl, case, strength, bc, keys, fat, st.power, st.speed_rpm, st.torque), ps)
                if strength.ok and bc.ok and fat.ok:
                    return last
                if _end_failed(strength, fat):
                    end_failed = True
                    break
                if not strength.ok or not fat.ok:
                    break
            if end_failed:
                break
        if not end_failed:
            break
        d_end = lay.std_diameter(d_end + 1 * MM)
    if last is None:
        raise standards.SelectionError(f"{st.name}：没有合适的圆锥滚子轴承（超出本程序的数据范围）")
    return last


def _intermediate_shaft(task: ReducerTask, kin: kinematics.Kinematics, h: lay.Housing, bevel: bevel_calc.BevelPair,
                        low: gear_calc.GearPair, pos: blay.BevelPositions, z_low: float) -> ShaftResult:
    """Ⅱ轴：大锥齿轮 + 圆柱小齿轮，一对圆锥滚子轴承正装（两端单向固定，便于调整锥齿轮啮合）。"""
    st = kin.shafts[2]
    d_min = shaft_calc.min_diameter(st.power, st.speed_rpm)
    d_b0 = lay.ceil_to(max(1.05 * d_min, 20 * MM), 5 * MM)
    last = None
    for step in range(8):
        d_b = d_b0 + step * 5 * MM
        for brg in standards.tapered_with_bore(d_b):
            dia = lay.diameters(d_b, brg.D, None, None)
            hub = pos.hub
            integral = lay.gear_shaft_needed(low.df1, dia.seat, low.mn)
            gears = [lay.GearOnShaft("bevel", 2, pos.z_back + hub / 2, hub, False, dia.seat, "left",
                                     bevel.df2, bevel.da2),
                     lay.GearOnShaft("low", 1, z_low, low.b1, integral, None if integral else dia.seat, "right",
                                     low.df1, low.da1)]
            segs = lay.build_segments(h, brg, dia, gears, None, None)
            off = brg.a - brg.T / 2  # 正装：压力中心在两轴承内侧
            za = -h.gap_bearing - brg.T / 2 + off
            zb = h.inner_width + h.gap_bearing + brg.T / 2 - off
            loads = [shaft_calc.PointLoad(pos.z_mean, fx=+bevel.axial_force1, fy=+bevel.tangential_force,
                                          fz=-bevel.radial_force1, x0=-bevel.dm2 / 2, label="大锥齿轮"),
                     gear_loads(low, 1, z_low)]
            case = shaft_calc.ShaftLoadCase((za, zb), loads, [(pos.z_mean, st.torque), (z_low, -st.torque)])
            keys = []
            for g in gears:
                if g.integral:
                    continue
                seg = next(s for s in segs if s.role == "齿轮" and s.z0 <= g.z <= s.z1)
                where = "大锥齿轮处" if g.pair == "bevel" else "齿轮处"
                kc = key_calc.select(f"{st.name}{where}", st.torque, g.seat_d, seg.length + 2 * MM, task.key_sigma_allow)
                seg.keyway = (kc.size.b, kc.size.t1, kc.length)
                keys.append(kc)
            strength = shaft_calc.check(segs, case, task.shaft_sigma_allow)
            r = strength.reactions
            bc = bearing_calc.check_tapered_pair(brg, r.radial_a, r.radial_b, r.axial, st.speed_rpm,
                                                 task.bearing_life_hours, task.load_factor_bearing, "正装")
            sl = lay.ShaftLayout(2, st.name, 0.0, d_min, brg, (za, zb), gears, segs, None, None,
                                 {"端部": None, "密封": None, "轴承": d_b, "齿轮": dia.seat,
                                  "轴环": dia.collar, "轴肩": dia.shoulder})
            mat = _mat(low.inp.material1) if integral else fatigue_calc.MATERIALS["45"]
            fat = fatigue_calc.check(segs, case, mat, task.shaft_S_required, task.shaft_fit_k)
            last = ShaftResult(sl, case, strength, bc, keys, fat, st.power, st.speed_rpm, st.torque)
            if strength.ok and bc.ok and fat.ok:
                return last
            if not strength.ok or not fat.ok:
                break
    if last is None:
        raise standards.SelectionError(f"{st.name}：没有合适的圆锥滚子轴承（超出本程序的数据范围）")
    return last


def _dip_depth(bevel: bevel_calc.BevelPair, low: gear_calc.GearPair) -> float:
    """大锥齿轮浸入 0.7 倍齿宽（径向投影 0.7b sin δ2）时，低速级大齿轮的浸油深度。"""
    return low.da2 / 2 - bevel.da2 / 2 + 0.7 * bevel.b * math.sin(bevel.delta2)


def run(task: ReducerTask) -> BevelReducerDesign:
    t = task.conveyor
    kin = kinematics.solve(t)
    i1 = kin.i_high
    # 大锥齿轮要整个齿宽浸油，低速级大齿轮又不能浸得过深：两者直径相差太多时先适当加大锥齿轮传动比
    # （不超过 4），仍不够再加大锥齿轮尺寸（强度有富余）
    min_d1 = 0.0
    while True:
        kin = kinematics.solve(t, i_high=i1)
        high = dict(task.high)
        if min_d1:
            high["min_d1"] = min_d1
        bevel = bevel_calc.design(bevel_calc.BevelPairInput(
            "高速级", kin.shafts[1].torque, kin.shafts[1].speed_rpm, i1, t.life_hours, **high))
        u_low = kin.reducer_ratio / bevel.u
        low = gear_calc.design(gear_calc.GearPairInput(
            "低速级", kin.shafts[2].torque, kin.shafts[2].speed_rpm, u_low, t.life_hours, **task.low))
        if _dip_depth(bevel, low) <= low.da2 / 6 or min_d1 > 2 * bevel.d1_trial:
            break
        if i1 < 4 - 1e-9:
            i1 = min(i1 + 0.25, 4.0)
        else:
            min_d1 = 1.05 * bevel.d1

    # 大锥齿轮轮毂长度取决于Ⅱ轴直径，先按估算的孔径定，再用实际孔径复核
    seat_guess = lay.std_diameter(max(1.05 * shaft_calc.min_diameter(kin.shafts[2].power, kin.shafts[2].speed_rpm),
                                      20 * MM) + 8 * MM)
    hub = blay.bevel_gear_hub(bevel, seat_guess)
    for _ in range(4):
        h = blay.housing(bevel, low, hub)
        pos = blay.bevel_positions(h, bevel, hub, seat_guess)
        z_low = h.gap_axial + hub + h.gap_gears + low.b1 / 2
        s2 = _intermediate_shaft(task, kin, h, bevel, low, pos, z_low)
        seat = s2.layout.diameters["齿轮"]
        hub_need = blay.bevel_gear_hub(bevel, seat)
        if hub_need <= hub + 1e-9 and seat <= seat_guess + 1e-9:
            break
        hub, seat_guess = max(hub, hub_need), seat
    s1, ps = _pinion_shaft(task, kin, h, bevel)
    s3 = _shaft(3, task, kin, h, SimpleNamespace(a=0.0), low, 0.0, z_low)
    s3.layout.x = low.a
    shafts = [s1, s2, s3]

    couplings = [
        Coupling("电动机—Ⅰ轴", task.coupling_service_factor * kin.shafts[1].torque,
                 (kin.motor.shaft_d, s1.layout.diameters["端部"]), s1.layout.coupling_hub),
        Coupling("Ⅲ轴—卷筒轴", task.coupling_service_factor * kin.shafts[3].torque,
                 (s3.layout.diameters["端部"], s3.layout.diameters["端部"]), s3.layout.coupling_hub),
    ]

    checks: list[tuple[str, bool, str]] = []
    warnings: list[str] = []
    n_out = kin.motor.speed_rpm / (bevel.u * low.u)
    err = (n_out - kin.drum_speed_rpm) / kin.drum_speed_rpm
    checks.append(("输送带速度误差", abs(err) <= 0.05, f"{err*100:+.2f}%，允许 ±5%"))
    c = bevel.check
    checks.append(("高速级锥齿轮齿面接触疲劳强度", c.sigma_h <= c.sigma_h_allow,
                   f"σH = {c.sigma_h/1e6:.1f} MPa ≤ [σH] = {c.sigma_h_allow/1e6:.1f} MPa"))
    for i in (0, 1):
        checks.append((f"高速级{'小' if i == 0 else '大'}锥齿轮齿根弯曲疲劳强度", c.sigma_f[i] <= c.sigma_f_allow[i],
                       f"σF = {c.sigma_f[i]/1e6:.1f} MPa ≤ [σF] = {c.sigma_f_allow[i]/1e6:.1f} MPa"))
    c = low.check
    checks.append(("低速级齿面接触疲劳强度", c.sigma_h <= c.sigma_h_allow,
                   f"σH = {c.sigma_h/1e6:.1f} MPa ≤ [σH] = {c.sigma_h_allow/1e6:.1f} MPa"))
    for i in (0, 1):
        checks.append((f"低速级{'小' if i == 0 else '大'}齿轮齿根弯曲疲劳强度", c.sigma_f[i] <= c.sigma_f_allow[i],
                       f"σF = {c.sigma_f[i]/1e6:.1f} MPa ≤ [σF] = {c.sigma_f_allow[i]/1e6:.1f} MPa"))
    for s in shafts:
        sc = s.strength
        checks.append((f"{s.layout.name}弯扭合成强度", sc.ok,
                       f"σca = {sc.critical.sigma_ca/1e6:.1f} MPa ≤ [σ−1b] = {sc.sigma_allow/1e6:.0f} MPa"))
        fc = s.fatigue
        if fc.critical is not None:
            cr = fc.critical
            checks.append((f"{s.layout.name}疲劳强度安全系数", fc.ok,
                           f"Sca = {cr.S_ca:.2f} ≥ [S] = {fc.S_required:g}（{cr.label}，近似）"))
        b = s.bearings
        checks.append((f"{s.layout.name}轴承 {b.bearing.designation} 寿命", b.ok,
                       f"L10h = {min(b.life):.0f} h ≥ {b.required:.0f} h"))
        for k in s.keys:
            checks.append((f"{k.location}平键挤压强度", k.ok,
                           f"σp = {k.sigma_p/1e6:.1f} MPa ≤ [σp] = {k.sigma_allow/1e6:.0f} MPa"
                           + ("（双键）" if k.count == 2 else "")))
    checks.append(("小锥齿轮悬臂支承", ps.span >= 2 * ps.overhang - 1e-9,
                   f"支点距离 {ps.span/MM:.0f} mm ≥ 2 × 悬臂长度 {ps.overhang/MM:.0f} mm"))
    # 大锥齿轮不得碰到Ⅲ轴
    d3 = max(seg.d for seg in s3.layout.segments if seg.z0 <= pos.z_back + hub and seg.z1 >= pos.z_back)
    gap = low.a - bevel.da2 / 2 - d3 / 2
    checks.append(("大锥齿轮与低速轴间隙", gap >= 10 * MM, f"{gap/MM:.1f} mm ≥ 10 mm"))
    # 小锥齿轮内端不得碰到大锥齿轮轮毂
    u_small = (bevel.cone_distance - bevel.b) * math.cos(bevel.delta1)
    gap = u_small - 2 * MM - 1.6 * s2.layout.diameters["齿轮"] / 2
    checks.append(("小锥齿轮与大锥齿轮轮毂间隙", gap >= 5 * MM, f"{gap/MM:.1f} mm ≥ 5 mm"))
    # 浸油：大锥齿轮整个齿宽浸入油中（取 0.7b 的径向投影），低速级大齿轮浸油不超过半径的 1/3
    dip = _dip_depth(bevel, low)
    dip_ok = dip <= low.da2 / 6
    checks.append(("浸油润滑深度", dip_ok, f"低速级大齿轮浸油 {dip/MM:.0f} mm ≤ R/3 = {low.da2/6/MM:.0f} mm"))
    if kin.reducer_ratio > 25:
        warnings.append(f"总传动比 {kin.reducer_ratio:.1f} 超出圆锥-圆柱齿轮减速器的常用范围（8～25），"
                        "可改选同步转速 1000 r/min 的电动机（任务书 motor_sync_speed_rpm: 1000）。")
    if kin.i_high > 3 + 1e-9:
        warnings.append(f"为使两级大齿轮都能浸油润滑，锥齿轮传动比加大到 {kin.i_high:.2f}（直齿锥齿轮一般不超过 3）。")
    if bevel.inp.min_d1:
        warnings.append(f"为使大锥齿轮能浸到油，锥齿轮按结构要求加大到 d1 = {bevel.d1 / MM:.0f} mm（强度有富余）。")
    if not dip_ok:
        warnings.append("大锥齿轮浸油时低速级大齿轮浸得太深，可减小锥齿轮传动比或改用带油轮润滑。")
    warnings.append("锥齿轮的 Kv 用解析近似、按精度降低一级取；KHβ = 1.5 KHβbe，KHβbe 按小锥齿轮悬臂取 1.1。")
    warnings.append("圆锥滚子轴承的压力中心按 a ≈ T/2 + (d + D)e/6 近似，数据待人工核对。")
    warnings.append("联轴器只给出计算转矩和轴孔直径，型号请按 GB/T 5014（LX 型弹性柱销联轴器）核对。")
    return BevelReducerDesign(task, kin, bevel, low, h, pos, ps, shafts, couplings, checks, warnings)

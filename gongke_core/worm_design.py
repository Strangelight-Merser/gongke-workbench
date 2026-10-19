"""单级蜗杆减速器（任务书 scheme: worm）的设计总流程。

电动机 → 联轴器 → 蜗杆传动（蜗杆下置）→ 联轴器 → 卷筒。结构布置见 `layout/worm_reducer.py`。
蜗杆传动效率先按头数估取，选出电动机、设计出蜗杆传动后再用实际效率重算各轴功率（必要时重选电动机）。
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from gongke_core import standards
from gongke_core.calc import bearing as bearing_calc
from gongke_core.calc import fatigue as fatigue_calc
from gongke_core.calc import key as key_calc
from gongke_core.calc import kinematics
from gongke_core.calc import shaft as shaft_calc
from gongke_core.calc import worm as worm_calc
from gongke_core.design import Coupling, ReducerTask, ShaftResult, _end_failed
from gongke_core.layout import reducer as lay
from gongke_core.layout import worm_reducer as wlay

MM = 1e-3


@dataclass
class WormReducerDesign:
    task: ReducerTask
    kin: kinematics.Kinematics
    worm: worm_calc.WormPair
    housing: lay.Housing
    worm_shaft: wlay.WormShaft
    shafts: list[ShaftResult]
    couplings: list[Coupling]
    thermal: worm_calc.ThermalCheck
    stiffness: worm_calc.WormStiffness
    checks: list[tuple[str, bool, str]]
    warnings: list[str]
    belt: None = None

    @property
    def high(self) -> worm_calc.WormPair:
        return self.worm

    @property
    def z_mid(self) -> float:
        """蜗轮中间平面（蜗杆轴线）的 z。"""
        return self.housing.inner_width / 2

    @property
    def actual_ratio(self) -> float:
        return self.worm.u

    @property
    def output_speed_error(self) -> float:
        n_out = self.kin.motor.speed_rpm / self.actual_ratio
        return (n_out - self.kin.drum_speed_rpm) / self.kin.drum_speed_rpm

    @property
    def ok(self) -> bool:
        return all(ok for _, ok, _ in self.checks)


def worm_loads(w: worm_calc.WormPair) -> tuple[shaft_calc.PointLoad, shaft_calc.PointLoad]:
    """啮合力。蜗杆在下方，啮合点在蜗杆顶部（蜗轮底部）。

    蜗杆轴局部坐标：轴向 = 总体 x，局部 x = 总体 z，局部 y = 总体 y。约定蜗杆转向使蜗杆所受切向力
    Ft1 沿 +z、轴向力 Fa1 沿 +x；径向力 Fr 指向各自轴线。蜗轮所受的力与之大小相等、方向相反：
    Ft2（沿 −x）、Fa2（沿 −z）、Fr（沿 +y）。
    """
    ft1, ft2, fr = w.tangential_force1, w.tangential_force2, w.radial_force
    on_worm = shaft_calc.PointLoad(0.0, fx=+ft1, fy=-fr, fz=+ft2, y0=+w.d1 / 2, label="蜗杆")
    on_wheel = shaft_calc.PointLoad(0.0, fx=-ft2, fy=+fr, fz=-ft1, y0=-w.d2 / 2, label="蜗轮")
    return on_worm, on_wheel


def _worm_shaft(task: ReducerTask, kin: kinematics.Kinematics, h: lay.Housing,
                w: worm_calc.WormPair) -> tuple[ShaftResult, wlay.WormShaft]:
    st = kin.shafts[1]
    d_min = shaft_calc.min_diameter(st.power, st.speed_rpm)
    d_end = lay.std_diameter(max(1.05 * d_min, 0.8 * kin.motor.shaft_d))
    on_worm, _ = worm_loads(w)
    last = None
    for _ in range(6):
        d_seal = lay.std_diameter(1.14 * d_end)
        hub = lay.coupling_hub_length(d_end)
        d_b0 = lay.ceil_to(d_seal + 1 * MM, 5 * MM)
        end_failed = False
        for step in range(8):
            d_b = d_b0 + step * 5 * MM
            for brg in standards.tapered_with_bore(d_b):
                ws = wlay.worm_shaft(h, w, brg, d_end, d_seal, d_b, hub)
                segs = ws.segments
                z_ext = lay.shaft_extension_z(segs)
                case = shaft_calc.ShaftLoadCase(ws.bearing_x, [on_worm], [(z_ext, st.torque), (0.0, -st.torque)])
                seg = next(s for s in segs if s.role == "端部")
                kc = key_calc.select(f"{st.name}联轴器处", st.torque, d_end, hub, task.key_sigma_allow)
                seg.keyway = (kc.size.b, kc.size.t1, kc.length)
                keys = [kc]
                strength = shaft_calc.check(segs, case, task.shaft_sigma_allow)
                r = strength.reactions
                bc = bearing_calc.check_tapered_pair(brg, r.radial_a, r.radial_b, r.axial, st.speed_rpm,
                                                     task.bearing_life_hours, task.load_factor_bearing, "正装")
                gear = lay.GearOnShaft("worm", 1, 0.0, w.b1, True, None, "left", w.df1, w.da1)
                sl = lay.ShaftLayout(1, st.name, 0.0, d_min, brg, ws.bearing_x, [gear], segs, "left", hub,
                                     dict(ws.diameters))
                fat = fatigue_calc.check(segs, case, fatigue_calc.MATERIALS["45"], task.shaft_S_required,
                                         task.shaft_fit_k)
                last = (ShaftResult(sl, case, strength, bc, keys, fat, st.power, st.speed_rpm, st.torque), ws)
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


def _wheel_shaft(task: ReducerTask, kin: kinematics.Kinematics, h: lay.Housing, w: worm_calc.WormPair,
                 hub: float) -> ShaftResult:
    """Ⅱ轴：蜗轮在中间，一对圆锥滚子轴承正装（便于调整蜗轮中间平面位置），输出端在 z = W 一侧。"""
    st = kin.shafts[2]
    d_min = shaft_calc.min_diameter(st.power, st.speed_rpm)
    d_end = lay.std_diameter(1.05 * d_min)
    zw = h.inner_width / 2
    _, on_wheel = worm_loads(w)
    on_wheel = replace(on_wheel, z=zw)
    last = None
    for _ in range(6):
        d_seal = lay.std_diameter(1.14 * d_end)
        hub_c = lay.coupling_hub_length(d_end)
        d_b0 = lay.ceil_to(d_seal + 1 * MM, 5 * MM)
        end_failed = False
        for step in range(8):
            d_b = d_b0 + step * 5 * MM
            for brg in standards.tapered_with_bore(d_b):
                dia = lay.diameters(d_b, brg.D, d_end, d_seal)
                gears = [lay.GearOnShaft("worm", 2, zw, hub, False, dia.seat, "left", w.df2, w.de2)]
                segs = lay.build_segments(h, brg, dia, gears, "right", hub_c)
                off = brg.a - brg.T / 2
                za = -h.gap_bearing - brg.T / 2 + off
                zb = h.inner_width + h.gap_bearing + brg.T / 2 - off
                z_ext = lay.shaft_extension_z(segs)
                case = shaft_calc.ShaftLoadCase((za, zb), [on_wheel], [(zw, st.torque), (z_ext, -st.torque)])
                keys = []
                seg = next(s for s in segs if s.role == "齿轮")
                kc = key_calc.select(f"{st.name}蜗轮处", st.torque, dia.seat, seg.length + 2 * MM, task.key_sigma_allow)
                seg.keyway = (kc.size.b, kc.size.t1, kc.length)
                keys.append(kc)
                seg = next(s for s in segs if s.role == "端部")
                kc = key_calc.select(f"{st.name}联轴器处", st.torque, d_end, hub_c, task.key_sigma_allow)
                seg.keyway = (kc.size.b, kc.size.t1, kc.length)
                keys.append(kc)
                strength = shaft_calc.check(segs, case, task.shaft_sigma_allow)
                r = strength.reactions
                bc = bearing_calc.check_tapered_pair(brg, r.radial_a, r.radial_b, r.axial, st.speed_rpm,
                                                     task.bearing_life_hours, task.load_factor_bearing, "正装")
                sl = lay.ShaftLayout(2, st.name, 0.0, d_min, brg, (za, zb), gears, segs, "right", hub_c,
                                     {"端部": d_end, "密封": d_seal, "轴承": d_b, "齿轮": dia.seat,
                                      "轴环": dia.collar, "轴肩": dia.shoulder})
                fat = fatigue_calc.check(segs, case, fatigue_calc.MATERIALS["45"], task.shaft_S_required,
                                         task.shaft_fit_k)
                last = ShaftResult(sl, case, strength, bc, keys, fat, st.power, st.speed_rpm, st.torque)
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


def _kinematics(task: ReducerTask, eta: float) -> kinematics.Kinematics:
    eff = replace(task.conveyor.efficiencies, worm_pair=eta)
    return kinematics.solve(replace(task.conveyor, efficiencies=eff))


def _settle(task: ReducerTask, kin: kinematics.Kinematics, min_d1: float):
    """设计蜗杆传动并用其实际效率重算各轴参数（必要时重选电动机），直到蜗杆传动参数不再变化，
    使说明书中代入的效率与蜗杆传动的设计结果一致。"""
    t = task.conveyor

    def make(k):
        return worm_calc.design(worm_calc.WormPairInput(
            "蜗杆传动", k.shafts[1].torque, k.shafts[1].speed_rpm, k.total_ratio, t.life_hours,
            **{**task.high, "min_d1": max(min_d1, task.high.get("min_d1", 0.0))}))

    w = make(kin)
    for _ in range(6):
        kin_new = _kinematics(task, w.eta)
        w_new = make(kin_new)
        if (w_new.a, w_new.m, w_new.d1, w_new.z2, kin_new.motor.model) == (w.a, w.m, w.d1, w.z2, kin.motor.model):
            return _kinematics(task, w_new.eta), w_new
        kin, w = kin_new, w_new
    return _kinematics(task, w.eta), w


def run(task: ReducerTask) -> WormReducerDesign:
    t = task.conveyor
    # 先按估计效率选电动机，再按实际效率重算，直到电动机不再变化
    kin = _kinematics(task, t.efficiencies.worm_pair)
    kin = _kinematics(task, kinematics.worm_starts_estimate_eta(kin.total_ratio))
    kin, w = _settle(task, kin, 0.0)

    for _ in range(6):  # 蜗杆刚度不够时加大蜗杆直径重新设计
        seat_guess = lay.std_diameter(
            1.05 * shaft_calc.min_diameter(kin.shafts[2].power, kin.shafts[2].speed_rpm) + 10 * MM)
        hub = wlay.wheel_hub(w, seat_guess)
        brg_D = 72 * MM
        for _ in range(5):
            h = wlay.housing(w, hub, brg_D)
            s1, ws = _worm_shaft(task, kin, h, w)
            s2 = _wheel_shaft(task, kin, h, w, hub)
            hub_need = wlay.wheel_hub(w, s2.layout.diameters["齿轮"])
            if hub_need <= hub + 1e-9 and ws.bearing.D <= brg_D + 1e-9:
                break
            hub, brg_D = max(hub, hub_need), max(brg_D, ws.bearing.D)
        if worm_calc.worm_stiffness(w, ws.span).ok:
            break
        try:
            kin, w = _settle(task, kin, w.d1 + 1e-6)
        except standards.SelectionError:
            break
    s1.layout.x = 0.0
    s2.layout.x = 0.0
    shafts = [s1, s2]

    couplings = [
        Coupling("电动机—Ⅰ轴", task.coupling_service_factor * kin.shafts[1].torque,
                 (kin.motor.shaft_d, s1.layout.diameters["端部"]), s1.layout.coupling_hub),
        Coupling("Ⅱ轴—卷筒轴", task.coupling_service_factor * kin.shafts[2].torque,
                 (s2.layout.diameters["端部"], s2.layout.diameters["端部"]), s2.layout.coupling_hub),
    ]

    checks: list[tuple[str, bool, str]] = []
    warnings: list[str] = []
    n_out = kin.motor.speed_rpm / w.u
    err = (n_out - kin.drum_speed_rpm) / kin.drum_speed_rpm
    checks.append(("输送带速度误差", abs(err) <= 0.05, f"{err*100:+.2f}%，允许 ±5%"))
    c = w.check
    checks.append(("蜗轮齿面接触疲劳强度", c.sigma_h <= c.sigma_h_allow,
                   f"σH = {c.sigma_h/1e6:.1f} MPa ≤ [σH] = {c.sigma_h_allow/1e6:.1f} MPa"))
    checks.append(("蜗轮齿根弯曲疲劳强度", c.sigma_f <= c.sigma_f_allow,
                   f"σF = {c.sigma_f/1e6:.1f} MPa ≤ [σF] = {c.sigma_f_allow/1e6:.1f} MPa"))
    stiff = worm_calc.worm_stiffness(w, ws.span)
    checks.append(("蜗杆刚度", stiff.ok, f"y = {stiff.deflection/MM:.4f} mm ≤ [y] = d1/1000 = {stiff.allowable/MM:.3f} mm"))
    eta_red = w.eta * t.efficiencies.bearing_pair ** 2
    th = worm_calc.thermal(kin.shafts[1].power, eta_red, w.a)
    checks.append(("热平衡", th.ok, f"油温 t0 = {th.t_oil:.1f} ℃ ≤ {worm_calc.OIL_LIMIT:.0f} ℃"
                                   f"（S = {th.area:.2f} m²，αd = {th.alpha_d:g} W/(m²·℃)）"))
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
    if w.sliding_velocity > 5:
        warnings.append(f"滑动速度 vs = {w.sliding_velocity:.1f} m/s 较高，蜗杆下置浸油润滑时注意搅油损失；"
                        "vs > 10 m/s 时宜改用蜗杆上置或喷油润滑。")
    if not th.ok:
        warnings.append("油温超过许用值：可在箱体上加散热片、在蜗杆轴端装风扇（αd 可提高到 20～30 W/(m²·℃)），"
                        "或在油池内装冷却水管。")
    if w.inp.min_d1:
        warnings.append(f"为满足蜗杆刚度，蜗杆分度圆直径加大到 d1 = {w.d1 / MM:g} mm。")
    if kin.total_ratio < 10:
        warnings.append(f"传动比 {kin.total_ratio:.1f} 偏小，蜗杆传动的经济传动比为 10～40，可考虑圆柱齿轮减速器。")
    warnings.append("蜗轮齿形系数 YFa2 借用圆柱齿轮的曲线、接触系数 Zρ 和当量摩擦角按教材图表插值，数据待人工核对。")
    warnings.append("箱体散热面积按经验式 S ≈ 9×10⁻⁵ a^1.88 估算，定稿时按实际箱体外形核算。")
    warnings.append("联轴器只给出计算转矩和轴孔直径，型号请按 GB/T 5014（LX 型弹性柱销联轴器）核对。")
    return WormReducerDesign(task, kin, w, h, ws, shafts, couplings, th, stiff, checks, warnings)

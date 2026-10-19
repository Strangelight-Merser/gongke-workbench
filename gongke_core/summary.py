"""设计结果的精简摘要（可 JSON 序列化），供界面显示和其他程序读取。长度单位 mm、应力 MPa。"""

from __future__ import annotations

import math

from gongke_core.design import ReducerDesign


def summarize(d: ReducerDesign) -> dict:
    k = d.kin
    gears = {}
    if d.task.scheme == "worm":
        w = d.worm
        gears["worm"] = {
            "name": w.inp.name, "type": "worm", "m": w.m * 1e3, "z1": w.z1, "z2": w.z2, "a": w.a * 1e3,
            "d1": w.d1 * 1e3, "d2": w.d2 * 1e3, "x2": w.x2, "gamma_deg": math.degrees(w.gamma),
            "eta": w.eta, "sliding_velocity": w.sliding_velocity, "wheel_material": w.material.name,
            "sigma_h": w.check.sigma_h / 1e6, "sigma_h_allow": w.check.sigma_h_allow / 1e6,
            "sigma_f": [w.check.sigma_f / 1e6], "sigma_f_allow": [w.check.sigma_f_allow / 1e6],
            "oil_temp": d.thermal.t_oil, "deflection_mm": d.stiffness.deflection * 1e3,
        }
    pairs = () if d.task.scheme == "worm" else (("high", d.high), ("low", d.low))
    for key, p in pairs:
        if not hasattr(p, "mn"):  # 直齿锥齿轮
            gears[key] = {
                "name": p.inp.name, "type": "bevel", "m": p.m * 1e3, "z1": p.z1, "z2": p.z2,
                "delta1_deg": math.degrees(p.delta1), "R": p.cone_distance * 1e3, "b": p.b * 1e3,
                "d1": p.d1 * 1e3, "d2": p.d2 * 1e3,
                "sigma_h": p.check.sigma_h / 1e6, "sigma_h_allow": p.check.sigma_h_allow / 1e6,
                "sigma_f": [s / 1e6 for s in p.check.sigma_f], "sigma_f_allow": [s / 1e6 for s in p.check.sigma_f_allow],
            }
            continue
        gears[key] = {
            "name": p.inp.name, "mn": p.mn * 1e3, "z1": p.z1, "z2": p.z2, "beta_deg": math.degrees(p.beta),
            "a": p.a * 1e3, "d1": p.d1 * 1e3, "d2": p.d2 * 1e3, "b1": p.b1 * 1e3, "b2": p.b2 * 1e3,
            "sigma_h": p.check.sigma_h / 1e6, "sigma_h_allow": p.check.sigma_h_allow / 1e6,
            "sigma_f": [s / 1e6 for s in p.check.sigma_f], "sigma_f_allow": [s / 1e6 for s in p.check.sigma_f_allow],
        }
    shafts = []
    for s in d.shafts:
        lay = s.layout
        shafts.append({
            "name": lay.name, "bearing": lay.bearing.designation,
            "diameters": {k2: (v * 1e3 if v else None) for k2, v in lay.diameters.items()},
            "segments": [{"role": g.role, "z0": g.z0 * 1e3, "length": g.length * 1e3, "d": (g.root_d or g.d) * 1e3}
                         for g in lay.segments],
            "sigma_ca": s.strength.critical.sigma_ca / 1e6,
            "bearing_life_h": min(s.bearings.life),
            "integral_pinion": any(g.integral for g in lay.gears),
        })
    belt = None
    if d.belt:
        b = d.belt
        belt = {"section": b.sec.name, "dd1": b.dd1 * 1e3, "dd2": b.dd2 * 1e3, "z": b.z, "ld": b.ld * 1e3,
                "a": b.a * 1e3, "alpha1_deg": b.alpha1, "v": b.v, "f0": b.f0, "fp": b.fp}
    return {
        "title": d.task.title,
        "scheme": d.task.scheme,
        "belt": belt,
        "motor": {"model": k.motor.model, "power_kw": k.motor.power / 1e3, "speed_rpm": k.motor.speed_rpm},
        "ratios": {"total": k.total_ratio, "belt": k.i_belt, "high": d.high.u, "low": d.low.u if hasattr(d, "low") else None, "speed_error_pct": d.output_speed_error * 100},
        "shaft_states": [{"name": s.name, "power_kw": s.power / 1e3, "speed_rpm": s.speed_rpm, "torque_nm": s.torque}
                         for s in k.shafts],
        "gears": gears,
        "shafts": shafts,
        "checks": [{"item": n, "ok": ok, "detail": t} for n, ok, t in d.checks],
        "warnings": d.warnings,
        "ok": d.ok,
    }

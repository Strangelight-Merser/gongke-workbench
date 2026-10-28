"""真实 U1 梁求解的闭式基准与网格收敛；不证明 CAD 局部应力或整轴安全。

运行：python tests/e2e/shaft_beam_convergence.py --course-snapshot <原生读取记录.json> --out <新目录>
均匀简支轴中央集中力：y_b=PL³/(48EI)，y_s=PL/(4κGA)，端部截面转角=PL²/(16EI)。
前者由 EI*y''=M 积分和简支边界得到，剪切项由 V/(κGA) 积分得到；κ 与现有 U1 输入一致。
课程轴解析参考仍是数值积分，并额外细化参考步长，不能称为另一套独立机械模型。
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from gongke_core.calc import shaft, shaft_stiffness
from gongke_core.fem import ccx, shaft_beam
from gongke_core.shaft_jobs import _beam_inputs


MESHES_M = (0.004, 0.002, 0.001)
NU = 0.3
REFERENCE_STEP_M = 0.0000625
# 预先声明数值验收阈值；不随本次结果调整，也不是机械设计许用值。
PROFILE_ERROR_LIMIT = 0.01
GRID_CHANGE_LIMIT = 0.005
REFERENCE_CHANGE_LIMIT = 0.0001
CLOSED_POINT_ERROR_LIMIT = 0.001


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + "\n", encoding="utf-8")


def solve_mesh(directory, solver, segments, case, young, h_max):
    directory.mkdir()
    inp = directory / "shaft.inp"
    nodes = shaft_beam.write_inp(inp, segments, case, E=young, nu=NU, h_max=h_max)
    with (directory / "stdout.log").open("w", encoding="utf-8") as log:
        completed = subprocess.run([str(solver), "-i", inp.stem], cwd=directory,
                                   stdout=log, stderr=subprocess.STDOUT, timeout=300,
                                   env=dict(os.environ, OMP_NUM_THREADS="1"))
    log = (directory / "stdout.log").read_text(errors="replace")
    dat = inp.with_suffix(".dat")
    if completed.returncode or "*ERROR" in log or not dat.is_file():
        raise RuntimeError(f"真实 ccx 求解失败，保留输入和日志：{directory}")
    values = shaft_beam.read_displacements(dat)
    if any(i not in values or len(values[i]) != 6 or not all(math.isfinite(v) for v in values[i])
           for i in range(1, len(nodes) + 1)):
        raise RuntimeError(f"位移或转角缺失、非有限：{dat}")
    column = lambda index, scale=1: [values[i][index] * scale for i in range(1, len(nodes) + 1)]
    curve = shaft_beam.BeamResult(nodes, column(0, shaft_beam.MM), column(1, shaft_beam.MM), column(3), column(4))
    return curve, {"h_max_m": h_max, "nodes": len(nodes), "elements": len(nodes) - 1,
                   "solver_returncode": completed.returncode, "directory": str(directory),
                   "inp_sha256": hashlib.sha256(inp.read_bytes()).hexdigest()}


def max_difference(a, b):
    return max(abs(x - y) for x, y in zip(a, b))


def assess_meshes(directory, solver, segments, case, young, probes, reference, limits=()):
    reference_y = [reference(z)[0] for z in probes]
    reference_theta = [reference(z)[1] for z in probes]
    results, samples, curves = [], [], []
    for h in MESHES_M:
        mesh_dir = directory / f"h{h * 1000:g}mm"
        curve, record = solve_mesh(mesh_dir, solver, segments, case, young, h)
        values_y = [curve.deflection(z) for z in probes]
        values_theta = [curve.slope(z) for z in probes]
        record.update(max_deflection_m=max(curve.deflection(z) for z in curve.z),
                      reference_max_deflection_m=max(reference_y),
                      normalized_profile_deflection_error=max_difference(values_y, reference_y) / max(reference_y),
                      normalized_profile_rotation_error=max_difference(values_theta, reference_theta) / max(reference_theta))
        if limits:
            record["stiffness_checks"] = []
            for item in limits:
                value = curve.deflection(item["z_m"]) if item["kind"] == "y" else curve.slope(item["z_m"])
                reference_value = reference(item["z_m"])[0 if item["kind"] == "y" else 1]
                record["stiffness_checks"].append({**item, "value": value, "reference_value": reference_value,
                                                    "status": "pass" if value <= item["limit"] else "fail"})
        write_json(mesh_dir / "result.json", record)
        print(json.dumps({"case": directory.name, "h_mm": h * 1000, "nodes": len(curve.z),
                          "deflection_m": record["max_deflection_m"],
                          "relative_profile_error": record["normalized_profile_deflection_error"]}), flush=True)
        results.append(record)
        samples.append((values_y, values_theta))
        curves.append(curve)
    changes = [{"from_h_m": MESHES_M[i], "to_h_m": MESHES_M[i + 1],
                "normalized_deflection_change": max_difference(samples[i][0], samples[i + 1][0]) / max(reference_y),
                "normalized_rotation_change": max_difference(samples[i][1], samples[i + 1][1]) / max(reference_theta)}
               for i in range(len(samples) - 1)]
    # 若变化已低于输出精度影响量，不以末位舍入波动声称失去收敛。
    checks = {
        "finest_profile_matches_reference": max(results[-1]["normalized_profile_deflection_error"],
                                                 results[-1]["normalized_profile_rotation_error"]) <= PROFILE_ERROR_LIMIT,
        "finest_two_grids_agree": max(changes[-1]["normalized_deflection_change"],
                                       changes[-1]["normalized_rotation_change"]) <= GRID_CHANGE_LIMIT,
        "grid_change_reduces": all(changes[-1][key] <= max(changes[0][key], 1e-5)
                                   for key in ("normalized_deflection_change", "normalized_rotation_change")),
    }
    return {"meshes": results, "successive_grid_changes": changes, "numerical_checks": checks}, curves


def run(output, course_path):
    solver = ccx.find()
    ccx.check_version(solver)
    payload = json.loads(course_path.read_text(encoding="utf-8"))
    snapshot = payload["snapshot"]
    if payload.get("ok") is not True or snapshot.get("scope") != "course_shaft_review":
        raise ValueError("需要已成功读取的课程原生轴记录及其 snapshot")
    segments, course_case, course_limits = _beam_inputs(snapshot)
    output.mkdir(parents=True, exist_ok=False)
    uniform_dir, course_dir = output / "uniform", output / "course"
    uniform_dir.mkdir()
    course_dir.mkdir()
    write_json(course_dir / "snapshot.json", snapshot)
    write_json(course_dir / "source.json", {"artifact": str(course_path),
               "artifact_sha256": hashlib.sha256(course_path.read_bytes()).hexdigest(),
               "saved_project": payload.get("saved_project"), "scope": "saved_native_snapshot_core_solver_validation"})

    length, diameter, force, young = 0.4, 0.04, 1000.0, 206e9
    area, inertia = math.pi * diameter**2 / 4, math.pi * diameter**4 / 64
    shear_modulus, kappa = young / (2 * (1 + NU)), 6 * (1 + NU) / (7 + 6 * NU)
    uniform_segments = [shaft.Segment(0, length, diameter, "均匀简支轴")]
    uniform_case = shaft.ShaftLoadCase((0, length), [shaft.PointLoad(length / 2, fy=-force)], [])

    def closed(z):
        x = min(z, length - z)
        bending = force * x * (3 * length**2 - 4 * x**2) / (48 * young * inertia)
        shear = force * x / (2 * kappa * shear_modulus * area)
        rotation = force * (3 * length**2 - 12 * x**2) / (48 * young * inertia)
        return bending + shear, abs(rotation)

    closed_eb = force * length**3 / (48 * young * inertia)
    closed_shear = force * length / (4 * kappa * shear_modulus * area)
    write_json(uniform_dir / "input.json", {
        "segments": [asdict(s) for s in uniform_segments], "load_case": asdict(uniform_case),
        "young_modulus_pa": young, "poisson_ratio": NU, "shear_coefficient": kappa,
        "source": "人工闭式基准：静力平衡、EI*y''=M 和 V/(κGA) 积分；材料仅为声明数值。",
    })
    probes = [length * i / 1000 for i in range(1001)]
    uniform, curves = assess_meshes(uniform_dir, solver, uniform_segments, uniform_case, young, probes, closed)
    analytic_eb = shaft_stiffness.solve(uniform_segments, uniform_case, E=young, step=REFERENCE_STEP_M)
    analytic_timo = shaft_stiffness.solve(uniform_segments, uniform_case, E=young, step=REFERENCE_STEP_M, shear=True, nu=NU)
    uniform["closed_form"] = {
        "center_eb_deflection_m": closed_eb, "center_shear_deflection_m": closed_shear,
        "center_timoshenko_deflection_m": closed_eb + closed_shear, "support_section_rotation_rad": closed(0)[1],
        "numeric_eb_center_m": analytic_eb.deflection(length / 2),
        "numeric_timoshenko_center_m": analytic_timo.deflection(length / 2),
        "finest_fem_center_m": curves[-1].deflection(length / 2), "finest_fem_support_rotation_rad": curves[-1].slope(0),
    }
    uniform["numerical_checks"]["closed_center_and_rotation"] = (
        abs(curves[-1].deflection(length / 2) / (closed_eb + closed_shear) - 1) <= CLOSED_POINT_ERROR_LIMIT
        and abs(curves[-1].slope(0) / closed(0)[1] - 1) <= CLOSED_POINT_ERROR_LIMIT)
    uniform["numerical_checks"]["analytic_eb_and_shear_agree_with_closed_form"] = (
        abs(analytic_eb.deflection(length / 2) / closed_eb - 1) <= REFERENCE_CHANGE_LIMIT
        and abs(analytic_timo.deflection(length / 2) / (closed_eb + closed_shear) - 1) <= REFERENCE_CHANGE_LIMIT)

    young = snapshot["material"]["young_modulus_pa"]
    fine = shaft_stiffness.solve(segments, course_case, E=young, step=REFERENCE_STEP_M, shear=True, nu=NU)
    coarse = shaft_stiffness.solve(segments, course_case, E=young, step=REFERENCE_STEP_M * 2, shear=True, nu=NU)
    start, end = segments[0].z0, segments[-1].z1
    probes = sorted({start + (end - start) * i / 1000 for i in range(1001)}
                    | {item["z_m"] for item in snapshot["stiffness_limits"]})
    course, _ = assess_meshes(course_dir, solver, segments, course_case, young, probes,
                            lambda z: (fine.deflection(z), fine.slope(z)), snapshot["stiffness_limits"])
    fine_y, fine_theta = [fine.deflection(z) for z in probes], [fine.slope(z) for z in probes]
    reference_changes = {
        "coarse_step_m": REFERENCE_STEP_M * 2, "fine_step_m": REFERENCE_STEP_M,
        "normalized_deflection_change": max_difference([coarse.deflection(z) for z in probes], fine_y) / max(fine_y),
        "normalized_rotation_change": max_difference([coarse.slope(z) for z in probes], fine_theta) / max(fine_theta),
    }
    course["analytic_reference_refinement"] = reference_changes
    course["numerical_checks"]["analytic_reference_stable"] = max(reference_changes[key] for key in
        ("normalized_deflection_change", "normalized_rotation_change")) <= REFERENCE_CHANGE_LIMIT
    course["material_source"] = snapshot["material"]["source"]
    course["limitations"] = list(course_limits)

    summary = {
        "created_at": datetime.now(timezone.utc).isoformat(), "solver": str(solver), "solver_version": ccx.version(solver),
        "scope": "core_u1_beam_numerical_validation", "engineering_conclusion": "not_established",
        "thresholds": {"finest_profile_relative_error": PROFILE_ERROR_LIMIT, "finest_two_grids_relative_change": GRID_CHANGE_LIMIT,
                       "analytic_reference_relative_change": REFERENCE_CHANGE_LIMIT, "closed_point_relative_error": CLOSED_POINT_ERROR_LIMIT},
        "uniform": uniform, "course": course,
        "numerical_validation_passed": all(uniform["numerical_checks"].values()) and all(course["numerical_checks"].values()),
        "limitations": [
            "仅验证线弹性小变形、简支条件下的圆截面 Timoshenko 梁数值；泊松比0.3及剪切系数均为声明假设。",
            "课程快照来自已保存的原生读取记录，不代表运行时重新读取或验收了当前打开的 CAD。",
            "课程梁保留完整集中力及轴向偏心力偶；不施加 torque_points，不校核扭转、键槽/圆角局部应力或疲劳。",
            "材料和课程刚度限值仍沿用原来源状态，网格收敛与解析接近不能升级为实际工程接受。",
        ],
    }
    write_json(output / "summary.json", summary)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--course-snapshot", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    result = run(args.out.resolve(), args.course_snapshot.resolve())
    print(json.dumps({"numerical_validation_passed": result["numerical_validation_passed"],
                      "summary": str(args.out.resolve() / "summary.json")}, ensure_ascii=False))
    raise SystemExit(0 if result["numerical_validation_passed"] else 1)

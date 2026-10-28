"""传动装置的总体设计：工作机功率、电动机选择、传动比分配、各轴运动和动力参数。

方案一（coupling）：电动机 → 联轴器 → 展开式二级圆柱齿轮减速器 → 联轴器 → 卷筒；
方案二（vbelt）：电动机 → V 带传动 → 展开式二级圆柱齿轮减速器 → 联轴器 → 卷筒；
方案三（bevel）：电动机 → 联轴器 → 圆锥-圆柱齿轮减速器 → 联轴器 → 卷筒；
方案四（worm）：电动机 → 联轴器 → 单级蜗杆减速器（蜗杆下置）→ 联轴器 → 卷筒；
方案五（single）：电动机 → V 带传动 → 一级斜齿圆柱齿轮减速器 → 联轴器 → 卷筒。
轴编号：0 电动机轴，1 高速轴，2 中间轴，3 低速轴，4 卷筒轴；蜗杆减速器和一级减速器只有两根轴：
0 电动机轴，1 高速轴（蜗杆轴），2 低速轴（蜗轮轴），3 卷筒轴。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

from gongke_core import standards


@dataclass
class Efficiencies:
    """各传动环节效率，默认值取课程设计指导书常用推荐值。"""

    coupling: float = 0.99  # 弹性联轴器
    bearing_pair: float = 0.99  # 一对滚动轴承
    gear_pair: float = 0.97  # 8 级精度闭式圆柱齿轮
    drum: float = 0.96  # 卷筒（含卷筒轴承）
    belt: float = 0.96  # V 带传动
    bevel_pair: float = 0.96  # 8 级精度闭式直齿锥齿轮
    worm_pair: float = 0.80  # 蜗杆传动（含搅油损失）的初估值，双头蜗杆 0.75～0.82；设计后按实际值重算

    def total(self, scheme: str = "coupling") -> float:
        if scheme == "worm":  # 联轴器 ×2，轴承 ×2 对，蜗杆传动 ×1，卷筒 ×1
            return self.coupling**2 * self.bearing_pair**2 * self.worm_pair * self.drum
        if scheme == "single":  # V 带 ×1，联轴器 ×1，轴承 ×2 对，齿轮 ×1，卷筒 ×1
            return self.belt * self.coupling * self.bearing_pair**2 * self.gear_pair * self.drum
        # 联轴器 ×2（V 带方案为 V 带 ×1、联轴器 ×1），轴承 ×3 对（减速器三根轴），齿轮 ×2，卷筒 ×1
        first = self.belt if scheme == "vbelt" else self.coupling
        gears = self.bevel_pair * self.gear_pair if scheme == "bevel" else self.gear_pair**2
        return first * self.coupling * self.bearing_pair**3 * gears * self.drum


@dataclass
class ConveyorTask:
    """带式输送机设计任务书。"""

    belt_pull: float  # 输送带工作拉力 F，N
    belt_speed: float  # 输送带速度 v，m/s
    drum_diameter: float  # 卷筒直径 D，m
    life_hours: float = 2 * 8 * 300 * 10  # 两班制、每年 300 天、10 年
    sync_speed_rpm: float = 1500
    efficiencies: Efficiencies = field(default_factory=Efficiencies)
    ratio_split: float = 1.3  # i1 = sqrt(ratio_split · i)
    scheme: str = "coupling"  # coupling：电动机直连；vbelt：电动机经 V 带传动；bevel：圆锥-圆柱齿轮减速器；worm：蜗杆减速器；
    # single：V 带 + 一级圆柱齿轮减速器
    belt_ratio: float | None = None  # V 带传动比（推荐 2～4，宜小于齿轮传动比）；不给出时 vbelt 取 2.5，single 按 belt_ratio_single 分配


@dataclass
class ShaftState:
    name: str
    power: float  # W
    speed_rpm: float
    torque: float  # N·m


@dataclass
class Kinematics:
    task: ConveyorTask
    work_power: float  # W，工作机所需功率 Pw = F v
    eta_total: float
    required_power: float  # W，电动机所需功率 Pd = Pw / η
    motor: standards.Motor
    drum_speed_rpm: float
    total_ratio: float
    i_high: float
    i_low: float
    shafts: list[ShaftState]
    i_belt: float = 1.0

    @property
    def reducer_ratio(self) -> float:
        return self.total_ratio / self.i_belt


def torque_from_power(power: float, speed_rpm: float) -> float:
    """T = P / ω，ω = 2πn/60。"""
    return power / (2 * math.pi * speed_rpm / 60)


def drum_speed(belt_speed: float, drum_diameter: float) -> float:
    """卷筒转速 n = 60 v / (π D)，r/min。"""
    return 60 * belt_speed / (math.pi * drum_diameter)


def split_ratio_bevel(i_total: float) -> tuple[float, float]:
    """圆锥-圆柱齿轮减速器：锥齿轮传动比 i1 ≈ 0.25 i，且不大于 3（避免大锥齿轮过大），i2 = i / i1。"""
    i1 = min(0.25 * i_total, 3.0)
    return i1, i_total / i1


def belt_ratio_single(i_total: float) -> float:
    """V 带 + 一级齿轮：指导书推荐 V 带 i = 2～4、一级圆柱齿轮 i = 3～5，且带传动比宜小于齿轮传动比。
    取齿轮传动比约 4，即 i带 = i/4，限制在 2～4 之间。"""
    return min(max(i_total / 4, 2.0), 4.0)


def split_ratio(i_total: float, k: float = 1.3) -> tuple[float, float]:
    """展开式二级减速器传动比分配：i1 = √(k·i)，i2 = i / i1，k 取 1.3–1.5。"""
    i1 = math.sqrt(k * i_total)
    return i1, i_total / i1


def solve(task: ConveyorTask, i_belt: float | None = None, i_high: float | None = None) -> Kinematics:
    """i_belt 为 V 带的实际传动比（带轮直径圆整后），不给出时取任务书的预定值；
    i_high 指定高速级传动比（不给出时按经验分配）。"""
    eff = task.efficiencies
    if task.scheme == "worm":
        return _solve_worm(task)
    if task.scheme == "single":
        return _solve_single(task, i_belt)
    vbelt = task.scheme == "vbelt"
    i_b = (i_belt or task.belt_ratio or 2.5) if vbelt else 1.0
    pw = task.belt_pull * task.belt_speed
    eta = eff.total(task.scheme)
    pd = pw / eta
    motor = standards.select_motor(pd, task.sync_speed_rpm)
    nw = drum_speed(task.belt_speed, task.drum_diameter)
    i = motor.speed_rpm / nw
    if i_high:
        i1, i2 = i_high, i / i_b / i_high
    elif task.scheme == "bevel":
        i1, i2 = split_ratio_bevel(i / i_b)
    else:
        i1, i2 = split_ratio(i / i_b, task.ratio_split)

    # 按电动机所需功率 Pd（而不是额定功率）计算各轴功率，这是课程设计的通常做法
    p0 = pd
    p1 = p0 * (eff.belt if vbelt else eff.coupling)
    p2 = p1 * eff.bearing_pair * (eff.bevel_pair if task.scheme == "bevel" else eff.gear_pair)
    p3 = p2 * eff.bearing_pair * eff.gear_pair
    p4 = p3 * eff.bearing_pair * eff.coupling
    n0 = motor.speed_rpm
    n1 = n0 / i_b
    speeds = [n0, n1, n1 / i1, n1 / i1 / i2, n1 / i1 / i2]
    names = ["电动机轴", "Ⅰ轴（高速轴）", "Ⅱ轴（中间轴）", "Ⅲ轴（低速轴）", "卷筒轴"]
    shafts = [
        ShaftState(nm, p, n, torque_from_power(p, n))
        for nm, p, n in zip(names, [p0, p1, p2, p3, p4], speeds)
    ]
    return Kinematics(task, pw, eta, pd, motor, nw, i, i1, i2, shafts, i_b)


def worm_starts_estimate_eta(i: float) -> float:
    """按传动比对应的蜗杆头数初估蜗杆传动效率（含搅油损失）。课程设计指导书的常用估计值：
    z1 = 1 取 0.70～0.75，z1 = 2 取 0.75～0.82，z1 = 4 取 0.87～0.92。"""
    return 0.75 if i > 30 else 0.80 if i > 13.5 else 0.87


def _solve_single(task: ConveyorTask, i_belt: float | None) -> Kinematics:
    """V 带 + 一级圆柱齿轮减速器：总传动比 = V 带 × 齿轮。"""
    eff = task.efficiencies
    pw = task.belt_pull * task.belt_speed
    eta = eff.total("single")
    pd = pw / eta
    motor = standards.select_motor(pd, task.sync_speed_rpm)
    nw = drum_speed(task.belt_speed, task.drum_diameter)
    i = motor.speed_rpm / nw
    i_b = i_belt or task.belt_ratio or belt_ratio_single(i)
    i1 = i / i_b
    p0 = pd
    p1 = p0 * eff.belt
    p2 = p1 * eff.bearing_pair * eff.gear_pair
    p3 = p2 * eff.bearing_pair * eff.coupling
    n0 = motor.speed_rpm
    n1 = n0 / i_b
    speeds = [n0, n1, n1 / i1, n1 / i1]
    names = ["电动机轴", "Ⅰ轴（高速轴）", "Ⅱ轴（低速轴）", "卷筒轴"]
    shafts = [ShaftState(nm, p, n, torque_from_power(p, n)) for nm, p, n in zip(names, [p0, p1, p2, p3], speeds)]
    return Kinematics(task, pw, eta, pd, motor, nw, i, i1, 1.0, shafts, i_b)


def _solve_worm(task: ConveyorTask) -> Kinematics:
    """蜗杆减速器：总传动比全部由蜗杆传动承担。task.efficiencies.worm_pair 为蜗杆传动效率（初估或实际值）。"""
    eff = task.efficiencies
    pw = task.belt_pull * task.belt_speed
    eta = eff.total("worm")
    pd = pw / eta
    motor = standards.select_motor(pd, task.sync_speed_rpm)
    nw = drum_speed(task.belt_speed, task.drum_diameter)
    i = motor.speed_rpm / nw
    p0 = pd
    p1 = p0 * eff.coupling
    p2 = p1 * eff.bearing_pair * eff.worm_pair
    p3 = p2 * eff.bearing_pair * eff.coupling
    n0 = motor.speed_rpm
    speeds = [n0, n0, n0 / i, n0 / i]
    names = ["电动机轴", "Ⅰ轴（蜗杆轴）", "Ⅱ轴（蜗轮轴）", "卷筒轴"]
    shafts = [ShaftState(nm, p, n, torque_from_power(p, n)) for nm, p, n in zip(names, [p0, p1, p2, p3], speeds)]
    return Kinematics(task, pw, eta, pd, motor, nw, i, i, 1.0, shafts, 1.0)


def with_actual_ratios(kin: Kinematics, ratios: tuple[float, ...]) -> Kinematics:
    """按已选齿数比重算各轴 n、T；功率和初选传动比分配保留用于说明书对照。

    n后=n前/u，T=P/(2πn/60)。末轴为联轴器后的卷筒，与输出轴同速。
    """
    if len(ratios) != len(kin.shafts) - 3:
        raise ValueError("实际齿数比数量与传动级数不一致")
    speeds = [kin.motor.speed_rpm, kin.motor.speed_rpm / kin.i_belt]
    for ratio in ratios:
        speeds.append(speeds[-1] / ratio)
    speeds.append(speeds[-1])
    return replace(kin, shafts=[replace(s, speed_rpm=n, torque=torque_from_power(s.power, n))
                                for s, n in zip(kin.shafts, speeds)])

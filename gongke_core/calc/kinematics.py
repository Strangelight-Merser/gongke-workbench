"""传动装置的总体设计：工作机功率、电动机选择、传动比分配、各轴运动和动力参数。

方案一（coupling）：电动机 → 联轴器 → 展开式二级圆柱齿轮减速器 → 联轴器 → 卷筒；
方案二（vbelt）：电动机 → V 带传动 → 展开式二级圆柱齿轮减速器 → 联轴器 → 卷筒。
轴编号：0 电动机轴，1 高速轴，2 中间轴，3 低速轴，4 卷筒轴。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from gongke_core import standards


@dataclass
class Efficiencies:
    """各传动环节效率，默认值取课程设计指导书常用推荐值。"""

    coupling: float = 0.99  # 弹性联轴器
    bearing_pair: float = 0.99  # 一对滚动轴承
    gear_pair: float = 0.97  # 8 级精度闭式圆柱齿轮
    drum: float = 0.96  # 卷筒（含卷筒轴承）
    belt: float = 0.96  # V 带传动

    def total(self, scheme: str = "coupling") -> float:
        # 联轴器 ×2（V 带方案为 V 带 ×1、联轴器 ×1），轴承 ×3 对（减速器三根轴），齿轮 ×2，卷筒 ×1
        first = self.belt if scheme == "vbelt" else self.coupling
        return first * self.coupling * self.bearing_pair**3 * self.gear_pair**2 * self.drum


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
    scheme: str = "coupling"  # coupling：电动机直连；vbelt：电动机经 V 带传动
    belt_ratio: float = 2.5  # V 带传动比（推荐 2～4，宜小于齿轮传动比）


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


def split_ratio(i_total: float, k: float = 1.3) -> tuple[float, float]:
    """展开式二级减速器传动比分配：i1 = √(k·i)，i2 = i / i1，k 取 1.3–1.5。"""
    i1 = math.sqrt(k * i_total)
    return i1, i_total / i1


def solve(task: ConveyorTask, i_belt: float | None = None) -> Kinematics:
    """i_belt 为 V 带的实际传动比（带轮直径圆整后），不给出时取任务书的预定值。"""
    eff = task.efficiencies
    vbelt = task.scheme == "vbelt"
    i_b = (i_belt or task.belt_ratio) if vbelt else 1.0
    pw = task.belt_pull * task.belt_speed
    eta = eff.total(task.scheme)
    pd = pw / eta
    motor = standards.select_motor(pd, task.sync_speed_rpm)
    nw = drum_speed(task.belt_speed, task.drum_diameter)
    i = motor.speed_rpm / nw
    i1, i2 = split_ratio(i / i_b, task.ratio_split)

    # 按电动机所需功率 Pd（而不是额定功率）计算各轴功率，这是课程设计的通常做法
    p0 = pd
    p1 = p0 * (eff.belt if vbelt else eff.coupling)
    p2 = p1 * eff.bearing_pair * eff.gear_pair
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

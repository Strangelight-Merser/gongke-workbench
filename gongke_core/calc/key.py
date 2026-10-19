"""普通平键（A 型，圆头）的选型与挤压强度校核。"""

from __future__ import annotations

from dataclasses import dataclass

from gongke_core import standards


@dataclass
class KeyCheck:
    location: str
    d: float
    size: standards.KeySize
    length: float  # 键长 L
    count: int  # 1 或 2（双键按 1.5 个键计算）
    sigma_p: float
    sigma_allow: float

    @property
    def working_length(self) -> float:
        """A 型键工作长度 l = L − b。"""
        return self.length - self.size.b

    @property
    def ok(self) -> bool:
        return self.sigma_p <= self.sigma_allow


def crush_stress(torque: float, d: float, h: float, l: float, count: int = 1) -> float:
    """挤压应力 σp = 2T / (k l d)，k = 0.5h；双键按 1.5 倍承载能力计。"""
    factor = 1.0 if count == 1 else 1.5
    return 2 * torque / (0.5 * h * l * d) / factor


def select(location: str, torque: float, d: float, hub_length: float,
           sigma_allow: float = 110e6, end_clearance: float = 5e-3) -> KeyCheck:
    """按轴径选键宽键高，按轮毂长度取不超过 (轮毂长 − 5 mm) 的最长标准键长，强度不够时改双键。

    [σp] 对钢制轮毂、轻微冲击取 100–120 MPa。
    """
    size = standards.key_size(d)
    lengths = [L for L in standards.key_lengths() if L <= hub_length - end_clearance + 1e-9]
    if not lengths:
        raise standards.SelectionError(f"{location}：轮毂长度 {hub_length*1e3:.0f} mm 放不下标准平键")
    length = lengths[-1]
    for count in (1, 2):
        s = crush_stress(torque, d, size.h, length - size.b, count)
        if s <= sigma_allow:
            break
    return KeyCheck(location, d, size, length, count, s, sigma_allow)

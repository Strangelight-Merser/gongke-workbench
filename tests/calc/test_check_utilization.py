"""校核利用率：≤ 型为 实际/许用，≥ 型为 要求/实际（定义式，无需查表）。"""

import json
import re

import pytest

from gongke_core import api


@pytest.mark.parametrize("scheme", list(api.SCHEMES))
def test_utilization_agrees_with_conclusion(scheme):
    s = api.design(api.example_task(scheme))
    json.dumps(s, allow_nan=False)  # 桌面协议拒绝 NaN/Infinity
    for c in s["checks"]:
        u = c.get("utilization")
        if u is None:
            continue
        assert u > 0, c
        assert c["ok"] == (u <= 1 + 1e-9), c


def test_contact_stress_ratio_matches_detail():
    # 由说明文字中的 σH 与 [σH] 反算，与利用率一致（文字保留一位小数）
    s = api.design(api.example_task("coupling"))
    for c in s["checks"]:
        if c["item"].endswith("齿面接触疲劳强度"):
            actual, allow = map(float, re.findall(r"= ([\d.]+) MPa", c["detail"]))
            assert c["utilization"] == pytest.approx(actual / allow, abs=1e-3)

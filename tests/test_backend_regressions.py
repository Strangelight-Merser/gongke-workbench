"""WorkBuddy 反馈回归：输入契约、MCP 报错和中心距圆整边界。"""
import math

import pytest

from gongke_core import api, mcp_server, standards
from gongke_core.calc import gear


@pytest.mark.parametrize('beta', [8, 14, 19, 20])
def test_rounded_center_preserves_geometry_and_strength(beta):
    # 濮良贵《机械设计》第八版第 10 章：a=mn(z1+z2)/(2cosβ)。
    # 不以“成功返回”代替几何、结构下限和最终强度校核。
    p = gear.design(gear.GearPairInput('边界回归', 26.75, 1440, 5.29, 48000,
                                     beta_deg=beta, min_d1=0.045))
    assert p.a / 0.005 == pytest.approx(round(p.a / 0.005))
    assert 8 - 1e-8 <= math.degrees(p.beta) <= 20 + 1e-8
    assert p.a == pytest.approx(p.mn * (p.z1 + p.z2) / (2 * math.cos(p.beta)))
    assert p.d1 >= 0.045 - 1e-12
    assert p.check.ok


@pytest.mark.parametrize('scheme', ['coupling', 'single'])
def test_twenty_degrees_through_agent_entry(scheme):
    task = api.example_task(scheme)
    for stage in task['gears'].values():
        stage['beta_deg'] = 20
    assert api.validate(task) == []
    assert api.design(task)['ok']


def test_motor_schema_matches_recorded_data():
    speeds = api.task_schema()['properties']['motor_sync_speed_rpm']['enum']
    assert speeds == sorted({m.sync_speed_rpm for m in standards.motors()})
    task = api.example_task()
    task['motor_sync_speed_rpm'] = 3000
    assert any('motor_sync_speed_rpm' in e for e in api.validate(task))
    with pytest.raises(standards.SelectionError, match='未收录.*3000.*1000 / 1500'):
        standards.select_motor(4000, 3000)
    with pytest.raises(standards.SelectionError, match='当前表最大'):
        standards.select_motor(1e9, 1500)


@pytest.mark.parametrize('kind,params,expected', [
    ('motor', {'sync_rpm': 3000}, '未收录同步转速 3000'),
    ('key', {}, '缺少参数 shaft_d_mm'),
    ('bearing', {}, '缺少参数 bore_mm'),
    ('form_factors', {}, '缺少参数 zv'),
])
def test_lookup_errors_reach_mcp_client(kind, params, expected):
    result = mcp_server.Server().handle({
        'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
        'params': {'name': 'lookup_standard', 'arguments': {'kind': kind, 'params': params}},
    })['result']
    assert result['isError']
    assert expected in result['content'][0]['text']

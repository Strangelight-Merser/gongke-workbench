"""国标数据交叉校验：字段齐全、尺寸关系自洽、文件头注明标准号。"""

from pathlib import Path

import pytest

from gongke_core import standards


def test_every_data_file_names_its_source():
    for p in Path(standards.data_dir()).rglob("*.yaml"):
        head = p.read_text(encoding="utf-8").splitlines()[0]
        assert head.startswith(("# 标准号", "# 来源")), p.name


def test_bearings_dimensions_consistent():
    bs = standards.deep_groove_ball_bearings()
    for b in bs:
        assert b.D > b.d and b.B < (b.D - b.d)
        assert b.Cr > b.C0r * 0.9  # 深沟球轴承 Cr 一般大于 C0r
        # 代号后两位 ×5 = 内径（04 及以上）
        assert int(b.designation[2:]) * 5 == pytest.approx(b.d * 1e3)
    # 同一内径 03 系列比 02 系列承载能力大
    for d in {b.d for b in bs}:
        same = standards.bearings_with_bore(d)
        assert [x.series for x in same] == sorted(x.series for x in same)


def test_key_table_contiguous():
    rows = standards.load("standards/GB-T_1095-2003_flat_keys.yaml")["sizes"]
    for a, b in zip(rows, rows[1:]):
        assert a[1] == b[0]  # 区间首尾相接
        assert b[2] >= a[2]  # 键宽单调不减
        assert b[4] < b[3]  # 轴槽深小于键高


def test_motor_speed_below_sync():
    for m in standards.motors():
        assert m.speed_rpm < m.sync_speed_rpm


def test_modules_increasing():
    m = standards.standard_modules(1)
    assert m == sorted(m)


def test_select_motor_picks_smallest_sufficient():
    m = standards.select_motor(4.1e3, 1500)
    assert m.power == pytest.approx(5.5e3)
    with pytest.raises(standards.SelectionError):
        standards.select_motor(1e6, 1500)

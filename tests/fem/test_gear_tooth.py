"""齿根应力二维有限元模型与教材 YFa·YSa 对照（需要 ccx 和 gmsh，没有时跳过）。

YFa、YSa 查表值见 data/textbook/gear_form_factors.yaml（濮良贵《机械设计》第八版表 10-5）。
教材的 YSa 由经验公式得到，公开文献中二维有限元齿根应力通常比它低几个百分点；这里要求相差在 10% 以内。
"""

from pathlib import Path

import pytest

from gongke_core import standards
from gongke_core.fem import ccx, gear_tooth


def _available() -> bool:
    try:
        ccx.check_version()
        gear_tooth.find_gmsh()
        return True
    except (ccx.CcxNotFound, gear_tooth.GmshNotFound):
        return False


pytestmark = pytest.mark.skipif(not _available(), reason="没有 CalculiX ccx ≥ 2.21 或 gmsh")


@pytest.mark.parametrize("z", [20, 50])
def test_root_stress_close_to_textbook(tmp_path: Path, z):
    r = gear_tooth.solve(z, tmp_path)
    yfa, ysa = standards.form_factors(z)
    assert r.yfs_fem == pytest.approx(yfa * ysa, rel=0.10)
    assert r.point[0] > 0  # 最大拉应力在受载一侧（右齿廓）的过渡曲线上
    assert 0.9 * (z / 2 - 1.25) < r.point[1] < z / 2 - 0.5


def test_fewer_teeth_higher_root_stress(tmp_path: Path):
    assert gear_tooth.solve(17, tmp_path, "a").yfs_fem > gear_tooth.solve(60, tmp_path, "b").yfs_fem

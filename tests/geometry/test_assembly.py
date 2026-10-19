"""示例任务书的完整装配体：能导出 STEP，再读回来零件数一致，零件间无明显干涉。"""

from pathlib import Path

import pytest

bd = pytest.importorskip("build123d")

from gongke_core import design  # noqa: E402
from gongke_core.geometry import assembly  # noqa: E402

EXAMPLE = Path(__file__).resolve().parents[2] / "examples" / "conveyor_basic.yaml"


@pytest.fixture(scope="module")
def result():
    return design.run(design.ReducerTask.from_yaml(EXAMPLE))


def test_export_and_reimport(result, tmp_path):
    path = tmp_path / "asm.step"
    shapes = assembly.export(result, path, with_housing=True)
    assert all(s.is_valid for s in shapes.values())
    back = bd.import_step(str(path))
    assert len(back.solids()) >= len(shapes)


def test_gears_do_not_hit_other_shafts(result):
    shapes = assembly.build(result, with_housing=False)
    high_gear = shapes["高速级大齿轮"]
    low_shaft = shapes["Ⅲ轴（低速轴）"]
    assert high_gear.intersect(low_shaft) is None or high_gear.intersect(low_shaft).volume < 1e-6

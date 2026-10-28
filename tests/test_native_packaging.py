"""原生轴安装资源必须脱离源码目录仍可读取。"""

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_independent_install_contains_native_resources(tmp_path):
    spec = importlib.util.spec_from_file_location("install_workbench", ROOT / "tools/install_freecad_workbench.py")
    installer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(installer)
    target = installer.install(tmp_path / "Mod")
    assert not target.is_symlink()
    assert (target / "package.xml").is_file()
    assert (target / "freecad/gongke/init_gui.py").is_file()
    assert not (target / "InitGui.py").exists()
    assert (target / "freecad/gongke/resources/icons/gongke.svg").is_file()
    for relative in ("README.md", "docs/agent-api.md", "docs/assistant-workflow.md",
                     "docs/architecture.md", "docs/drawing-checklist.md",
                     "examples/existing_shaft_conditions.json", "docs/images/freecad_assembly.png"):
        assert (target / relative).read_bytes() == (ROOT / relative).read_bytes()
    expected = json.loads((ROOT / "examples/native_shaft.json").read_text(encoding="utf-8"))
    code = """from importlib.resources import files
import gongke_core, json
from gongke_core import api, course_shaft
course = course_shaft.from_design(api._run(api.example_task('coupling')))
print(json.dumps({'module':gongke_core.__file__, 'sample':json.loads(files('gongke_core').joinpath('resources/native_shaft.json').read_text(encoding='utf-8')), 'course_segment_count':len(course['segments']), 'course_fz_n':course['loads'][0]['fz_n']}))
"""
    env = {**os.environ, "PYTHONPATH": str(target)}
    proc = subprocess.run([sys.executable, "-c", code], cwd=tmp_path, env=env,
                          capture_output=True, text=True, check=True)
    result = json.loads(proc.stdout)
    assert Path(result["module"]).is_relative_to(target)
    assert result["sample"] == expected
    assert result["course_segment_count"] == 7 and result["course_fz_n"] != 0
    with pytest.raises(FileExistsError):
        installer.install(tmp_path / "Mod")

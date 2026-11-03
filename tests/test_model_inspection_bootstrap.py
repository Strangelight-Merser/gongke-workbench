"""用旧安装目录及模块缓存复现原生验收的导入冲突；不声称运行了 CAD 几何。"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tests/e2e/model_inspection_freecad.py"


@pytest.mark.parametrize("preloaded", [False, True])
def test_acceptance_uses_checkout_despite_old_workbench(tmp_path, preloaded):
    old = tmp_path / "old-install"
    package = old / "freecad/gongke"
    package.mkdir(parents=True)
    (old / "freecad/__init__.py").write_text("")
    (package / "__init__.py").write_text("")
    (package / "bridge.py").write_text("class DocumentState:\n    def __init__(self, results_dir): pass\n")
    for module in ("native_shaft", "native_inspection"):
        (package / (module + ".py")).write_text("OLD_INSTALL = True\n")
    # 用本地SDK替身模拟 FreeCAD 初始化时改变路径、预载旧工作台。
    sdk = tmp_path / "sdk"
    sdk.mkdir()
    (sdk / "FreeCAD.py").write_text(f'''
import sys
sys.path.insert(0, {str(old)!r})
import freecad
if {preloaded!r}:
    from freecad.gongke import bridge, native_shaft, native_inspection
ActiveDocument = None
def addDocumentObserver(state): pass
def listDocuments(): return {{}}
''')
    for module in ("FreeCADGui", "Part", "Sketcher"):
        (sdk / (module + ".py")).write_text("")
    (sdk / "PySide.py").write_text("from types import SimpleNamespace\nQtCore = SimpleNamespace()\n")
    code = r'''
import json, runpy, sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, sys.argv[1])
ns = runpy.run_path(sys.argv[2], run_name="inspection_bootstrap_test")
from freecad.gongke import bridge, native_shaft, native_inspection
from gongke_app import inspection
root = Path(sys.argv[2]).resolve().parents[2]
for module, relative in [(bridge, "freecad/gongke/bridge.py"), (native_shaft, "freecad/gongke/native_shaft.py"),
                         (native_inspection, "freecad/gongke/native_inspection.py"), (inspection, "gongke_app/inspection.py")]:
    assert Path(module.__file__).resolve() == root / relative
assert ns["call"]("model.context")["documents"] == []
state = ns["state"]
# 真实 DocumentState -> native_inspection.dispatch/bound，几何函数单独替身。
shape = SimpleNamespace(isNull=lambda: False)
obj = SimpleNamespace(Name="Imported", Shape=shape)
doc = SimpleNamespace(Name="Fixture", getObject=lambda name: obj if name == obj.Name else None)
bridge.App.listDocuments = lambda: {doc.Name: doc}
sid = state._session_for_document(doc)
reference = {"host_instance": state.host_instance, "document_id": sid, "revision": 0, "configuration": ""}
plane = {"origin": [0,0,.01], "normal": [0,0,1]}
native_inspection.inspect = lambda target, ref: {"method": "inspect", "object": target.Name, "document": ref}
native_inspection.section = lambda target, ref, plane: {"method": "section", "object": target.Name, "document": ref, "plane": plane}
args = {"document": reference, "object_ref": obj.Name}
assert ns["call"]("model.inspect", **args)["object"] == obj.Name
assert ns["call"]("model.section", **args, plane=plane)["plane"] == plane
state.slotChangedObject(SimpleNamespace(Document=doc), "Length")
try:
    ns["call"]("model.inspect", **args)
except ValueError as error:
    assert "修订" in str(error)
else:
    raise AssertionError("旧修订未拒绝")
print(json.dumps({"bootstrap": "passed", "preloaded_modules_replaced": True}))
'''
    result = subprocess.run([sys.executable, "-c", code, str(sdk), str(SCRIPT)], cwd=tmp_path,
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout.splitlines()[-1])["bootstrap"] == "passed"

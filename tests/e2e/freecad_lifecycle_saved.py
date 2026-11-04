"""真实 FreeCAD：已保存文档退出；文件信号只存在于本轮测试宏中。"""
import json
import os
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.owned_processes import OwnedProcesses
from gongke_app.freecad_lifecycle import FreeCADLifecycle
from gongke_core.host_session import process_identity

output = Path(tempfile.mkdtemp(prefix="gongke-lifecycle-saved-"))
os.environ["GONGKE_FREECAD_SESSION"] = str(output / "session.json")
macro = output / "saved.FCMacro"
# 不增加产品任意执行入口：由自建进程的启动宏构造独立验收文档。
macro.write_text(f'''import sys, freecad
sys.path.insert(0, {str(ROOT)!r})
freecad.__path__.insert(0, {str(ROOT / 'freecad')!r})
for name in list(sys.modules):
    if name == 'freecad.gongke' or name.startswith('freecad.gongke.'): del sys.modules[name]
if hasattr(freecad, 'gongke'): del freecad.gongke
import FreeCAD as App, FreeCADGui as Gui
from freecad.gongke.bridge import start
doc = App.newDocument('SavedFixture')
doc.addObject('Part::Box', 'Box')
doc.recompute()
doc.saveAs({str(output / 'saved.FCStd')!r})
Gui.getDocument(doc.Name).save()
start()
''')
owned = OwnedProcesses()
try:
    env = {key: value for key, value in os.environ.items() if key.upper() in {"HOME", "PATH", "TMPDIR", "USER", "LANG", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "APPDATA", "LOCALAPPDATA", "USERPROFILE"}}
    env.update(GONGKE_FREECAD_SESSION=str(output / "session.json"), GONGKE_FREECAD_MANAGED="1")
    with (output / "freecad.log").open("w") as log:
        child = owned.spawn([os.environ.get("GONGKE_FREECAD_EXE", "/Applications/FreeCAD.app/Contents/MacOS/FreeCAD"), str(macro)], env=env, stdout=log, stderr=log)
    deadline = time.monotonic() + 40
    while not (output / "session.json").exists():
        assert child.poll() is None
        if time.monotonic() > deadline: raise TimeoutError("宿主未就绪")
        time.sleep(.1)
    manager = FreeCADLifecycle()
    assert manager.connect()["pid"] == child.pid
    result = manager.close()
    assert result == {"closed": True, "documents": []}, result
    assert child.wait(timeout=15) == 0
    assert process_identity(child.pid) is None
    evidence = {"pid": child.pid, "saved_document_closed": True, "exit_code": child.returncode}
    (output / "result.json").write_text(json.dumps(evidence))
    print(json.dumps({"output": str(output), **evidence}))
finally:
    owned.close()

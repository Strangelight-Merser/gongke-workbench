"""FreeCAD 自带 Python 的无窗口读取契约检查；不连接 GUI 或其他实例。"""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.append('/Applications/FreeCAD.app/Contents/Resources/lib')
import FreeCAD as App
import Part
import Sketcher
import freecad
sys.path.insert(0, str(ROOT))
freecad.__path__ = [str(ROOT / 'freecad'), *freecad.__path__]
for name in list(sys.modules):
    if name == 'freecad.gongke' or name.startswith('freecad.gongke.'):
        del sys.modules[name]
from freecad.gongke.bridge import DocumentState
from freecad.gongke import native_inspection

out = ROOT / 'out/live-model-validation'
out.mkdir(parents=True, exist_ok=True)
state = DocumentState(out / 'native-read')
doc = App.newDocument('LiveDisplayReadTest')
try:
    body = doc.addObject('PartDesign::Body', 'Body')
    sketch = doc.addObject('Sketcher::SketchObject', 'Sketch')
    body.addObject(sketch)
    sketch.addGeometry(Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), 10), False)
    doc.recompute()
    reference = native_inspection.document_ref(state, doc)
    outline = state.inspect_host('model.inspect', {'document': reference, 'object_ref': sketch.Name})
    assert outline['edges'] and outline['edges'][0]['radius'] == .01, outline
    pad = body.newObject('PartDesign::Pad', 'Pad')
    pad.Profile = sketch
    pad.Length = 8
    doc.recompute()
    reference = native_inspection.document_ref(state, doc)
    solid = state.inspect_host('model.inspect', {'document': reference, 'object_ref': body.Name})
    assert {'Body', 'Sketch', 'Pad'} <= {f['native_ref'] for f in solid['features']}, solid
    assert solid['solid_count'] == 1, solid
    assert all(len(e['samples']) == 17 for e in solid['edges'])
    (out / 'native-read.json').write_text(json.dumps({'freecad_version': App.Version(), 'source': str(Path(native_inspection.__file__).resolve()), 'outline': outline, 'solid': solid}, ensure_ascii=False, indent=2), encoding='utf-8')
    print('PASS: 原生草图轮廓、Body 特征树、世界坐标边读取；无 GUI、无 MCP 链路')
finally:
    App.closeDocument(doc.Name)

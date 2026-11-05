"""FreeCAD 自带 Python：只读采集已有原生模型，或创建自绘合成试件。见 docs/independent-drawing-check.md。"""
import argparse
import hashlib
import json
from pathlib import Path
import runpy
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if sys.platform == 'darwin':
    sys.path.append('/Applications/FreeCAD.app/Contents/Resources/lib')
import FreeCAD as App
import Part
import freecad
sys.path.insert(0, str(ROOT))
freecad.__path__ = [str(ROOT/'freecad'), *freecad.__path__]
for name in list(sys.modules):
    if name == 'freecad.gongke' or name.startswith('freecad.gongke.'):
        del sys.modules[name]
from freecad.gongke import native_inspection
assert Path(native_inspection.__file__).resolve() == ROOT/'freecad/gongke/native_inspection.py'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--model', type=Path)
    source.add_argument('--synthetic', choices=['good', 'bad'])
    parser.add_argument('--object-ref')
    parser.add_argument('--plane', type=float, nargs=3, required=True)
    parser.add_argument('--normal', type=float, nargs=3, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    digest = hashlib.sha256(args.model.read_bytes()).hexdigest() if args.model else None
    if args.model:
        doc = App.openDocument(str(args.model.resolve()))
        obj = doc.getObject(args.object_ref) if args.object_ref else None
        if obj is None:
            raise ValueError('必须明确指定已有模型的 --object-ref')
    else:
        fixture = runpy.run_path(str(ROOT/'tests/fixtures/independent_drawing/generate.py'))
        doc = App.newDocument('SyntheticDrawingCheck')
        loops = fixture['loops'](args.synthetic == 'bad')
        wires = [Part.makePolygon([App.Vector(x, y, 0) for x, y in loop+[loop[0]]]) for loop in loops]
        obj = doc.addObject('PartDesign::Feature', 'Plate')
        obj.Shape = Part.makeFace(wires, 'Part::FaceMakerBullseye').extrude(App.Vector(0, 0, 3))
        doc.recompute()  # 仅合成试件准备阶段；已有模型不重建、不保存。
    try:
        document = {'host_instance': 'isolated-readonly-capture', 'document_id': doc.Name, 'revision': 0, 'configuration': ''}
        plane = {'origin': args.plane, 'normal': args.normal}
        before = obj.Shape.exportBrepToString()
        snapshot = native_inspection.inspect(obj, document)
        section = native_inspection.section(obj, document, plane)
        assert before == obj.Shape.exportBrepToString()
        if args.model:
            assert digest == hashlib.sha256(args.model.read_bytes()).hexdigest()
        result = {'mode': 'native_readonly', 'freecad_version': App.Version(), 'module': native_inspection.__file__,
                  'model_sha256': digest, 'snapshot': snapshot, 'section': section}
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2))
        print(args.out)
    finally:
        App.closeDocument(doc.Name)


if __name__ == '__main__':
    main()

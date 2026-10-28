"""读取实际交付文件，检查清单、数值关系、STEP 实体和 DXF 结构。

用法：python tools/verify_delivery.py 输出目录 [输出目录 ...]
输出 JSON 到 stdout；不修改任何待验文件。此检查不替代制图或工程审查。
"""
import hashlib
import json
import math
import sys
from pathlib import Path

import build123d as bd
import ezdxf


def verify(folder):
    root = Path(folder)
    manifest = json.loads((root / 'manifest.json').read_text())
    summary = json.loads((root / 'summary.json').read_text())
    errors = []
    files = {}
    for rel in manifest['files']:
        path = root / rel
        if not path.is_file() or not path.stat().st_size:
            errors.append(f'缺失或空文件：{rel}')
        else:
            files[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    for s in summary['shaft_states']:
        expected = 1000*s['power_kw']/(2*math.pi*s['speed_rpm']/60)
        if not math.isclose(expected, s['torque_nm'], rel_tol=1e-9):
            errors.append(f"转矩不一致：{s['name']}")
    for g in summary['gears'].values():
        mt = g['mn']/math.cos(math.radians(g['beta_deg']))
        for key, expected in [('d1',mt*g['z1']),('d2',mt*g['z2']),('a',mt*(g['z1']+g['z2'])/2)]:
            if not math.isclose(g[key], expected, rel_tol=1e-9):
                errors.append(f"齿轮几何不一致：{g['name']} {key}")
    shape = bd.import_step(root / 'reducer_assembly.step')
    solids = shape.solids()
    invalid = [i for i, s in enumerate(solids) if not s.is_valid or s.volume <= 0]
    if not solids or invalid:
        errors.append(f'STEP 无效实体：{invalid}')
    drawings = []
    for path in sorted((root/'drawings').glob('*.dxf')):
        doc = ezdxf.readfile(path)
        audit = doc.audit()
        item = {'file':path.name, 'entities':len(doc.modelspace()), 'errors':len(audit.errors), 'fixes':len(audit.fixes)}
        drawings.append(item)
        if item['errors'] or item['fixes'] or not item['entities']:
            errors.append(f'DXF 结构需修复：{path.name}')
    if len(drawings) != len(manifest['drawings']):
        errors.append('DXF 数量与清单不符')
    return {'run_id':manifest['run_id'], 'directory':str(root.resolve()), 'passed':not errors,
            'errors':errors, 'sha256':files, 'step':{'solids':len(solids),'invalid':invalid,'volume_mm3':shape.volume},
            'dxf':drawings, 'scope':'文件完整性、数值恒等关系及几何/文件结构；不含制造可行性或专业认可'}


if __name__ == '__main__':
    results = [verify(folder) for folder in sys.argv[1:]]
    print(json.dumps(results, ensure_ascii=False, indent=2))
    sys.exit(0 if results and all(r['passed'] for r in results) else 1)

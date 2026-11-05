"""用当前产品核验逻辑回放本地宿主采集；可另启 FreeCAD 从原生文档重新采集。学生资料不写进代码。"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from gongke_app.project import Project
from gongke_app.drawing_input import read_drawing
from gongke_app.drawing_check import extract_outline, UnknownDrawing
from gongke_app.inspection import check


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--native-python', help='指定后从原生模型重新采集，不使用历史截面')
    args = parser.parse_args()
    entries = json.loads(args.manifest.read_text())
    results = []
    args.out.mkdir(parents=True, exist_ok=True)
    for entry in entries:
        name = entry['name']
        project = Project.open(entry['project'])
        request = entry['drawing']
        data = read_drawing(project, request['path'], page=request['page'], limit=500)
        # 请求的哈希必须在清单中固定，不能将已变更的图纸悄悄重新接受。
        record = {'name': name, 'mode': 'native_readonly' if args.native_python else 'historical_capture_replay',
                  'drawing_sha256': data['sha256'], 'request': request}
        capture_path = Path(entry['capture']) if entry.get('capture') else None
        if args.native_python and entry.get('model'):
            capture_path = args.out/(name+'-capture.json')
            command = [args.native_python, str(ROOT/'tools/drawing_check_capture.py'), '--model', entry['model'],
                       '--object-ref', entry['object_ref'], '--plane', *map(str, request['plane']['origin']),
                       '--normal', *map(str, request['plane']['normal']), '--out', str(capture_path)]
            completed = subprocess.run(command, capture_output=True, text=True)
            record['capture_command'] = command
            record['capture_exit_code'] = completed.returncode
            if completed.returncode:
                record.update(status='unknown', reason='真实宿主采集失败', stderr=completed.stderr)
                results.append(record)
                continue
        if capture_path and capture_path.exists():
            capture = json.loads(capture_path.read_text())
            record['capture_sha256'] = hashlib.sha256(capture_path.read_bytes()).hexdigest()
            if capture.get('section') and capture.get('snapshot'):
                report = check(capture['snapshot'], [], lambda plane: capture['section'], project, request)
                record.update(status=report['status'], report=report)
            else:
                record.update(status='unknown', reason='历史记录未保存可用截面')
        else:
            record.update(status='unknown', reason='没有可用模型/截面记录')
        if record['status'] == 'unknown':
            try:
                extract_outline(data, request['outline_seed'])
            except UnknownDrawing as exc:
                record['drawing_limitation'] = str(exc)
        if 'expect' in entry:
            record['expected_status'] = entry['expect']
            record['expectation_met'] = entry['expect'] == record['status']
        results.append(record)
    path = args.out/'regression.json'
    path.write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print(json.dumps([{'name': r['name'], 'status': r['status'], 'reason': r.get('reason'),
                       'drawing_limitation': r.get('drawing_limitation')} for r in results], ensure_ascii=False, indent=2))
    print(path)
    return 1 if any(r.get('expectation_met') is False or r.get('capture_exit_code', 0) for r in results) else 0


if __name__ == '__main__':
    raise SystemExit(main())

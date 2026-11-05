"""合成矢量 PDF + FreeCAD 正确/错误实体端到端验收；不读取学生资料。"""
import argparse
import json
from pathlib import Path
import runpy
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from gongke_app.project import Project
from gongke_app.drawing_input import read_drawing
from gongke_app.inspection import check


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--freecad-python', required=True)
    parser.add_argument('--out', type=Path, default=ROOT/'out/independent-drawing-check/synthetic-native')
    args = parser.parse_args()
    project = Project.open(args.out) if (args.out/'gongke-project.json').exists() else Project.create(args.out)
    fixture = runpy.run_path(str(ROOT/'tests/fixtures/independent_drawing/generate.py'))
    fixture['make_pdf'](project.path/'plate.pdf')
    data = read_drawing(project, 'plate.pdf')
    plane = {'origin': [0, 0, .0015], 'normal': [0, 0, 1]}
    request = {'path': 'plate.pdf', 'sha256': data['sha256'], 'page': 1,
               'outline_seed': 'page-1/lines/0', 'plane': plane, 'axes': [1, 2]}
    results = []
    for variant, expected in [('good', 'pass'), ('bad', 'fail')]:
        path = project.path/(variant+'-capture.json')
        subprocess.run([args.freecad_python, str(ROOT/'tools/drawing_check_capture.py'), '--synthetic', variant,
                        '--plane', '0', '0', '.0015', '--normal', '0', '0', '1', '--out', str(path)], check=True)
        capture = json.loads(path.read_text())
        report = check(capture['snapshot'], [], lambda p: capture['section'], project, request)
        assert report['status'] == expected, report
        if variant == 'bad':
            assert report['checks'][0]['missing_or_shifted'] and report['checks'][0]['extra_or_shifted']
        results.append({'variant': variant, 'report': report})
    (project.path/'acceptance.json').write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print('合成原生模型：正确轮廓通过，错误轮廓不符并有定位。')


if __name__ == '__main__':
    main()

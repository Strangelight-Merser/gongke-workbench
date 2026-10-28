"""一次设计的交付清单；输出目录只接收一次运行，失败产物也保留状态。"""
from __future__ import annotations

import json
import hashlib
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

from gongke_core import summary
from gongke_core.task_input import TaskError


def generate(task, out_dir, report_docx=True, drawings=True, step=False,
             full_teeth=False, fem=False, with_housing=True, source_task=None):
    from gongke_core import design
    from gongke_core.report import content, markdown_writer

    parsed = design.ReducerTask.from_dict(task)
    out = Path(out_dir).resolve()
    # CLI 的输入任务书可以位于输出目录，其余已有文件一律保留并拒绝复用。
    source = Path(source_task).resolve() if source_task else None
    if out.exists() and any(p.resolve() != source for p in out.iterdir()):
        raise TaskError(f"输出目录非空：{out}；请为本次运行指定新的目录，已有文件不会覆盖")
    out.mkdir(parents=True, exist_ok=True)
    manifest = out / 'manifest.json'
    result = {'run_id': uuid4().hex, 'out_dir': str(out), 'ok': False,
              'calculation_ok': False, 'exports_complete': False,
              'status': 'running', 'artifacts': {}, 'drawings': [], 'files': [], 'notes': []}
    from gongke_core import standards
    def fingerprint(root, pattern):
        digest = hashlib.sha256()
        for path in sorted(root.rglob(pattern)):
            digest.update(str(path.relative_to(root)).encode())
            digest.update(path.read_bytes())
        return digest.hexdigest()
    result['versions'] = {
        'core_sha256': fingerprint(Path(__file__).parent, '*.py'),
        'data_sha256': fingerprint(standards.data_dir(), '*.yaml'),
    }
    # 独占创建也阻止两个进程同时使用同一目录。
    with manifest.open('x', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    def save():
        manifest.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')

    def artifact(name, action, expected):
        before = {p for p in out.rglob('*') if p.is_file()}
        try:
            value = action()
            missing = [str(p.relative_to(out)) for p in expected if not p.is_file() or p.stat().st_size == 0]
            if missing:
                raise RuntimeError('未生成或为空：' + '、'.join(missing))
        except Exception as exc:
            result['artifacts'][name] = {'status': 'failed', 'error': f'{type(exc).__name__}: {exc}'}
            result['notes'].append(f'{name} 未完成：{exc}')
            return None
        else:
            created = sorted(str(p.relative_to(out)) for p in out.rglob('*') if p.is_file() and p not in before)
            result['artifacts'][name] = {'status': 'complete', 'files': created}
            result['files'].extend(created)
            return value
        finally:
            save()

    try:
        (out / 'task.json').write_text(json.dumps(task, ensure_ascii=False, indent=2), encoding='utf-8')
        (out / 'normalized_task.json').write_text(json.dumps(asdict(parsed), ensure_ascii=False, indent=2), encoding='utf-8')
        result['files'].extend(['task.json', 'normalized_task.json'])
        res = design.run(parsed)
        result['calculation_ok'] = res.ok
        fem_rep = None
        if fem:
            def export_fem():
                from gongke_core.fem import shaft_check
                rep = shaft_check.run(res, out / 'fem')
                (out / 'fem/comparison.md').write_text(shaft_check.to_markdown(rep), encoding='utf-8')
                if rep.gear_note:
                    raise RuntimeError(rep.gear_note)
                return rep
            fem_rep = artifact('fem', export_fem, [out / 'fem/comparison.md'])
        (out / 'summary.json').write_text(json.dumps(summary.summarize(res, fem_rep), ensure_ascii=False, indent=2), encoding='utf-8')
        result['files'].append('summary.json')
        doc = content.build(res, fem=fem_rep)
        artifact('markdown', lambda: markdown_writer.write(doc, out / 'report.md'), [out / 'report.md'])
        if report_docx:
            def export_docx():
                from gongke_core.report import docx_writer
                docx_writer.write(doc, out / 'report.docx')
            artifact('docx', export_docx, [out / 'report.docx'])
        if drawings:
            def export_drawings():
                from gongke_core import drawing, api
                sheets = drawing.build_all(res, out / 'drawings')
                for sh in sheets:
                    if not sh.dxf.is_file() or sh.svg is None or not sh.svg.is_file():
                        raise RuntimeError(f'{sh.name} 缺少 DXF 或 SVG')
                index = [{'name': sh.name, 'number': sh.number, 'size': sh.size,
                          'dxf': sh.dxf.name, 'svg': sh.svg.name} for sh in sheets]
                (out / 'drawings/index.json').write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding='utf-8')
                result['drawing_check'] = api.check_drawings(out / 'drawings')
                if result['drawing_check']['total']:
                    result['notes'].append(f"图纸自动检查发现 {result['drawing_check']['total']} 处问题，需修正")
                return index
            result['drawings'] = artifact('drawings', export_drawings,
                [out / 'drawings/index.json', out / 'drawings/drawings.pdf']) or []
        if step:
            def export_step():
                from gongke_core.geometry import assembly
                assembly.export(res, out / 'reducer_assembly.step', teeth=full_teeth, with_housing=with_housing)
            artifact('step', export_step, [out / 'reducer_assembly.step'])
        result['exports_complete'] = all(a['status'] == 'complete' for a in result['artifacts'].values())
        result['ok'] = (result['calculation_ok'] and result['exports_complete']
                        and result.get('drawing_check', {}).get('total', 0) == 0)
        result['status'] = 'complete' if result['ok'] else 'needs_attention'
        if drawings:
            result['notes'].append('图纸自动检查不替代视觉检查和专业审阅')
    except Exception as exc:
        result['status'] = 'failed'
        result['notes'].append(f'{type(exc).__name__}: {exc}')
    finally:
        result['files'] = sorted(set(result['files'] + ['manifest.json']))
        save()
    return result

"""依据自绘解析试件验证独立核验，禁止引入学生图纸或 robot 坐标。"""
from copy import deepcopy
from pathlib import Path
import runpy

import pytest

from gongke_app import inspection
from gongke_app.drawing_input import read_drawing
from gongke_app.drawing_check import compare_section, extract_outline, UnknownDrawing
from gongke_app.project import Project
from gongke_app.hosts import Hosts
from gongke_app.commands import Commands

FIXTURE = runpy.run_path(str(Path(__file__).parent / 'fixtures/independent_drawing/generate.py'))
DOC = {'host_instance': 'test', 'document_id': 'plate', 'revision': 1, 'configuration': ''}
PLANE = {'origin': [0, 0, .0015], 'normal': [0, 0, 1]}


def section(wrong=False):
    edges = []
    for loop in FIXTURE['loops'](wrong):
        for a, b in zip(loop, loop[1:]+loop[:1]):
            edges.append({'native_ref': f'section.Edge{len(edges)+1}', 'kind': 'line',
                          'start': [a[0]/1000, a[1]/1000, .0015], 'end': [b[0]/1000, b[1]/1000, .0015]})
    return {'document': DOC, 'object_ref': 'Body', 'status': 'ok', 'plane': PLANE, 'edges': edges}


@pytest.fixture
def case(tmp_path):
    project = Project.create(tmp_path/'project')
    FIXTURE['make_pdf'](project.path/'plate.pdf')
    data = read_drawing(project, 'plate.pdf')
    request = {'path': 'plate.pdf', 'sha256': data['sha256'], 'page': 1, 'outline_seed': 'page-1/lines/0',
               'plane': PLANE, 'axes': [1, 2]}
    snapshot = {'document': DOC, 'object_ref': 'Body', 'state': 'ready', 'faces': [], 'edges': [], 'features': []}
    return project, data, request, snapshot


def test_pdf_good_bad_and_location(case):
    project, data, request, snapshot = case
    good = inspection.check(snapshot, [], lambda p: section(), project, request)
    assert good['status'] == 'pass'
    row = good['checks'][0]
    assert row['source_kind'] == 'drawing_geometry'
    assert row['drawing_edge_count'] == 16
    assert row['pt_per_mm'] == 4
    bad = inspection.check(snapshot, [], lambda p: section(True), project, request)
    assert bad['status'] == 'fail'
    row = bad['checks'][0]
    assert row['missing_or_shifted'] and row['extra_or_shifted']
    assert all(abs(e['start'][0]) < .014 for loc in row['actual']['locations'] for e in loc['edges'])


def test_agent_answer_cannot_certify_itself(case):
    project, data, request, snapshot = case
    snapshot['faces'] = [{'native_ref': 'hole', 'kind': 'cylinder', 'radius': .005}]
    condition = {'id': 'self', 'source': '图纸明确标注，已经人工核对', 'measurement': {'kind': 'diameter', 'selectors': [{'native_ref': 'hole'}]},
                 'expected': 10, 'tolerance': 0, 'unit': 'mm'}
    result = inspection.check(snapshot, [condition], project=project)
    assert result['status'] == 'unverified'
    assert result['checks'][0]['source_kind'] == 'agent_defined'
    condition['evidence'] = {'path': 'plate.pdf', 'sha256': data['sha256'], 'page': 1, 'item': 'page-1/text/0'}
    assert inspection.check(snapshot, [condition], project=project)['status'] == 'unknown'
    condition['expected'] = 36
    snapshot['faces'] = [{'native_ref': 'left', 'kind': 'plane', 'point': [0, 0, 0], 'direction': [1, 0, 0]},
                         {'native_ref': 'right', 'kind': 'plane', 'point': [.036, 0, 0], 'direction': [1, 0, 0]}]
    condition['measurement'] = {'kind': 'plane_distance', 'selectors': [{'native_ref': 'left'}, {'native_ref': 'right'}]}
    result = inspection.check(snapshot, [condition], project=project)
    assert result['status'] == 'pass'
    assert result['checks'][0]['evidence']['text'] == '36'
    assert len(result['checks'][0]['evidence']['bbox']) == 4
    condition['evidence']['sha256'] = 'stale'
    assert inspection.check(snapshot, [condition], project=project)['status'] == 'unknown'
    condition.pop('evidence')
    assert inspection.check(snapshot, [condition], lambda p: section(), project, request)['status'] == 'unverified'


def test_reject_hole_seed_stale_cut_wrong_axis_curves_and_empty(case):
    project, data, request, snapshot = case
    for seed in ['page-1/lines/8', 'page-1/text/0']:
        result = compare_section(snapshot, section(), data, {**request, 'outline_seed': seed})
        assert result['status'] == 'unknown'
    for cut in [{**section(), 'document': {**DOC, 'revision': 2}}, {**section(), 'edges': []},
                {**section(), 'edges': [{**section()['edges'][0], 'kind': 'circle'}]}]:
        assert compare_section(snapshot, cut, data, request)['status'] == 'unknown'
    assert compare_section(snapshot, section(), data, {**request, 'axes': [1, 3]})['status'] == 'unknown'
    assert inspection.check(snapshot, [], project=project)['status'] == 'unknown'
    assert inspection.check(snapshot, [], lambda p: section(), project, {**request, 'sha256': 'old'})['status'] == 'unknown'


def test_missing_dimensions_open_geometry_and_raster_are_unknown(case):
    _, data, request, snapshot = case
    missing = {**data, 'items': [r for r in data['items'] if r['source'] != 'page-1/text/1']}
    assert compare_section(snapshot, section(), missing, request)['status'] == 'unknown'
    opened = {**data, 'items': [r for r in data['items'] if r['source'] != 'page-1/lines/9']}
    assert compare_section(snapshot, section(), opened, request)['status'] == 'unknown'
    raster = {**data, 'raster_regions': [{'x0': 100, 'x1': 200, 'top': 100, 'bottom': 200}]}
    assert compare_section(snapshot, section(), raster, request)['status'] == 'unknown'


def test_split_collinear_edge_is_equivalent_and_extra_hole_fails(case):
    _, data, request, snapshot = case
    cut = section()
    edge = cut['edges'].pop(0)
    midpoint = [(a+b)/2 for a, b in zip(edge['start'], edge['end'])]
    cut['edges'] += [{**edge, 'end': midpoint}, {**edge, 'start': midpoint}]
    assert compare_section(snapshot, cut, data, request)['status'] == 'pass'
    cut['edges'].append({'native_ref': 'extra', 'kind': 'line', 'start': [0, 0, .0015], 'end': [.001, 0, .0015]})
    assert compare_section(snapshot, cut, data, request)['status'] == 'fail'


@pytest.mark.parametrize('host', ['freecad', 'sw-test'])
def test_shared_host_command(case, tmp_path, monkeypatch, host):
    project, _, request, snapshot = case
    hosts = Hosts(tmp_path/'hosts')
    def native(method, params):
        return deepcopy(snapshot if method == 'model.inspect' else section(True))
    if host == 'freecad':
        monkeypatch.setattr('gongke_app.hosts.native_client.call', lambda _, **kw: native(kw['command'], kw['params']))
    else:
        monkeypatch.setattr(hosts, 'discover', lambda: [{'host_id': host, 'host': 'solidworks', 'capabilities': list(inspection.NATIVE_METHODS)}])
        monkeypatch.setattr(hosts, '_request', lambda config, method, params: native(method, params))
    result = Commands(hosts).call('host.check', {'host_id': host, 'document': DOC, 'object_ref': 'Body',
                                 'conditions': [], 'drawing': request}, project, allow_writes=False)
    assert result['status'] == 'fail'


def test_hidden_line_unknown_and_inconsistent_scale(case):
    _, data, request, snapshot = case
    hidden = {'source': 'hidden', 'type': 'lines', 'stroke': True, 'linewidth': .35,
              'dash': [[3, 3], 0], 'pts': [[140, 140], [180, 140]], 'x0': 140, 'x1': 180, 'top': 140, 'bottom': 140}
    modified = {**data, 'items': data['items']+[hidden]}
    assert compare_section(snapshot, section(), modified, request)['status'] == 'unknown'
    modified = deepcopy(data)
    next(r for r in modified['items'] if r['source'] == 'page-1/text/1')['text'] = '30'
    assert compare_section(snapshot, section(), modified, request)['status'] == 'unknown'


def test_thinner_hole_must_not_be_silently_omitted(case):
    _, data, request, snapshot = case
    modified = deepcopy(data)
    for row in modified['items']:
        if row['source'] in {f'page-1/lines/{i}' for i in range(8, 12)}:
            row['linewidth'] = .4
    assert compare_section(snapshot, section(), modified, request)['status'] == 'unknown'

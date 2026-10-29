"""Native desktop bridge acceptance in one real FreeCAD GUI process.

Call start(new_output_directory) on the GUI thread. The worker exercises the
same authenticated HTTP bridge as the desktop service; local callbacks only
construct the synthetic drawing, simulate manual edits, and reopen saved files.
Existing projects and test fixtures are never modified.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import queue
import threading
import time
import traceback
import uuid
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
_runs = []


class Run:
    def __init__(self, output):
        from PySide import QtCore
        from freecad.gongke import bridge
        assert Path(bridge.__file__).resolve() == ROOT / 'freecad/gongke/bridge.py', bridge.__file__
        self.output = Path(output).resolve()
        self.output.mkdir(parents=True, exist_ok=True)
        if (self.output / 'result.json').exists():
            raise FileExistsError('Use a fresh output directory to preserve evidence.')
        self.bridge = bridge.start(str(self.output / 'session.json'))
        import FreeCAD as App
        App.addDocumentObserver(self)
        self.calls = queue.Queue()
        self.events = []
        self.checks = []
        self.done = False
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.poll)
        self.timer.start(20)
        self.thread = threading.Thread(target=self.execute, daemon=True, name='desktop-native-acceptance')
        self.thread.start()

    def slotChangedObject(self, obj, prop):
        try:
            value = str(getattr(obj, prop))
        except Exception as exc:
            value = str(exc)
        with (self.output / 'native-changes.jsonl').open('a') as handle:
            handle.write(json.dumps({'object': obj.Name, 'property': prop, 'value': value[:1000],
                                     'at': time.time()}, ensure_ascii=False) + '\n')

    def record(self, kind, payload):
        event = {'sequence': len(self.events) + 1, 'kind': kind, 'payload': payload}
        self.events.append(event)
        with (self.output / 'trace.jsonl').open('a') as handle:
            handle.write(json.dumps(event, ensure_ascii=False, allow_nan=False) + '\n')

    def call(self, method, **params):
        from urllib.request import Request, ProxyHandler, build_opener
        endpoint = json.loads(self.bridge.endpoint.read_text())
        request = Request(endpoint['url'] + '/command',
                          data=json.dumps({'method': method, 'params': params}, allow_nan=False).encode(),
                          headers={'Authorization': 'Bearer ' + endpoint['token'], 'Content-Type': 'application/json'})
        self.record('request', {'method': method, 'params': params})
        with build_opener(ProxyHandler({})).open(request, timeout=35) as response:
            result = json.load(response)
        self.record('response', result)
        if not result['ok']:
            raise ValueError(result['error'])
        return result['result']

    def local(self, action, **params):
        reply = queue.Queue(maxsize=1)
        self.calls.put((action, params, reply))
        ok, result = reply.get(timeout=30)
        self.record('local', {'action': action, 'result': result, 'ok': ok})
        if not ok:
            raise RuntimeError(result)
        return result

    def poll(self):
        while not self.calls.empty():
            action, params, reply = self.calls.get_nowait()
            try:
                reply.put((True, self.perform(action, **params)))
            except Exception:
                reply.put((False, traceback.format_exc()))
        if self.done:
            self.timer.stop()

    def perform(self, action, **params):
        import FreeCAD as App
        import FreeCADGui as Gui
        doc = App.ActiveDocument
        if action == 'document_info':
            context = self.bridge.state.get_project_context()
            return {'path': doc.FileName, 'revision': context['revision'],
                    'dirty': bool(Gui.getDocument(doc.Name).Modified),
                    'states': {obj.Name: list(obj.State) for obj in doc.Objects},
                    'selection': [(item.DocumentName, item.ObjectName, tuple(item.SubElementNames))
                                  for item in Gui.Selection.getSelectionEx()],
                    'documents': sorted(App.listDocuments()),
                    'disk_sha256': hashlib.sha256(Path(doc.FileName).read_bytes()).hexdigest()}
        if action == 'select_face':
            body = next(obj for obj in doc.Objects if hasattr(obj, 'GkEntityId'))
            Gui.Selection.clearSelection()
            Gui.Selection.addSelection(doc.Name, body.Name, 'Face1')
            assert tuple(Gui.Selection.getSelectionEx()[0].SubElementNames) == ('Face1',)
            return {'subelement': 'Face1'}
        if action == 'create_drawing':
            body = next(obj for obj in doc.Objects if hasattr(obj, 'GkEntityId'))
            body.Placement = App.Placement(App.Vector(12, -25, 40), App.Rotation(App.Vector(0, 0, 1), 37))
            doc.recompute()
            Gui.activateWorkbench('TechDrawWorkbench')
            page = doc.addObject('TechDraw::DrawPage', 'ShaftDrawing')
            template = doc.addObject('TechDraw::DrawSVGTemplate', 'DrawingTemplate')
            template.Template = App.getResourceDir() + 'Mod/TechDraw/Templates/Default_Template_A4_Landscape.svg'
            page.Template = template
            view = doc.addObject('TechDraw::DrawViewPart', 'EndView')
            view.Source = [body]
            view.Direction = body.Placement.Rotation.multVec(App.Vector(1, 0, 0))
            view.X, view.Y = 140, 100
            page.addView(view)
            Gui.getDocument(doc.Name).getObject(page.Name).show()
            doc.recompute()
            edge = None
            projection = []
            for _ in range(100):
                Gui.updateGui()
                time.sleep(.03)
                projection = []
                for i in range(len(view.getVisibleEdges())):
                    try:
                        radius = getattr(view.getEdgeByIndex(i).Curve, 'Radius', -1)
                        projection.append({'index': i, 'radius': radius})
                        if math.isclose(radius, 20.0):
                            edge = i
                    except ValueError:
                        projection.append({'index': i, 'pending': True})
                if edge is not None:
                    break
            assert edge is not None, projection
            dim = doc.addObject('TechDraw::DrawViewDimension', 'MiddleDiameter')
            dim.Type = 'Diameter'
            dim.References2D = [(view, (f'Edge{edge}',))]
            page.addView(dim)
            dim.X, dim.Y = 35, 25
            doc.recompute()
            for _ in range(30):
                Gui.updateGui()
                time.sleep(.02)
            return {'page': page.Name, 'view': view.Name, 'dimension': dim.Name,
                    'edge_reference': f'Edge{edge}', 'projection': projection, 'measurement_mm': dim.getRawValue()}
        if action == 'settle':
            for _ in range(35):
                Gui.updateGui()
                time.sleep(.02)
            return {'dimension_mm': doc.getObject('MiddleDiameter').getRawValue(),
                    'pending': [obj.Name for obj in doc.Objects if 'Touched' in obj.State]}
        if action == 'capture':
            Gui.getMainWindow().grab().save(str(self.output / 'native-window.png'))
            return {'window_image': 'native-window.png'}
        if action == 'manual_edit':
            body = next(obj for obj in doc.Objects if hasattr(obj, 'GkEntityId'))
            metadata = json.loads(body.GkMetadata)
            radius = next(item['radius'] for item in metadata['dimensions'] if item['segment_id'] == 'middle')
            index = next(i for i, c in enumerate(body.GkSketch.Constraints) if c.Name == radius)
            doc.openTransaction('Manual desktop acceptance edit')
            body.GkSketch.setDatum(index, App.Units.Quantity(str(params['diameter_mm'] / 2) + ' mm'))
            doc.recompute()
            doc.commitTransaction()
            return {'diameter_mm': params['diameter_mm']}
        if action == 'undo_manual':
            assert doc.UndoNames[0] == 'Manual desktop acceptance edit'
            doc.undo()
            doc.recompute()
            return {'undone': True}
        if action == 'close_reopen':
            filename = doc.FileName
            App.closeDocument(doc.Name)
            new = App.openDocument(filename)
            new.UndoMode = 1
            App.setActiveDocument(new.Name)
            Gui.getDocument(new.Name).getObject('ShaftDrawing').show()
            for _ in range(30):
                Gui.updateGui()
                time.sleep(.02)
            return {'document': new.Name, 'path': new.FileName}
        raise ValueError(action)

    def scene_check(self, label):
        scene = self.call('get_display_scene')
        assert scene['unit'] == 'mm'
        assert len(scene['objects']) == 1, scene['objects']
        mesh = scene['objects'][0]
        assert len(mesh['vertices']) > 20 and len(mesh['triangles']) > 20
        assert all(len(t) == 3 and all(0 <= i < len(mesh['vertices']) for i in t) for t in mesh['triangles'])
        assert all(math.isfinite(v) for point in mesh['vertices'] for v in point)
        assert len(scene['pages']) == 1 and not scene['pages'][0].get('error'), scene['pages']
        svg = scene['pages'][0]['svg']
        assert ET.fromstring(svg).tag.endswith('svg')
        assert len(svg) > 1000
        (self.output / (label + '.svg')).write_text(svg)
        (self.output / (label + '.json')).write_text(json.dumps(scene, ensure_ascii=False, indent=2))
        return scene

    def execute(self):
        started = time.time()
        result = {'ok': False, 'verification_level': 'real_freecad_gui', 'synthetic_fixture': True}
        try:
            snapshot = json.loads((ROOT / 'gongke_core/resources/native_shaft.json').read_text())
            snapshot['entity_id'] = str(uuid.uuid4())
            context = self.call('create_project', snapshot=snapshot)
            identity = {'session_id': context['session_id'], 'entity_id': snapshot['entity_id']}
            drawing = self.local('create_drawing')
            assert math.isclose(drawing['measurement_mm'], 40.0)
            self.call('save_project', session_id=identity['session_id'], path=str(self.output / 'original.FCStd'))
            original_hash = hashlib.sha256((self.output / 'original.FCStd').read_bytes()).hexdigest()
            self.call('save_project', session_id=identity['session_id'], path=str(self.output / 'revision.FCStd'))
            self.local('select_face')
            state_before = self.local('document_info')
            initial_scene = self.scene_check('before')
            assert self.local('document_info') == state_before, 'Display export mutated the source document'
            self.checks.append('real_native_mesh_and_techdraw_svg')
            selected = self.call('select_display_object', session_id=identity['session_id'],
                                 object_name=initial_scene['objects'][0]['id'], expected_revision=initial_scene['revision'])
            assert selected['selection'] == [identity['entity_id']]
            selected_state = self.local('document_info')
            repeated = self.call('get_display_scene')
            assert self.local('document_info') == selected_state, 'Repeated display changed source or selection'
            assert repeated['revision'] == initial_scene['revision']
            self.checks.append('display_selection_maps_to_native_entity')
            self.checks.append('display_preserves_native_revision_dirty_selection_and_original_bytes')
            before = self.call('review_current_object', **identity)
            candidate = self.call('preview_shaft_change', **identity, segment_id='middle', diameter_m=.038)
            assert candidate['can_apply'], candidate
            applied = self.call('apply_change', session_id=identity['session_id'], change_id=candidate['change_id'], operation_id='desktop-native-edit')
            assert applied['applied']
            actual = self.call('read_engineering_object', **identity)
            assert math.isclose(actual['snapshot']['segments'][1]['diameter_m'], .038)
            review = self.call('review_current_object', **identity)
            assert review['content_hash'] == actual['content_hash']
            self.checks.append('preview_native_edit_readback_recalculate')
            self.local('settle')
            scene = self.call('get_display_scene')
            updated = self.call('update_drawing', session_id=identity['session_id'], page_name=drawing['page'], expected_revision=scene['revision'])
            assert updated['updated'], updated
            settled = self.local('settle')
            assert math.isclose(settled['dimension_mm'], 38.0), settled
            scene = self.scene_check('after')
            assert scene['objects'][0]['vertices'] != initial_scene['objects'][0]['vertices']
            capture = self.call('read_revision_context', document_path=str(self.output / 'revision.FCStd'),
                                body_name='GongKeShaft', pages=[drawing['page']])
            (self.output / 'drawing-capture.json').write_text(json.dumps(capture, ensure_ascii=False, indent=2))
            native_dimension = capture['drawing']['pages'][0]['views'][0]['dimensions'][0]
            assert native_dimension['reference_status'] == 'valid'
            assert math.isclose(native_dimension['raw_value'], 38.0)
            self.checks.append('associated_dimension_updates_to_actual_38mm')
            exported = self.call('export_drawing', session_id=identity['session_id'], page_name=drawing['page'],
                                 expected_revision=scene['revision'], path=str(self.output / 'revision.dxf'))
            assert exported['source'] == 'native_techdraw_page'
            assert (self.output / 'revision.dxf').stat().st_size > 100
            assert exported['text_encoding'] == 'dxf_unicode_escape'
            assert '\\U+2300' in (self.output / 'revision.dxf').read_text(encoding='ascii')
            self.checks.append('native_techdraw_dxf_export')
            try:
                self.call('export_drawing', session_id=identity['session_id'], page_name=drawing['page'],
                          expected_revision=self.call('get_display_scene')['revision'], path=str(self.output / 'revision.dxf'))
                raise AssertionError('Existing export overwritten')
            except ValueError as exc:
                assert '尚不存在' in str(exc)
            stale = self.call('preview_shaft_change', **identity, segment_id='middle', diameter_m=.036)
            self.local('manual_edit', diameter_mm=37)
            try:
                self.call('select_display_object', session_id=identity['session_id'],
                          object_name=scene['objects'][0]['id'], expected_revision=scene['revision'])
                raise AssertionError('Stale display selection accepted')
            except ValueError as exc:
                assert '过期' in str(exc)
            try:
                self.call('apply_change', session_id=identity['session_id'], change_id=stale['change_id'], operation_id='must-reject-stale')
                raise AssertionError('Stale candidate accepted')
            except ValueError as exc:
                assert '过期' in str(exc)
            manual = self.call('read_engineering_object', **identity)
            assert manual['analysis']['applicability'] == 'stale'
            self.local('undo_manual')
            self.local('settle')
            self.checks.append('manual_edit_invalidates_results_and_native_undo_restores')
            self.call('save_project', session_id=identity['session_id'])
            self.local('close_reopen')
            context = self.call('get_project_context')
            assert context['session_id'] != identity['session_id']
            identity['session_id'] = context['session_id']
            reopened = self.call('read_engineering_object', **identity)
            assert math.isclose(reopened['snapshot']['segments'][1]['diameter_m'], .038)
            final_scene = self.scene_check('reopened')
            self.local('capture')
            assert hashlib.sha256((self.output / 'original.FCStd').read_bytes()).hexdigest() == original_hash
            self.checks.append('save_reopen_native_model_drawing_and_original_preserved')
            import FreeCAD as App
            result.update(ok=True, freecad_version=App.Version(), checks=self.checks,
                          source_sha256={name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                                         for name in ('freecad/gongke/bridge.py', 'freecad/gongke/native_drawing.py', 'freecad/gongke/native_display.py', 'freecad/gongke/native_export.py',
                                                      'freecad/gongke/native_shaft.py', 'tests/e2e/desktop_native_flow.py')},
                          original_sha256=original_hash, input_diameter_mm=40, output_diameter_mm=38,
                          mesh_vertices=len(final_scene['objects'][0]['vertices']),
                          mesh_triangles=len(final_scene['objects'][0]['triangles']),
                          review=review['result'], exported=exported)
        except Exception:
            result.update(error=traceback.format_exc(), checks=self.checks)
        finally:
            result['elapsed_seconds'] = time.time() - started
            (self.output / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
            self.done = True


def start(output):
    run = Run(output)
    _runs.append(run)
    return run

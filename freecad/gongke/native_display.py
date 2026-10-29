"""Render TechDraw previews from a disposable native copy, never the working file.

FreeCAD 1.1.4 SVG export rewrites template Width/Height/Orientation even when
values do not change. Rendering the live page therefore dirties the engineering
document. All projection and export side effects here belong to the copy.
This helper must run on the GUI thread; its caller must prevent bridge reentry.
"""
from __future__ import annotations

from pathlib import Path
import tempfile
import time
import xml.etree.ElementTree as ET


def _selection(Gui):
    return [(item.DocumentName, item.ObjectName, tuple(item.SubElementNames))
            for item in Gui.Selection.getSelectionEx()]


def _has_content(svg):
    root = ET.fromstring(svg)
    if root.tag.rsplit('}', 1)[-1] != 'svg':
        return False
    content = next((node for node in root.iter() if node.get('id') == 'DrawingContent'), None)
    if content is None:
        return False
    return any(node.tag.rsplit('}', 1)[-1] in {'path', 'line', 'circle', 'ellipse', 'polygon', 'polyline', 'text', 'image'}
               for node in content.iter())


def _wait_for_projection(page, Gui, deadline):
    part_views = [view for view in page.Views if view.isDerivedFrom('TechDraw::DrawViewPart')]
    if not part_views:
        raise ValueError('图纸没有受支持的原生零件投影视图')
    while True:
        Gui.updateGui()
        pending = [view.Name for view in part_views if not view.getVisibleEdges()]
        invalid = [view.Name for view in page.Views if not view.isValid()]
        if invalid:
            raise ValueError('图纸副本中有无效视图：' + ', '.join(invalid))
        if not pending:
            # Let the projection-dependent annotations process the same event turn.
            Gui.updateGui()
            return
        if time.monotonic() >= deadline:
            raise TimeoutError('图纸投影在限定时间内未就绪：' + ', '.join(pending))
        time.sleep(.02)


def drawing_pages(doc, page_names):
    """Return SVG page records; the total projection wait is bounded to 8 s.

    Native save/open/export calls are synchronous host operations and are not
    forcefully interrupted. A timeout or empty preview is an explicit page error.
    Source active document and selection (including subelements) are restored.
    """
    import FreeCAD as App
    import FreeCADGui as Gui
    import TechDrawGui

    if not page_names:
        return []
    originals = []
    for name in page_names:
        page = doc.getObject(name)
        if page is None or page.TypeId != 'TechDraw::DrawPage':
            raise ValueError('指定 TechDraw 图纸页不存在：' + str(name))
        originals.append({'name': name, 'label': page.Label})
    active = App.ActiveDocument
    selected = _selection(Gui)
    clone = None
    records = []
    deadline = time.monotonic() + 8.0
    with tempfile.TemporaryDirectory(prefix='gongke-display-') as temp:
        try:
            path = Path(temp) / 'preview.FCStd'
            doc.saveCopy(str(path))
            clone = App.openDocument(str(path), True, True)
            for original in originals:
                record = dict(original)
                try:
                    if time.monotonic() >= deadline:
                        raise TimeoutError('图纸预览准备已超过限定时间')
                    page = clone.getObject(original['name'])
                    # hidden=True hides the 3D view. TechDraw still needs its own
                    # graphics scene initialized before exporting real content.
                    Gui.getDocument(clone.Name).getObject(page.Name).show()
                    clone.recompute()
                    _wait_for_projection(page, Gui, deadline)
                    target = Path(temp) / (page.Name + '.svg')
                    TechDrawGui.exportPageAsSvg(page, str(target))
                    svg = target.read_text(encoding='utf-8')
                    if not _has_content(svg):
                        raise ValueError('原生图纸导出为空，尚不能显示预览')
                    record['svg'] = svg
                except (OSError, RuntimeError, ValueError, ET.ParseError) as exc:
                    record['error'] = str(exc)
                records.append(record)
        except (OSError, RuntimeError, ValueError) as exc:
            records = [{**item, 'error': str(exc)} for item in originals]
        finally:
            if clone is not None and App.listDocuments().get(clone.Name) == clone:
                App.closeDocument(clone.Name)
            if active is not None and App.listDocuments().get(active.Name) == active:
                App.setActiveDocument(active.Name)
            Gui.Selection.clearSelection()
            for document_name, object_name, subelements in selected:
                if subelements:
                    for subelement in subelements:
                        Gui.Selection.addSelection(document_name, object_name, subelement)
                else:
                    Gui.Selection.addSelection(document_name, object_name)
    return records

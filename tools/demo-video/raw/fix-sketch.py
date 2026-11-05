# 在已打开的原生草图编辑器执行真实控件操作；所有几何变更均由 GUI 命令完成。
# 坐标适用于 1440×810、右侧 Tasks 停靠、此 robot4 图纸的俯视画面。
def mark(description):
    events.append({'seconds':time.monotonic()-started,'kind':'event','description':description})
QtTest.QTest.qWait(1100)
for index in (32,29):
    mark(f'元素列表选择第 {index+1} 条错误斜边并删除')
    elements.scrollToItem(elements.item(index),QtWidgets.QAbstractItemView.PositionAtCenter)
    r=elements.visualItemRect(elements.item(index))
    click(elements.viewport(),210,r.center().y())
    QtTest.QTest.qWait(400)
    QtTest.QTest.keyClick(elements,QtCore.Qt.Key_Delete)
    QtTest.QTest.qWait(500)
for label,start,end in [('上三角形',(407,280),(305,214)),('下三角形',(407,352),(509,418))]:
    mark('用直线工具连接'+label+'的正确端点')
    button=next(w for w in main.findChildren(QtWidgets.QToolButton) if w.defaultAction() and w.defaultAction().objectName()=='Sketcher_CreateLine')
    click(button,button.width()//2,button.height()//2)
    click(viewWidget,*start)
    QtTest.QTest.qWait(350)
    click(viewWidget,*end)
    QtTest.QTest.keyClick(viewWidget,QtCore.Qt.Key_Escape)
    QtTest.QTest.qWait(700)
mark('关闭草图，原生拉伸随之更新')
button=next(w for w in main.findChildren(QtWidgets.QPushButton) if w.isVisible() and w.text()=='Close')
click(button,button.width()//2,button.height()//2)
QtTest.QTest.qWait(1200)
# 只读验证实际结果；不是用模型 API 改值。
result={'geometry':App.ActiveDocument.Profile.GeometryCount,'volume_mm3':App.ActiveDocument.robot4.Shape.Volume,'area_mm2':App.ActiveDocument.robot4.Shape.Volume/4}
(out/'after-ui.json').write_text(json.dumps(result))
assert result['geometry']==40 and abs(result['area_mm2']-828.5)<1e-6,result

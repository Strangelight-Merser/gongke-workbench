# QWidget.grab 不含 macOS Coin/OpenGL 子表面：从同一原生视口读取当前场景。
# Qt 控件、原生视口和自有模态窗口按实际位置组成一帧，没有额外画面元素。
def capture():
    from PySide6 import QtGui,QtCore,QtWidgets
    base=main.grab()
    views=[w for w in main.findChildren(QtWidgets.QWidget) if w.metaObject().className()=='QOpenGLWidget' and w.isVisible() and w.width()>300]
    image=None
    if views and Gui.activeDocument():
        v=views[-1];position=v.mapTo(main,QtCore.QPoint())
        imagefile=out/'current-viewport.png'
        Gui.activeDocument().activeView().saveImage(str(imagefile),v.width(),v.height(),'Current')
        image=QtGui.QImage(str(imagefile))
    painter=QtGui.QPainter(base)
    if image is not None:
        region=QtGui.QRegion(QtCore.QRect(position,v.size()))
        for dock in main.findChildren(QtWidgets.QDockWidget):
            if dock.isVisible():region=region.subtracted(QtGui.QRegion(QtCore.QRect(dock.mapTo(main,QtCore.QPoint()),dock.size())))
        painter.setClipRegion(region);painter.drawImage(position,image);painter.setClipping(False)
    for dialog in QtWidgets.QApplication.topLevelWidgets():
        if isinstance(dialog,QtWidgets.QDialog) and dialog.isVisible():
            location=main.mapFromGlobal(dialog.mapToGlobal(QtCore.QPoint()))
            painter.drawPixmap(location,dialog.grab())
    painter.end()
    return base

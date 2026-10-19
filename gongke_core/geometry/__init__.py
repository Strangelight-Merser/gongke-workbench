"""由设计结果生成三维模型（build123d / OCCT），导出 STEP。

本模块只依赖 build123d，不依赖 FreeCAD。FreeCAD 工作台通过独立进程调用它生成 STEP，再导入文档，
避免 FreeCAD 自带的 OCCT 与 pip 版 OCP 在同一进程中冲突。
"""

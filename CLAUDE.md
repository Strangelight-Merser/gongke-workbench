# CLAUDE.md

本仓库是工科工作台（GongKe Workbench）：一个 FreeCAD 工作台插件，帮中国机械类学生完成课程设计。总体规划见 `PLAN.md`。

## 结构约定

- `gongke_core/` 是纯 Python，不得 import FreeCAD。所有计算、国标查询、说明书生成都放这里，方便脱离 FreeCAD 测试。
  - `calc/` 计算，`layout/` 结构布置，`design.py` 总流程，`geometry/` 用 build123d 建模，`report/` 说明书，`drawing/` 用 ezdxf 按 GB 规定画法出图（`sheet.py` 是图框、图线、尺寸、符号等通用部分）。
  - 齿轮腹板等结构尺寸只在 `layout/gear_blank.py` 定义，带轮结构只在 `layout/pulley.py` 定义，锥齿轮结构只在 `layout/bevel_blank.py` 定义，蜗轮结构只在 `layout/worm_blank.py` 定义，三维和二维共用，不要各算一遍。
  - 三维几何由 `gongke_core.geometry` 生成 STEP；FreeCAD 工作台在**独立进程**中调用（`freecad/gongke/runner.py`），避免 FreeCAD 的 OCCT 与 OCP 冲突。
- `freecad/gongke/` 只做界面和建模调用，业务逻辑调用 `gongke_core`。
- 输出文件名用 ASCII（`report.docx`、`reducer_assembly.step`），C/ASCII 区域设置下中文路径会出错；显示给用户的名称用中文。
- 架构与取舍见 `docs/architecture.md`。
- 国标数据放 `data/standards/`，一个标准一个文件，文件头必须写明标准号和版本年份（如 `GB/T 5782-2016`）。

## 硬性规则

- **不复制国标原文、原表排版和图片**。只录入数值，使用本项目自己的字段结构，并注明来源标准号。
- **不使用、不阅读、不复述商业软件的反编译代码或 SDK**。私有格式只能基于公开文档和样例文件研究，并单独记录在 `docs/clean-room/`。
- GPL 组件（CalculiX、LibreDWG 等）只能以独立进程调用，不能链接进本项目代码。
- 新增计算函数必须附带测试，测试数据来自教材例题或解析解，并在测试里注明出处（书名、版次、页码或公式）。
- 单位统一使用 SI，界面显示可转换为工程常用单位。

## 测试

- `pytest tests/calc tests/standards`：纯 Python，不需要 FreeCAD。
- `pytest tests/drawing`：工程图（需要 ezdxf），改图后用 `drawing.render.to_svg` 渲染 SVG 目视检查重叠。
- `pytest tests/fem`：CalculiX 有限元复核（需要 ccx ≥ 2.21 和 gmsh，可用 `GONGKE_CCX`、`GONGKE_GMSH` 指定路径；没有时自动跳过）。
- `pytest tests/geometry`：需要 build123d（约 2 分钟）。
- `tests/e2e/run_freecad_e2e.sh`：下载 FreeCAD AppImage，在 Xvfb 下跑界面端到端测试，CI 中运行。
- 提交前至少跑纯 Python 测试。

## 语言

- 界面、文档、注释用中文；代码标识符用英文。
- 术语以国标和主流教材用词为准。

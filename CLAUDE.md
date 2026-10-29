# CLAUDE.md

本仓库是构想引擎（原工科工作台 GongKe Workbench）：统一工程桌面应用，在一个窗口内管理原生 CAD 模型、图纸、确定性计算和内置工程助手。FreeCAD 工作台和课程设计计算核心保留并被桌面应用复用。产品方向、首个完整故事和验收顺序见 `PLAN.md`，当前进展见 `docs/implementation-progress.md`。

## 结构约定

- `desktop/`：Electron＋React＋TypeScript＋Three.js 桌面应用，主进程通过子进程标准输入输出（JSON Lines）调用 Python 应用服务。用法与打包见 `desktop/README.md`。
- `gongke_app/`：应用服务（工程、任务、宿主、内置 agent），方法清单见 `gongke_app/README.md`。服务标准输出只能写 JSON Lines。
- `adapters/solidworks/`（C# COM add-in）、`adapters/autocad/`（C# 托管 bundle）：Windows 原生插件，各自 README 说明构建与安装。FreeCAD 使用 `freecad/gongke/` 的原生命令桥。
- 原生 CAD 是几何事实来源；修改前先另存工作修订，原件不直接修改。agent 只能调用列出的工程工具，不执行任意 shell/Python/VBA/AutoLISP。详见 `PLAN.md` 工程约束。

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
- `pytest tests/drawing`：工程图（需要 ezdxf），五个方案的图纸都用 `drawing/lint.py` 自动检查文字重叠和压线（必须为 0）；改图后仍要渲染 `drawings.pdf` 目视检查，并按 `docs/drawing-checklist.md` 复查。
- `pytest tests/fem`：CalculiX 有限元复核（需要 ccx ≥ 2.21 和 gmsh，可用 `GONGKE_CCX`、`GONGKE_GMSH` 指定路径；没有时自动跳过）。
- `pytest tests/geometry`：需要 build123d（约 2 分钟）。
- `tests/e2e/run_freecad_e2e.sh`：下载 FreeCAD AppImage，在 Xvfb 下跑界面端到端测试，CI 中运行。
- `tests/e2e/freecad_python_flow.py`：不开界面，用 FreeCAD 自带的 Python 按面板流程装依赖、跑五种方案（中文用户目录、中文输出目录）；CI 在 Windows 版 FreeCAD 上运行它。
- `pytest tests`（可 `--ignore=tests/geometry --ignore=tests/fem` 加速）：含应用服务、原生桥、修订流程等测试；`tests/test_revision_mcp.py` 需要官方 `mcp` SDK。
- `cd desktop && npm run build && npm test`：桌面应用。
- `dotnet run --project adapters/solidworks/tests/ProtocolChecks.csproj -c Release`、`dotnet run --project adapters/autocad/Gongke.AutoCAD.ContractTests -c Release`：Windows 插件协议检查。编译和协议测试通过不等于在真实宿主中验收。
- 提交前至少跑纯 Python 测试；改了桌面或服务再跑相应测试。

## 语言

- 界面、文档、注释用中文；代码标识符用英文。
- 术语以国标和主流教材用词为准。

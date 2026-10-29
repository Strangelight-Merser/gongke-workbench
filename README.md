# 构想引擎

面向工科学生的统一工程工作台。模型、图纸、计算和工程助手在同一个桌面窗口中使用；原生 CAD 执行实际编辑，工作台读取结果与操作回执。

当前主入口为 [桌面应用](desktop/README.md)：Electron＋React 界面、随安装包提供的 Python 服务，以及内置的模型工具调用循环。FreeCAD 工作台、SOLIDWORKS COM 插件和 AutoCAD 托管插件分别承担原生接入，手动操作与内置助手共用应用命令。

首个完整故事是：修改已有轴的明确尺寸，重新计算，更新关联工程图，再形成 AutoCAD DWG 工作修订。各环节并行推进；当前尚未完成 Windows 双宿主现场验收，不能把 SDK 编译或教学基准通过视为机械验收。

| 入口 | 已有能力 | 验证边界 |
|---|---|---|
| 桌面应用 | 创建与打开工程、真实计算和导出、SVG 图纸预览、任务记录、模型服务配置 | 已运行真实桌面流程；发行包未签名、公证 |
| 内置工程助手 | Chat Completions 流式工具调用、工程读取、确定性计算、受限原生操作 | 协议与工具循环已测；真实模型账号任务待连接验证 |
| FreeCAD | 原生轴读写、候选校核、撤销、网格与 TechDraw 页显示、原生 DXF 导出 | macOS 宿主稳定性仍单独跟踪 |
| [SOLIDWORKS](adapters/solidworks/README.md) | 正式 COM add-in、尺寸读写、网格、图纸检查/更新、工作副本及 DXF | 真实 interop 编译检查；Windows 宿主待测 |
| [AutoCAD](adapters/autocad/README.md) | 正式 .bundle、原生实体读取/选择、文字编辑、标注文字移动、DXF→DWG | Autodesk SDK 编译与协议检查；Windows 宿主待测 |

工作台只允许修改由原生保存回执登记的工作副本；原件即使放在工程目录内，也不会自动获准修改。教学输入始终明确标识，缺少的机械条件不能由助手编造。以下 CLI/MCP 操作供开发、回归和外部 agent 使用；G1 只读检查继续独立保留。

## 检查已有轴与关联图纸

打开已有 FreeCAD 三段实心回转轴及其 TechDraw 图纸，启用“工科工作台”。执行者准备一个明确的 case，记录文件绝对路径、Body/草图/回转对象、目标半径约束对应的轴段，以及所选页中的每个目标直径标注。检查器核对这些对应关系，不靠尺寸数值相同猜测关系，也不需要先绑定或改写原件。

```bash
python -m gongke_core inspect-revision --host freecad \
  --case /absolute/path/shaft.case.json --out /absolute/path/check-01
```

命令读取当前已打开的 FreeCAD，打印中文条件确认表和问题定位，并在新目录中生成 `revision.json`。检查不重算、不保存，不改模型、显示或选择。若模型或图纸待更新，结果保留未确认状态，需在 CAD 中明确更新后再读。

支持范围为三段轴的名义弯扭应力、梁挠度，以及所选图纸中显式映射的直径标注。图纸检查包括实际测量、毫米显示精度、数值覆盖和模型/视图引用；未识别对象、悬空引用和枚举缺口会保留问题位置。两个视图显示同一尺寸时，须分别映射和检查。

工程条件使用学生常见单位，并逐字段记录来源原文、来源位置及确认状态；示例见 [revision_conditions.json](examples/revision_conditions.json)。缺弹性模量时仍可计算应力，缺许用值时保留数值并标为未判定；缺载荷不视为零载荷。该示例中的材料与载荷均为**人工教学假定**，不得直接作为自己零件的实际依据。

克隆后可从 [原生轴与图纸基准](tests/fixtures/revision_cases/README.md) 开始：复制一份 `.FCStd` 与同名 `.case.json` 到新工作目录，只把 case 的 `document.path` 改为该副本的绝对路径，然后在 FreeCAD 中打开副本。这些文件由 [revision_fixture.py](tests/e2e/revision_fixture.py) 构造，包含正常及四种负例；它们是测试基准，不是学生试用样本，保留仓库原件不变。

手工修正后，重新检查并比较上一份结果：

```bash
python -m gongke_core inspect-revision --case /absolute/path/shaft.case.json \
  --previous /absolute/path/check-01/revision.json --out /absolute/path/check-02
```

几何、条件、映射、图纸或会话改变会使旧结论过期。每次 `--out` 必须是尚不存在的新目录；已有空目录也拒绝覆盖。退出码 `0` 表示当前范围的图纸检查和数值限值检查均通过，`1` 表示已生成结果但有失败或未确认项，`2` 表示输入、连接或输出错误。通过只针对已声明条件及受支持范围，不代表机械设计、疲劳或制造验收合格。

提供 `--capture /absolute/path/normal.capture.json` 时改为离线核对，不连接 FreeCAD。结果明确标为 `recorded_capture`，只能说明该次采集，不能证明当前 CAD 仍相同。完整 case、条件状态与 MCP 调用见 [agent-api.md](docs/agent-api.md#已有轴与工程图只读检查)。

## 原生轴协作

在 FreeCAD 的“工科工作台”中选择“创建原生教学轴”，通过已有 MCP 客户端读取选中对象、比较轴径、应用修改和保存。模型包含原生 Body、带命名尺寸的 Sketch 和 Revolution，学生可以直接编辑草图并使用原生撤销。

- 尺寸读取自当前草图；过时候选不能覆盖人工修改。
- 分别显示计算结论和结果是否仍适用于当前工程。
- 可提交受限轴梁仿真，查询或取消任务；工程修改后旧结果标为过期。
- 当前可编辑案例为教学三段轴，校核仅包括名义弯扭应力与梁挠度，不代表实际减速器的轴肩、疲劳和配合验收。

MCP 的 `create_shaft_project(case="course_output")` 可从减速器任务书初始化七段输出轴、两个原生键槽和六处原生圆角。此后 `review_current_object` 直接读取当前模型，检查名义应力、刚度、键连接及轴承座、齿轮座、联轴器孔径的一致性；手改轴承座 55→54.5 mm 会明确显示与 55 mm 轴承孔径不一致。课程轴暂不开放 agent 自动改径，材料疲劳依据和配合条件仍需补齐。

轴肩疲劳使用当前原生圆角半径；超出公式适用范围的截面单独标为受阻。键槽槽根仍是计算假设，不视为实形疲劳通过。原生特征重算失败时停止分析，即使 FreeCAD 仍显示上一次的实体也不会沿用。

课程轴可用 `preview_fillet_change` 比较右轴承邻接轴肩的圆角增大，再以 `apply_change` 写入一次可撤销的原生事务。默认案例支持 R1→R1.2/R1.5 mm，其他尺寸保持原样；预览后发生手改会使候选失效。`ready` 只表示满足本阶段编辑条件，整轴校核中的来源和模型缺口仍保留。

已有的原生三段回转轴可通过 `bind_existing_shaft` 接续。工作台识别现有的具名长度和半径约束，保留个人命名、草图、先前手改尺寸及 Body 位置，只添加工程映射。材料、支承、载荷、转矩、限值和编辑区间必须明确提供并注明来源；绑定本身可撤销。表达式驱动、未完全约束或含未知特征的轴保留原样，不自动接管。

三段轴与课程轴均可提交 CalculiX 梁任务。课程轴保留轴向力产生的偏心弯矩，梁模型不计算键槽、圆角的局部应力或扭转。分析结果保存在本机并关联对象内容和计算方法版本；保存重开后可继续判断适用性，改变轴段长度会使原载荷位置绑定失效。

macOS 上，任务管理进程异常退出后，下一次加载会核对并清理该任务遗留的求解器，任务显示为中断。进程身份无法核实时保留明确的未核实状态，不会按 PID 直接终止其他进程。此恢复路径已用真实 CalculiX 进程验证，尚未在其他系统验证自动清理。

实测配置：macOS 15.6、FreeCAD 1.1.4 arm64、外部 Python 3.13。独立安装副本中的工作台与 stdio MCP 已完成读取、候选、应用、撤销、手改模拟、保存重开和真实梁求解验证；macOS 辅助功能点击验证遇到 Qt 崩溃，尚未闭合。

[Linux ARM64 隔离桌面](tools/linux-gui/README.md) 已用 FreeCAD 1.1.4 与独立安装包完成真实界面接续：MCP 改径 40→35 mm、菜单撤销至 40 mm、Sketcher 输入半径 19 mm 后读回直径 38 mm、拒绝过时候选、原生保存退出重开，以及新会话继续修改至 36 mm。界面动作通过 noVNC 的鼠标键盘完成，MCP 通过 stdio 测试客户端调用。该结果不代表 macOS 崩溃修复、WorkBuddy 本轮接续通过或真实学生试用完成。

独立安装（目标目录尚不存在时）：

```bash
python tools/install_freecad_workbench.py --mod-dir "$HOME/Library/Application Support/FreeCAD/v1-1/Mod"
```

重启 FreeCAD 后加载工作台。MCP 使用外部 Python 3.11 或更新版本运行 `python -P -m gongke_core mcp --profile native`，将 `PYTHONPATH` 设为安装目录 `GongKeWorkbench` 的绝对路径；详细接口见 [agent-api.md](docs/agent-api.md)。`-P` 避免客户端的当前工作目录覆盖已安装模块。原生编辑不依赖 build123d。`native` 提供当前工程工具与 `inspect_revision`，`batch` 只提供 9 个任务书批处理工具，默认 `all` 提供两组。

## 减速器批处理

已有批处理支持**带式输送机用展开式二级斜齿圆柱齿轮减速器**，电动机可经联轴器或 V 带接入；另有一级圆柱齿轮、圆锥-圆柱齿轮和蜗杆方案。这条路径用于初始化和批量导出，不编辑当前 FreeCAD 原生工程。

输入一张设计任务书（输送带拉力、速度、卷筒直径、使用年限），一次得到：

- **全部设计计算**：电动机选择、传动比分配、各轴运动和动力参数；普通 V 带传动（带型、带轮直径、中心距、根数、初拉力和压轴力）；两级斜齿轮按接触强度设计、按弯曲强度定模数、圆整中心距后校核；三根轴的结构设计、受力分析、弯扭合成校核；深沟球轴承寿命；平键挤压强度；箱体主要尺寸；润滑方式。
- **三维装配体（STEP）**：渐开线斜齿轮（大齿轮为腹板式）、带键槽的阶梯轴、齿轮轴、轴承、联轴器半体或大带轮、箱座、箱盖、轴承盖、连接螺栓和主要附件。可直接在 FreeCAD、SolidWorks、UG 中打开。
- **二维工程图（DXF，附 SVG 预览）**：装配图（主视图、俯视剖视图、左视图，画出箱盖、轴承盖、连接螺栓、视孔盖、通气器、吊环螺钉、油标、放油螺塞等附件，零件序号、明细栏、技术特性表、技术要求），三根轴、各齿轮和大带轮的零件图（尺寸和极限偏差、键槽断面图和对称度、表面结构、基准、圆跳动和轴颈圆柱度、齿轮参数表和检验项目公差、公法线长度偏差），箱座、箱盖零件图（中心距极限偏差、轴承孔平行度和圆柱度按齿轮精度等级算出，螺栓孔、销孔、螺纹孔标注，放油孔和油标孔局部剖；圆锥-圆柱方案画出端壁上的小锥齿轮轴承座，蜗杆方案局部剖出两端蜗杆轴承座，蜗杆中心距偏差按 GB/T 10089），按 GB 图幅、比例、图线和标题栏绘制。装配图标注特性、配合、安装和外形尺寸，深沟球轴承按规定画法。对照课程设计通行要求的自查结果见 [docs/drawing-checklist.md](docs/drawing-checklist.md)。可用 AutoCAD、中望 CAD、LibreCAD 等打开修改。
- **计算说明书（Word / Markdown）**：每一步写出公式、代入值和结论，附各轴弯矩图、转矩图和校核汇总表。

![FreeCAD 中导入的减速器装配体](docs/images/freecad_assembly.png)

![自动生成的装配图](docs/images/assembly_drawing.png)

改任何一个参数，后面的齿轮、轴、轴承、键、模型、说明书全部重算。

**人和 AI 都能用**：除了 FreeCAD 图形界面和命令行，同一套能力还以 MCP 服务器（`python -P -m gongke_core mcp`，按上述配置设置 `PYTHONPATH`）的形式提供给 AI agent。
Claude、Cursor 等可以直接调用设计计算、多方案对比、标准件查询和出图，不需要操作界面。接入方法见 [docs/agent-api.md](docs/agent-api.md)。

## 使用方法

### 方式一：FreeCAD 工作台

1. 安装 FreeCAD 1.1.4 或更新版本；当前原生轴功能在 1.1.4 上验收。
2. 使用上面的安装脚本复制工作台到 FreeCAD 用户目录的 `v1-1/Mod/`。也可在 FreeCAD Python 控制台用 `App.getUserAppDataDir()` 确认本机目录，再在其下创建 `Mod/`。
3. 启动 FreeCAD，切换到“工科工作台”，选择“创建原生教学轴”；也可打开自己的受支持三段轴并选中 Body。
4. 按 [MCP 接入说明](docs/agent-api.md) 连接现有 agent 客户端，先读取当前工程，再比较和应用一个候选。原生编辑无需安装批处理导出包。已有轴绑定的完整工况格式见 [existing_shaft_conditions.json](examples/existing_shaft_conditions.json)；其中是示例假定，接入自己的工程时必须换成其实际工况和来源。
5. 学生可继续在原草图中手改尺寸，用 FreeCAD 撤销并保存 `.FCStd`。关闭重开后重新读取当前工程，不能复用旧会话标识。

需要任务书批处理时，再打开“带式输送机传动装置设计”，选择方案并填写参数。首次运行可在该面板安装导出依赖（需联网，约 1 GB），或通过 **工科 → 设置 Python 解释器…** 指定已有依赖的外部 Python。安装的包只供外部计算进程使用。计算完成后，STEP 导入开始任务时绑定的文档，面板提供图纸和说明书链接；目标文档已关闭或正在编辑时保留输出文件供手工导入。

### 方式二：命令行

```
pip install pyyaml python-docx pillow build123d ezdxf
python -m gongke_core design examples/conveyor_basic.yaml -o out
```

`out/` 下得到 `summary.json`、`report.docx`、`report.md`（含弯矩图）、`reducer_assembly.step` 和 `drawings/`（`assembly.dxf`、`shaft1.dxf`…、`gear_low2.dxf` 等，每张都有同名 SVG 预览；整套图另合成一个 `drawings.pdf`，每张一页、页面等于图幅，可直接打印）。三维模型默认把齿轮画成齿顶圆柱（约 1 MB），加 `--full-teeth` 建出完整渐开线齿形（约 30 MB）；`--no-step`、`--no-drawings` 可跳过对应输出；加 `--fem` 用 CalculiX（FreeCAD 自带，或安装 `calculix-ccx`，需 2.21 以上）复核各轴刚度（梁单元）和各齿轮的齿根弯曲应力（二维模型，网格用 Gmsh，FreeCAD 也自带），输出 `fem/` 目录并在说明书中加一章对照和应力云图。任务书格式见 [examples/conveyor_basic.yaml](examples/conveyor_basic.yaml)，教材里查图得到的系数可以在 `overrides` 中填写，覆盖程序的近似值。

## 计算方法和数据

- 轴先按弯扭合成法定直径，再在每个轴肩和键槽处按安全系数法做疲劳校核，不满足时自动加大轴径；然后按阶梯轴实际截面积分求挠度和偏转角，做刚度校核（濮良贵《机械设计》表 15-5 许用值）。
- 计算主要参考濮良贵《机械设计》（第八版）和课程设计指导书的方法；部分公式已有注释与出处，默认系数、部分取值和标准数据仍需逐项核对，不能视为全部完成来源核验。
- 教材中只能查图的系数（动载系数 Kv、寿命系数 KHN/KFN）用 ISO 6336 的解析近似，说明书里会提示，并可在任务书中手工覆盖。
- 只录入计算链路必须用到的少量标准数据（Y 系列电动机、深沟球轴承、平键、模数、齿形系数），存放在 `data/`，每个文件注明标准号，状态为“待人工核对”。

详细的分层和取舍见 [docs/architecture.md](docs/architecture.md)。

## 目前的限制

- 支持“电动机 → 联轴器（或 V 带传动）→ 展开式二级斜齿圆柱齿轮减速器 → 联轴器 → 卷筒”两种方案（任务书 `scheme: coupling / vbelt`，示例见 [examples/conveyor_vbelt.yaml](examples/conveyor_vbelt.yaml)）。
- V 带 + 一级斜齿圆柱齿轮减速器（`scheme: single`，示例 [examples/conveyor_single.yaml](examples/conveyor_single.yaml)）：V 带传动比不指定时取 i/4（限制在 2～4），使齿轮传动比约为 4；齿轮对称布置在两轴承之间，箱体壁厚按一级减速器公式。齿轮传动比超过 5 时给出提示（宜改用 1000 r/min 电动机或二级减速器）。计算、说明书、三维模型和整套工程图与二级方案相同。
- 圆锥-圆柱齿轮减速器（`scheme: bevel`，示例 [examples/conveyor_bevel.yaml](examples/conveyor_bevel.yaml)）包括直齿锥齿轮、三根轴（小锥齿轮悬臂、圆锥滚子轴承反装在套杯中）、轴承、键的计算和说明书，三维模型（锥齿轮按齿顶圆锥简化）和整套工程图（装配图、锥齿轮零件图、锥齿轮轴等）。
- 单级蜗杆减速器（`scheme: worm`，蜗杆下置，示例 [examples/conveyor_worm.yaml](examples/conveyor_worm.yaml)）按 GB/T 10085 选标准中心距、模数和蜗杆分度圆直径，计算蜗轮接触和弯曲强度、效率、热平衡、蜗杆刚度（刚度不够时自动加大蜗杆直径、并把蜗杆轴承座做成内凸台缩短跨距），电动机按实际蜗杆效率选择。有计算、说明书、三维模型（蜗轮为齿圈压配式，--full-teeth 时建出阿基米德蜗杆螺纹）和整套工程图（装配图、蜗杆、蜗轮、蜗轮轴零件图）。
- V 带只录入了 A、B 型的数据，带型按“带的根数不超过 4～5 根时带轮最小”自动试选，代替教材的选型图；P0、KL 数值待人工核对。V 带的压轴力按水平指向电动机计入Ⅰ轴受力。
- 轴的疲劳校核（安全系数法）中，应力集中、尺寸、表面系数用公开的解析拟合代替查图，说明书注明“近似”；齿轮过盈配合处默认不校核，可在任务书 `shaft: k_sigma_fit` 中填入查表值。
- 箱体是简化模型：轴承座为圆柱凸台加轴承旁凸台，箱座两侧壁外有加强肋，没有铸造圆角；附件按常用尺寸示意，型号需按手册核对。
- 联轴器只给出计算转矩和孔径，型号需按 GB/T 5014 自行核对。
- 工程图是按设计数据直接绘制的“规定画法”，不是从三维模型投影：装配图的主视图、左视图只画外形（不作局部剖）；五种方案都有箱座、箱盖零件图（含轴承旁凸台和箱座外加强肋）；零件图的倒角、圆角用技术要求统一说明。作为底稿使用，提交前请按指导书补全。
- 工程图字体按 Windows 的仿宋（simfang.ttf）设置；FreeCAD 自带的 DXF 导入只导入线条，不导入文字和尺寸，看完整图纸请用 CAD 软件或 SVG 预览。

## 测试

开发测试环境使用 Python 3.11+，在独立虚拟环境中安装依赖。MCP 协议验收强制使用官方 SDK；缺依赖会失败，不以跳过代替验收。

```bash
python -m pip install -e '.[dev,geometry,report,drawing]'
python -m pytest -q                # 单元、协议、计算、图纸、三维与命令行测试
tests/e2e/run_freecad_e2e.sh       # 下载 FreeCAD，在 Xvfb 下跑界面端到端测试
```

`tests/test_revision_mcp.py` 使用官方 SDK 验证真实 stdio 通信，输入是明确标识的合成采集。G1 的 FreeCAD 原生文件、真实界面操作与读取前后状态验收需另行执行；协议通过和教学基准通过均不代表真实学生或专业机械验收通过。

## 许可证

LGPL-2.1-or-later，与 FreeCAD 一致。

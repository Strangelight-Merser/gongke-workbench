# 独立图纸检查（2026-11-04）

## 修复范围与依据

原 `host.check` 的 `source` 是任意文字，期望值和模型都可以出自同一次错误读图。现在自由文本不再取得图纸证据身份：无独立引用的条件匹配返回 `unverified`，中文为“未经独立核对”。服务端自行读取原图，校验 SHA-256、页码、标注对象；几何比较不接收调用者填写的边坐标、面积、比例或逐边白名单。

人工通过桌面应用命令、Agent 通过 MCP，均执行 `Commands → Hosts.inspect → inspection.check`。FreeCAD/SOLIDWORKS 只采集 `model.inspect` 和 `model.section`；图纸解析、尺寸关联、几何比较全部位于共享 Python `gongke_app/drawing_check.py`，不导入 CAD 内核。本次不新增宿主执行命令、shell 工具或任意代码工具。

## 调研与选择

| 方案 | 原始资料及能力 | 本次取舍 |
| --- | --- | --- |
| Drawing2CAD | [论文及作者代码入口](https://arxiv.org/abs/2508.18733)：把矢量图元编码为序列，预测 CAD 命令与参数 | 目标是生成模型，不提供本任务所需的确定性独立核验。引入模型、训练数据与推理不适合首版 |
| Photo2CAD | [论文](https://arxiv.org/abs/2101.04248)：OpenCV 从照片提取特征并重建；作者明确说明目前不处理隐藏线 | 当前输入已有精确矢量，无需先栅格化再识别 |
| PyMuPDF | [官方图形提取文档](https://pymupdf.readthedocs.io/en/latest/recipes-drawing-and-graphics.html)：`get_drawings` 输出绘图路径 | 可以获取图元，但仍需建立标注与边线关系；不为重复能力增加依赖 |
| pdfplumber | [项目文档](https://github.com/jsvine/pdfplumber)：提供线、曲线、线宽、虚线、文字位置、旋转字符和图像范围 | 项目已依赖；复用 `read_drawing` 的坐标、文字方向修正和来源编号 |

选择：限定范围内的确定性线框提取和双向线段覆盖比较。没有训练或生成式识别，也没有硬编码 robot 外形或面积。以上是对公开方法与接口的调研，不声称复现这些论文的模型或指标。

## 返回语义

每项都有 `source_kind`：

- `drawing_annotation`（图纸标注）：`evidence` 指向 `read_drawing` 的 `path / sha256 / page / item`。服务端重新提取纯数值文字，关联紧邻尺寸线、两条尺寸界线与几何顶点，返回文字、页面 bbox、尺寸线/界线编号。只支持毫米长度的直接量测，不能给截面积、任意特征参数或推导值背书。引用数值和 SI 期望不一致返回未知。
- `drawing_geometry`（图纸几何）：从 PDF 的完整视图线框提取，返回全部图元编号、尺寸关联证据、图纸哈希、比例、缺少/多出或偏移的边及文档坐标定位。
- `agent_defined`（Agent 自定）：没有独立引用的期望值，即使 `source` 写着“人工确认”“图纸标注”，匹配也只能是 `unverified`。不匹配仍报告 `fail`，表示模型与自定条件矛盾，并不证明自定条件正确。

总状态优先级：`fail → unknown → unverified → pass`；空检查为未知。包含未独立核对条件时不能总通过。`unverified` 列出全部 Agent 自定条件 ID。界面标识依据类别，不将未核对项折叠进绿色成功组；MCP 任务外层 `status=complete` 不覆盖内层检查状态。

**通过的范围始终是返回的条件/截面，不是整个零件或整张图纸。** 标注引用核实数值及图纸上的几何关联，但模型量测对象仍由调用方选择；不声称已经自动识别所有设计意图。输入图纸本身必须是用户认可的原始依据，哈希用于固定本次依据，不是图纸真实性认证。

## 几何算法与适用条件

1. 调用者给一个外轮廓实线 `outline_seed`，不是轮廓坐标或裁切白名单。服务端沿相同线宽端点连通提取完整外环，并纳入其范围内同线宽的全部内环；拒绝以内部孔环作种子。
2. 端点度数必须为 2，拒绝开放、分叉、退化、自交路径。PDF 端点归并精度为 0.001 pt。需要可区分的较粗实线轮廓与较细尺寸线；隐藏线/未分类虚线、曲线以及图像覆盖所选视图时返回未知。细点划中心线不作为实体边界。
3. 纯数字标注须紧邻平行尺寸线，两端各有唯一垂直界线，界线端点落在轮廓顶点。至少取得横、纵两个方向的关联。比例取关联值中位数，任何比例偏差超过 0.5% 则未知；不使用模型尺寸反推比例，也不使用标题栏“比例”替代尺寸关联。
4. 调用者指定截面和页面向右/向上的模型有向轴 `axes`。当前只支持正交坐标轴；检查截面身份、修订、位置和法向。按完整外包络中心平移配准，不做旋转/镜像搜索，不用内孔拟合抵消错误。**因此不检查模型在全局坐标中的绝对放置。**
5. 两个方向检查线段并集覆盖，支持模型对共线边的拆分。固定 0.05 mm 几何容差用于 PDF 坐标舍入；调用方不能扩大此容差。尺寸/比例含糊时不猜、不补边。面积相同也可能轮廓不同，所以不以面积替代边线比较。
6. 多出/偏移边使用宿主截面边 ID 与三维端点；缺少/偏移边从图纸反投影到同一截面。模型视图用红色画实际错误边、橙色画图纸要求的边。截面边不是模型 B-rep 面编号，不伪造 `FaceN` 定位。

毫米单位是当前接口的适用前提，不自动推断英制单位。只支持以一致粗实线表达完整边界的直线视图；多种轮廓线宽、剖面线混杂、圆弧/样条、断裂/局部放大/非等比视图、照片、未关联尺寸、隐藏孔、盲孔深度、多视图自动对应、任意斜视图及自动判定投影是否等于某截面均不在首版能力内。调用方必须明确所选视图与截面的对应关系；无法确认时保留未知，不用其他视图的通过覆盖它。

## 调用示例

先用 `project.read_drawing` 读取输入，原样使用其哈希和图元编号。以下图元对应仓库自绘合成夹具，不是学生图纸：

```json
{
  "host_id": "freecad",
  "document": {"host_instance": "从 host.context 取得", "document_id": "从 host.context 取得", "revision": 0, "configuration": ""},
  "object_ref": "Plate",
  "conditions": [],
  "drawing": {
    "path": "plate.pdf", "sha256": "从 read_drawing 取得", "page": 1,
    "outline_seed": "page-1/lines/0",
    "plane": {"origin": [0, 0, 0.0015], "normal": [0, 0, 1]},
    "axes": [1, 2]
  }
}
```

标注条件在原条件上增加 `evidence: {path, sha256, page, item}`。其他条件保持 Agent 自定身份。不能只把 `source` 换个文字就获得“图纸标注”类别。

## 本地回归结果

使用历史真实 FreeCAD 采集记录回放**当前产品检查函数**，不是重新运行旧的人工坐标审计。输入模型/图纸没有改写。清单与详细回执在本工作树 `out/independent-drawing-check/local-manifest.json` 和 `replay/regression.json`；这些含本地路径及学生图纸的文件均不提交。

| 案例 | 新逻辑结果 | 证据与边界 |
| --- | --- | --- |
| 演示第二次 `paid-robot4-02/robot4-1`，会话 b7fd234f | **不符** | 40 条图纸边中，两条内部三角孔斜边不匹配；实际 `section.Edge28 / Edge31`，图纸 `lines/73 / lines/101` |
| 演示第一次 `paid-robot4/robot4-1` | **通过** | 40 条完整内外轮廓边双向匹配，限定中间截面 |
| round8 `robot4-low/robot4-1` | **通过** | 历史中间截面 40 边匹配 |
| round8 `robot4-low-repeat/robot4-2` | **通过** | 历史中间截面 40 边匹配 |
| round8 `robot13-low/robot13-1` | **未知** | 历史审计未保存可用截面边；所选正视图含圆弧，纯直线外环无法闭合 |
| round8 `robot13-off/robot13-1` | **未知** | 同上；不把旧审计结论作为新逻辑通过 |
| round8 `robot13-high/robot13-1` | **未知** | 没有最终原生模型/截面记录；同一曲线图纸也超出首版范围 |

第二次运行具体位置（mm，Z=2）：实际边从 `(0,-3)` 接到 `(-8.5,8.5)`，图纸要求该上三角边接到约 `(0,3)`；另一实际边从 `(0,3)` 接到 `(8.5,-8.5)`，图纸要求其接到约 `(0,-3)`。这是内部孔顶点连接错位。几何核验没有引用 `828.5`、`777.5` 或原审计的手工轮廓坐标；比例由图纸六处尺寸关联得到，约 `5.66917 pt/mm`。

## 自动验证与沙箱外复验

已执行：相关 Python 回归 76 项通过；桌面 TypeScript/Vite 构建通过；桌面测试 67 项通过、1 项跳过（含真实 MCP 外层回执、未经独立核对的呈现和 FreeCAD/SOLIDWORKS 共用执行测试）。合成夹具 `tests/fixtures/independent_drawing/generate.py` 自绘 36×24 mm 倒角板及两个梯形孔，错误变体移动左孔顶点 2 mm；测试注明解析依据，不读取学生素材。生成的 PDF 已渲染检查。原生实体生成脚本使用相同自绘定义，尚待下面的宿主运行。

本沙箱 FreeCAD 在导入时因 Qt `Incompatible processor ... neon` 退出；Electron 启动以 SIGABRT 退出。不能据此声称新代码已完成真实宿主重开或桌面场景目视验收。SOLIDWORKS 本轮只验证共享协议执行，未运行真实 Windows 宿主。

在本工作树根目录，沙箱外执行：

```sh
# 1. 从原生 FCStd 重新采集七个本地案例，再走产品比较逻辑。
.venv/bin/python tools/check_drawing_regression.py \
  --manifest out/independent-drawing-check/local-manifest.json \
  --out out/independent-drawing-check/native \
  --native-python /Applications/FreeCAD.app/Contents/Resources/bin/python

# 2. 完全不依赖学生材料：生成自绘 PDF + 正确/错误 FreeCAD 实体并核验。
.venv/bin/python tests/e2e/independent_drawing_native.py \
  --freecad-python /Applications/FreeCAD.app/Contents/Resources/bin/python

# 3. 复查桌面真实显示；使用当前 checkout 的源码服务。
GONGKE_PYTHON=.venv/bin/python npm --prefix desktop run dev
```

第 1 条保留每次原生采集的退出码、模块路径、FreeCAD 版本、源文件哈希和检查回执；任何宿主启动失败返回非零。没有原生模型的 robot13-high 仍是未知。第 2 条必须正确模型 pass、错误模型 fail 且有边定位，否则非零退出。两条命令均不保存或重建已有学生文档，不覆盖原件。

桌面检查：打开错误模型，在工程内导入其原 PDF，用 `read_drawing` 和 `host.check drawing` 取得当前修订回执；查看内部两条斜边红/橙定位。再调用只有自填期望的条件，确认显示“Agent 自定 / 未经独立核对”，不出现绿色通过。仅标注/截面通过时仍展示范围。把 `native/regression.json`、`synthetic-native/acceptance.json` 和实际界面截图交回即可继续收口。

只回放已有采集、不启动宿主：

```sh
.venv/bin/python tools/check_drawing_regression.py \
  --manifest out/independent-drawing-check/local-manifest.json \
  --out out/independent-drawing-check/replay
```

## 提交状态

沙箱阻止写入主仓库 `.git/worktrees/gongke-workbench15/index.lock`，`git add` 返回 `Operation not permitted`。修改仍在 `codex/independent-drawing-check` 工作树，未提交、未 push。沙箱外在本工作树运行以下精确列表（不包含学生资料、`out/` 或其他修改）：

```sh
git add gongke_app/drawing_check.py gongke_app/inspection.py gongke_app/hosts.py \
  gongke_app/drawing_input.py gongke_app/modeling.py \
  desktop/src/agent/ToolCall.tsx desktop/src/styles/agent.css \
  desktop/src/workspace/FreeCadInspector.tsx desktop/src/workspace/ModelView.tsx \
  desktop/tests/agent-presentation.test.cjs tests/test_model_inspection.py \
  tests/test_independent_drawing.py tests/fixtures/independent_drawing/generate.py \
  tests/e2e/independent_drawing_native.py tools/drawing_check_capture.py \
  tools/check_drawing_regression.py docs/independent-drawing-check.md docs/model-inspection.md
git commit -m "修复图纸检查自证通过并增加独立矢量轮廓核验"
```

# 原生零件建模

真实窗口内 Agent 自行读图、选择工具、建模与自查的运行入口见 [真实 Agent 建模验收](agent-modeling-trial.md)。下文的 P7/P8 配方脚本验证工具执行能力，不计作真实模型成功率。

`gongke_app/modeling.py` 定义输入与说明，`tools.py` 汇总；桌面已有 Agent 的 MCP 调用仍经过 `Commands` 的工程、写入开关和收据。FreeCAD/SOLIDWORKS 各自执行受限原生 API。没有脚本执行工具，也没有修改桌面前端或重写 `host.inspect/section/measure/check`。

## 工具与顺序

1. `hosts.list`、`host.context`：取得真实宿主实例、文档修订和能力。
2. `host.model_new`：在工程内新建并保存零件，返回 `document`、`body_ref`。已有原件用 `host.model_copy` 另存并打开；原件不改。
3. `host.sketch`：新建时传 `name/support`，追加时传 `sketch_ref`。每批最多 128 项几何、256 项约束，一次求解。支持线、圆、三点弧、矩形，以及水平、竖直、重合、相切、平行、垂直、相等、固定和尺寸约束。
4. `host.feature`：pad、pocket、revolve、hole、fillet、chamfer、mirror、linear_pattern、polar_pattern。每次返回实际原生引用和 `editable_parameters`。
5. `host.feature_edit` 修改回执中列出的尺寸；`host.feature_delete` 只删叶特征，不级联删除下游。`host.rebuild` 明确重建。
6. `host.inspect/check` 按图纸条件读回，修正失败项，最后 `host.model_save` 保存当前副本。

所有写工具都服从 `allow_writes=False`，包括泛型 `host.write`。`host.model_operation` 是只读查询。MCP 同时提供 `gongke://modeling` resource 与 `native-modeling` prompt；两者使用同一段简短说明。

长度为 **m**，角度为 **rad**，数组 `count` 含原始实例。草图坐标 `[u,v]` 是局部坐标；三点弧依次为 start、mid、end。矩形从 start 到 end 展开四条边，并添加端点重合与水平/竖直约束。回执 `added_geometry` 是每项输入展开后的索引，`geometry` 为当前草图引用映射。

FreeCAD Body 局部基准面：XY 的 `(u,v,n)=(X,Y,+Z)`，XZ 为 `(X,Z,-Y)`，YZ 为 `(Y,Z,+X)`；offset 沿 n。模型面必须为当前 Body/Tip 的真实平面引用。支持面原生关联保留在草图上。SOLIDWORKS 基准面按原点与法向识别，不靠语言相关的平面名称；草图本地坐标来自模板，先用空 geometry/constraints 建草图读取 `frame`，再加几何。面上草图同样依据 frame 定位。

pad 沿草图正法向，pocket/hole 沿负法向，reversed 翻转。旋转轴取草图水平/竖直轴。线性阵列 spacing 是相邻间距；圆周阵列 angle 是总扫角，2π 表示整圆均布。参考体坐标与模型坐标必须一致后才能比较。

pocket 切除范围二选一：`length` 表示定深；`through_all: true` 表示沿指定方向贯通，不能同时传 length。从 XY 底面向上切通孔用 `reversed: true`。固定高度的草图和定深切除不会自动随上游加高延长；应按零件设计意图选择贯通。FreeCAD 贯通切除不提供闲置 Length 的编辑入口。

## 工程语义决定

- 工具粒度是一批草图和一个特征，避免逐线调用，也避免一次不可定位的大配方。P7/P8 各需 5 张草图和 5 个特征。
- 欠约束草图可继续使用，但明确回报求解状态；不人为加固定约束冒充完整设计意图。冲突、冗余、无解、无效特征阻止成功回执。FreeCAD 在事务内回滚，revision 仍可能增加，失败后重新 context。
- SOLIDWORKS 没有独立的空 Body2。new/body 返回 `body_state=pending_first_feature` 和仅属该打开文档的 body_ref，首个非合并 pad/revolve 后返回真正 Body2 持久引用。预留不声称产生实体或递增几何修订；之后必须采用新的 body_ref。
- 直孔在 FreeCAD 使用 `PartDesign::Hole`；SOLIDWORKS 使用全圆草图和原生 Cut，要求圆直径与 diameter 一致，孔径在草图命名尺寸中编辑。不推断孔向导标准、螺纹或公差；没有假冒 HoleWizard 特征。
- SOLIDWORKS 使用原生 Undo 分组，COM 写入后失败保留 `needs_review/unknown`，不承诺跨 API 原子回滚。必须读回真实错误码、草图状态和文档再处理。
- 所有新建/复制输出必须为工程内未使用路径；保存只能写当前文档自身已登记副本。执行端同时核对宿主实例、文档身份、配置、revision 和宿主登记资格。
- 写入前宿主持久化 operation_id 与请求指纹；new/copy 同时在工程保存原请求。超时只查原 ID；应用仅在回执匹配原请求、宿主会话、路径且文件确实存在时登记副本。started/not_found 不能解释为未执行，禁止换 ID 重做。
- 替换/撤销/手改后的结论仍绑定旧 `document`；每次工具使用返回的新 document，最终重新 check。没有引入第二套检查或评分算法。

## FreeCAD 沙箱外验收

不在 Codex 沙箱中启动 FreeCAD（此机器 Qt 的 CPU 检测被沙箱拒绝）。在独立 FreeCAD GUI 进程使用当前 checkout。以下变量不是产品配置，只供验收隔离：

```sh
cd /Users/huaiyi/.codex/worktrees/model-build/gongke-workbench
export GONGKE_MODELING_ROOT="$PWD"
export GONGKE_FREECAD_SESSION="$(mktemp -d /tmp/gongke-native-host.XXXXXX)/session.json"
/Applications/FreeCAD.app/Contents/MacOS/FreeCAD "$PWD/tests/e2e/native_modeling_host.FCMacro"
```

等控制台出现“原生建模验收桥接已启动”，在另一终端设置同一个 `GONGKE_FREECAD_SESSION`（用上一终端的完整路径），然后：

```sh
cd /Users/huaiyi/.codex/worktrees/model-build/gongke-workbench
/private/tmp/gongke-modeling-venv/bin/python tests/e2e/native_modeling_freecad.py \
  --endpoint "$GONGKE_FREECAD_SESSION" \
  --study /Users/huaiyi/Documents/gongke-workbench/out/drawing-to-model-study \
  --output "out/native-modeling-$(date +%Y%m%d-%H%M%S)"
```

Python 环境需要项目 `[dev]` 依赖；也可用另一个已安装依赖的 Python。脚本创建自己的应用服务、工程与 MCP 写绑定，不改其他桌面工程。宿主启动记录实际模块路径、hash 和版本；源码改变后必须重启验收宿主。每步通过真实 SDK、绑定 MCP、应用服务、HTTP 和 GUI 主线程执行，**不会导入参考 STEP 作为模型**。

产物：`project/p7.FCStd`、`project/p8.FCStd`、`acceptance.json`、逐次 `calls.jsonl`、`service.log` 及应用任务收据。断言失败返回非零并保留现场。

验收包括：

- 两件各至少 5 张原生草图，实际 PartDesign 特征树、有效单实体；没有用 `PartDesign::Feature` 导入体替代。
- 体积和包围盒对比独立 build123d 参考 metrics；`host.check` 比较图纸条件与多个参考截面，防止漏筋、孔径或槽位置错误被总量掩盖。
- P7 把 Tube.Length 改错，使总高 28 mm，check 必须 fail；再改回 12 mm，最终总高 20 mm，check 必须 pass。
- 拒绝旧 revision、查询保存回执、只读绑定隐藏且拒绝写工具。
- 独立小零件验收旋转、直孔、圆角、倒角、镜像、线性/圆周阵列，带解析体积断言；面上草图、追加约束、依赖删除拒绝、叶特征删除和工作副本。

**本脚本的 pass 仍需实际输出确认。** 参考数据继承原试验：单位 mm 为无标题栏的试验假设，P7 左端 R10、P8 鼻端/耳部相切等假设保留在 acceptance 的 source 中。对比采用体积、包围盒与局部尺寸/截面，不使用原试验已发现不稳定的全形布尔差。

## Windows 真机验证

1. 从本分支构建 `adapters/solidworks/Gongke.SolidWorks.csproj`，`SolidWorksInteropDir` 指向正式安装的 `api/redist`。运行 `dotnet run --project adapters/solidworks/tests/ProtocolChecks.csproj -c Release`；加载新插件，`hosts.list` 必须声明 model.* 能力。
2. 使用专门的新工程与默认零件模板。MCP `host.model_new` 得到 pending Body；空批建 XY 草图，保存返回 frame，再批量画 20×10 mm 矩形、加入宽高尺寸并 pad 8 mm。核对产生真正 Body2、Sketch、Boss 特征和原生尺寸。
3. 新建圆草图（直径 4 mm）并 hole 贯穿 8 mm；inspect 检查 Cut 及圆柱面，check 孔径 4 mm；修改草图命名直径为 5 mm 后重查。面上草图也做一次，验证 face_ref、frame 和原生面关联。
4. 分别验收 revolve（草图水平/竖直轴）、圆角、45°等距倒角、基准面镜像、X/Y/Z 线性及圆周阵列。确认阵列方向、spacing、总扫角和数量；在原生特征面板核对参数。删除叶特征保留源草图，有下游依赖的删除必须拒绝。
5. 原件在工程目录中也必须拒绝写；model_copy 后可写。手工改尺寸后旧 revision 必须拒绝；模型重开、切换配置、换宿主后旧身份不能继续写。对已进入 COM 写入但未收到回执的请求，用同一 operation_id 查询，不新建重试。
6. 只读 MCP 绑定直接调用 host.feature/host.write 均拒绝。错误草图、无交集切除和过大圆角不得返回 committed；检查错误码、原生 Undo 分组和 host.context 新修订。
7. 保存并重开 .sldprt，在草图/特征面板手工改一个尺寸，重建通过。保留 MCP 收据、宿主版本、SLDPRT 和实际界面截图。

本机的 Interop 编译只证明签名与类型匹配，不能代替上述 SOLIDWORKS GUI/COM 真机验收。

## API 与同类方案依据

- [FreeCAD 官方 Sketcher scripting](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/Sketcher_scripting.md)：原生几何/约束及零起始几何索引；另核对本机发布包 `Mod/PartDesign/PartDesignTests/TestHole.py`、`TestMirrored.py`、`TestLinearPattern.py` 的实际属性用法；[1.1.4 Datums 源码](https://github.com/FreeCAD/FreeCAD/blob/1.1.4/src/App/Datums.cpp) 确认 Role 与基准面方向，使用真实 AttachmentSupport。
- [SOLIDWORKS FeatureExtrusion3](https://help.solidworks.com/2024/english/api/sldworksapi/solidworks.interop.sldworks~solidworks.interop.sldworks.ifeaturemanager~featureextrusion3.html)、[FeatureCut4](https://help.solidworks.com/2024/english/api/sldworksapi/solidworks.interop.sldworks~solidworks.interop.sldworks.ifeaturemanager~featurecut4.html)：m 单位、草图法向及实体选择 scope。
- [FeatureRevolve2](https://help.solidworks.com/2012/english/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.IFeatureManager~FeatureRevolve2.html)、[FeatureFillet3](https://help.solidworks.com/2025/English/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.IFeatureManager~FeatureFillet3.html)、[InsertFeatureChamfer](https://help.solidworks.com/2024/english/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.IFeatureManager~InsertFeatureChamfer.html)：旋转与修饰特征签名。
- [Mirror 选择标记](https://help.solidworks.com/2023/English/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.IFeatureManager~InsertMirrorFeature2.html)、[Pattern feature data](https://help.solidworks.com/2023/English/api/sldworksapiprogguide/OVERVIEW/Pattern_Features_and_their_Feature_Data_Objects.htm)：阵列使用 CreateDefinition/CreateFeature，不增加旧版本兼容分支。
- [ModelToSketchTransform](https://help.solidworks.com/2022/english/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.ISketch~ModelToSketchTransform.html)：虽然 Interop 有 setter，官方明确 setter 未实现，因此读取 frame，不尝试强改模板坐标系。
- [mcp-freecad](https://github.com/seansackowitz/mcp-freecad)：同类项目以细粒度 sketch/PartDesign 工具组织能力；本实现结合已有统一清单采用批量草图，不引入它的任意属性/表达式执行入口，也不把其 README 当作本项目真机证据。

## 本轮已运行的证据

- 相关 Python 测试：86 passed，覆盖统一清单、MCP resource/prompt、工程绑定、只读开关、原件/旧修订拒绝、写入未知恢复、跨会话回执拒绝、FreeCAD 事务错误与表达式驱动尺寸保护。`out/native-modeling-validation/python.log`。
- 使用本机已有官方 `SolidWorks.Interop.*` 程序集编译 .NET Framework 4.8 插件：0 warning、0 error。`out/native-modeling-validation/solidworks-build.log`。
- 现有协议、回执和调度检查：51 passed。`out/native-modeling-validation/solidworks-protocol.log`。NuGet 漏洞源查询出现 NU1900 网络警告，协议程序正常结束。
- 验收 Python 的 CLI 入口和语法已检查；本轮没有在沙箱启动 FreeCAD，没有执行 SOLIDWORKS COM。待 Claude 沙箱外运行并回传 `acceptance.json` 与失败时的 `calls.jsonl/service.log`，再修正实机问题；Windows 按上节逐项验证。

## 合并主线检查模块后的修正（2026-11-03）

六处文件冲突已清除。`freecad/gongke/native_inspection.py` 与 `docs/model-inspection.md` 按主线最终版保留，逐字节比对主仓库一致；其余四个冲突文件仅在主线基础上接入建模工具清单、能力声明和分派，未替换只读检查逻辑。本次未运行 git 命令，合并索引及提交由外部完成。

依据 `/Users/huaiyi/.codex/worktrees/f755/gongke-workbench/out/model-inspection/api-probe.json`（FreeCAD 1.1.4），建模模块的约束枚举、约束重名检查、命名尺寸修改统一读取 `Constraint.Name` / `Constraint.Driving`，移除不存在的 `Sketch.getConstraintName()` / `Sketch.isDriving()`。探针中只有这两个历史方法报错；草图求解状态属性、`renameConstraint`、`setDatum`、`solve`、附着属性和特征状态方法均在实际 API 清单中。

镜像与阵列的 `Originals`、`MirrorPlane`、`Direction`、`Axis`、`Length`、`Angle`、`Occurrences` 另与本机发布包 `PartDesignTests/TestMirrored.py`、`TestLinearPattern.py`、`TestPolarPattern.py` 对照；孔属性与 `TestHole.py` 对照。[Quantity 构造器](https://github.com/FreeCAD/FreeCAD/blob/1.1.4/src/Base/QuantityPyImp.cpp) 和 [setDatum 实现](https://github.com/FreeCAD/FreeCAD/blob/1.1.4/src/Mod/Sketcher/App/SketchObjectPyImp.cpp) 确认长度 Quantity 传 mm、角度 Quantity 传 deg，接口仍使用 m/rad。以上是 API 核查，未代替本轮原生几何运行。

保留已修正的 P7/P8 `write(tool, **fields)`；补充特征验收脚本中的同类参数冲突也已修正，并增加命名草图直径修改后恢复的实机检查。新增回归不提供不存在的旧方法，覆盖驱动/引用尺寸、表达式锁定、命名/重名、尺寸单位转换、补充验收入口，以及桥接读写分派并存。

本次普通 Python 回归 **78 passed、14 deselected**，日志 `out/native-modeling-validation/merge-python.log`，完整命令 `merge-tests-command.json`。首次完整运行的 14 项服务/MCP 测试因本地 socket 绑定被沙箱拒绝（`Operation not permitted`）而失败或初始化报错，保留在 `merge-all-python.log`；没有将其计为通过。冲突标记扫描和所改 Python 文件语法检查通过。下一步：重启沙箱外独立 FreeCAD 宿主，使用新的输出目录重跑上面的 P7/P8 和补充特征验收；回传 `acceptance.json` 与失败时的 `calls.jsonl/service.log`。

## P7 加高后的通孔修正（run2）

原始证据保持在 `out/native-modeling-run2/calls.jsonl`。第14次检查为 pass；第15次修改 Tube.Length，回执为 0.020 m，修订 423→446；第16次 `tube_height` 实际为 **unknown / ambiguous_entity**，同时返回 `Body.Face7` 的 z=0.028 m 和 `Body.Face18` 的 z=0.020 m，并非仍为 pass。新顶面已证明几何加高，参数名称、Pad 的 Length 模式与方向没有失效。

根因是配方将 BoreSketch 固定在 XY+20 mm，Bore 用 20 mm 定深 Pocket 向下切。Tube 从 12 mm 加长至 20 mm 后，总高变为 28 mm，但孔只切到旧的 20 mm 位置，上方留下 8 mm 实心封顶。检查器按约定对两个候选面返回歧义；不应改成猜测其中一个面，也不应把 unknown 当成预期 fail。

公共建模契约增加 pocket 的 `through_all: true`，与 length 互斥。FreeCAD 设置原生 `Type="ThroughAll"`，SOLIDWORKS 的 FeatureCut4 使用 `swEndCondThroughAll`。P7 BoreSketch 改在 XY 底面，反向向上贯穿；其余目标尺寸、图纸条件和原有失败/恢复断言不变。这样孔随筒加高继续贯穿，仍保持5张草图与5个特征。

API 依据：[FreeCAD 1.1.4 Pocket](https://github.com/FreeCAD/FreeCAD/blob/1.1.4/src/Mod/PartDesign/App/FeaturePocket.cpp) 定义 Length/ThroughAll 并反转草图法向；[FeatureExtrude](https://github.com/FreeCAD/FreeCAD/blob/1.1.4/src/Mod/PartDesign/App/FeatureExtrude.cpp) 在 Length 模式读取固定 Length，在 ThroughAll 模式重新计算贯通长度，同时禁用 Length 编辑。本机发布包 `PartDesignTests/TestPocket.py::testPocketThroughAllCase` 也使用 `Type=1`。

验收在修改后增加 host.inspect 记录，要求包围盒顶高为28 mm，体积增量为 `π × (10²−7²) × 8 mm³`，同时仍要求原 `tube_height` 明确 fail，修复后完整条件 pass。没有修改 `tests/fixtures/model_inspection/cases.json` 或只读检查实现。

本次普通 Python：**43 passed、2 deselected**（已知沙箱禁止本地服务端口的两个 MCP 测试）；SolidWorks 官方 Interop 编译 **0 warning、0 error**。日志为 `out/native-modeling-validation/through-all-python.log`、`through-all-solidworks-build.log`；run2 诊断摘录为 `run2-diagnosis.json`。修正后的 FreeCAD 几何与完整 P7/P8 流程尚待重启沙箱外宿主、使用新输出目录验收。本次未运行 git 命令。

## 固定约束与错误恢复（真实 Agent 第四轮修复）

FreeCAD 的 Block 只接受一个完整几何，不能传点号。`fixed` 的 `point=center/start/end` 表示固定该点当前位置：原点映射为与原点重合，其他位置映射为 X/Y 尺寸或轴上约束。固定点不固定圆半径或弧端点；非原点命名展开为 `name_X/name_Y`，`added_constraints` 包含展开后的全部索引。约束构造前验证几何/点/重载，数值以浮点传递；非法组合在 Python 层返回错误并回滚。

第四轮 `Block(0,3)` 触发 FreeCAD 1.1.4 的未捕获 C++ `Py::TypeError` 退出。原请求已保留为回归夹具；真实宿主回归和两组 Agent 运行命令见 [试验记录第五轮](agent-modeling-trial.md)。25 秒桥接等待只限制请求等待，不能抢占 C++ 或恢复已退出进程；原生未知结果不自动重发。

第五轮两组均通过 8 项真实宿主回归，未再出现桥接退出。vision 的 13 次草图调用中有 6 次求解冲突/冗余及 1 次缺少 body_ref；MCP 引导补充端点相切已包含重合关系、整几何固定后不再叠加尺寸、有效欠约束可继续、追加草图仍需 body_ref 和最新 document。按需一次 `host.inspect` 获取拓扑，批量 `host.check` 核对尺寸与截面；不要求草图每步重复 inspect 或把自由度清零。不引入零件专用配方或脚本执行接口。

### 真实 Agent 回归补充（2026-11-03，第七轮）

FreeCAD 的三点圆弧保留输入方向，但 Sketcher 的点 1/2 按逆时针排序。对负法向圆弧，工具将 `start/end` 映射到原生 2/1；公开含义始终为三点输入的首末点，追加约束也相同，不增加持久化映射属性。真实探针见本地 `out/agent-modeling-dev/round7/arc-probe.json`。第六轮 P7 原调用同时有冗余关系：修复端点后从冲突变为明确冗余；回归保留原请求，再移除重复的圆心水平/等半径关系验证可拉伸及保存。`sketch_constraint_acceptance.py` 现在包含 10 项，每项都验证后续读写仍可用。

`host.sketch.geometry` 增加求解后的局部坐标（m）、圆心和半径，便于在生成特征前识别欠约束求解引起的漂移；不将输入坐标冒充求解结果。原生几何索引不变。创建轮廓与必要约束可一次提交；已有草图追加须 `geometry=[]`。这是公开回执的增量改动，原因是机器人 PDF 首轮直到实体检查才发现漂移，产生了整树删除重建。

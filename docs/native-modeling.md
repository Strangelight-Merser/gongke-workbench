# 原生零件建模

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

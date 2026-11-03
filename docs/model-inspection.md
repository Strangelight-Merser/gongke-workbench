# 通用只读模型检查

本轮决策（2026-11-03）：FreeCAD 与 SOLIDWORKS 共用 `host.context`、`host.inspect`、`host.section`、`host.measure`、`host.check`。工具清单仍在 `gongke_app/tools.py`，经 Commands / Hosts 执行，桌面服务、ACP 注入的 MCP、WorkBuddy MCP 不另建执行路径。不改前端。

- 文档引用由宿主产生：`host_instance / document_id / revision / configuration`；实体引用是该修订中的 `native_ref`。读取也验证文档身份和修订，禁止将旧 Face 编号用于新模型。
- 原生宿主负责读特征、草图、B-rep 与截面；应用层负责统一量测与逐项比较。只访问明确指定的对象，不自动绑定、重算、保存或切换文档。
- 几何全部转换为 m、m²、rad，坐标系为文档全局坐标；草图约束和宿主参数保留各自明确单位。圆柱面保留凹凸和角度覆盖，不能把所有圆柱面都叫通孔。
- 条件为用户确认的结构化量测、期望值、公差和来源，不解析自然语言来猜测工程语义。不符、缺失、歧义、待重建分别返回；缺失或未支持不算通过。
- 导入 STEP 只有 B-rep，没有原来的草图历史；如实返回导入特征。轴类绑定、校核和编辑仍是 FreeCAD 特有能力，不扩展为自动代做。

实现及验收记录见本文后续章节。

## 调用契约

1. `hosts.list` 发现 host_id 和原生命令能力。
2. `host.context({host_id})` 返回 `documents[].document` 与 `objects[].native_ref`。新建未保存的文档也能读取。FreeCAD 文档会话 UUID 与桥接实例 UUID 分离；SolidWorks 用打开文档的会话 UUID 和原生持久引用，关闭重开后旧引用失效。
3. `host.inspect({host_id, document, object_ref})` 返回特征、草图、面、边与状态。
4. 同样的三个字段可用于 `host.section / host.measure / host.check`。泛型 `host.read` 的 `model.context / model.inspect / model.section` 也经过相同 schema 校验；没有额外执行旁路。

`document` 必须完整回传四个字段：`host_instance`、`document_id`、`revision`（整数）、`configuration`。FreeCAD configuration 为空字符串。定位引用仅在返回的文档修订内有效；应用和宿主不为旧 Face 编号寻找替代对象。

`faces` 包含 `native_ref / kind / area`；平面增加 `point / direction`，圆柱面增加 `radius / point / direction / inward / angular_span`。圆柱的 point 是轴线到文档原点的垂足；平面的 point 是支撑平面到原点的垂足，未必位于有限面边界内。轴/法线均归一化，不因参数原点沿轴移动而误判孔位。

`edges` 包含精确长度、端点和解析圆弧参数；`samples` 仅为显示用的16段均匀参数采样，不能用于尺寸验收。截面在临时几何上计算面积与边，单位分别是 m²、m。

特征按原生引用、父级和依赖表达结构，返回原生类型、名称、参数、错误状态。FreeCAD 读取数值/枚举/文本属性、表达式以及草图约束、DoF、冗余/冲突状态。SolidWorks 读取特征关联尺寸（`parameter_scope=display_dimensions`）、几何关系和原生草图约束状态；不声称读取了每种 FeatureData 的全部选项，API 未提供通用 DoF 数值时返回 null。STEP 导入件不会凭空补出草图和参数历史。

量测种类：

| kind | 输入与语义 |
|---|---|
| diameter | 一个圆或圆柱面的直径 |
| axis_distance | 两条平行圆柱轴线的最短距离；不将偏斜轴距解释为孔中心距 |
| plane_distance | 两个平行支撑平面距离；需用户确认对应底面/顶面，不能推断所有局部壁厚 |
| coordinate | 所选几何 point 的 axis=0/1/2 分量 |
| edge_length | 一条原生边的弧长 |
| count | 满足筛选的**几何实体数**；分裂圆柱面不能直接当孔数 |
| section_area | 明确给定 plane.origin（m）、plane.normal 的截面面积 |
| parameter | 给定 feature 原生引用和 parameter 名称的数值，保留实际单位 |

selectors 可用 `native_ref` 精确定位；也可用 `kind/radius/direction/inward` 和 `point`、`near+within` 定位。半径/精确位置筛选容差固定为 1e-8 m，只用于识别，不是条件验收公差。平面 `offset` 必须同时给 direction，表示该方向上的支撑平面坐标。多个候选返回 ambiguous_entity；找不到返回 missing_entity。检查错误位置应使用允许覆盖偏差的 near 窗口，避免用期望的精确位置筛选而把偏移对象排除。

示例（document 与 native_ref 从当前宿主读取）：

```json
{
  "host_id": "freecad",
  "document": {"host_instance": "当前实例", "document_id": "当前文档", "revision": 1, "configuration": ""},
  "object_ref": "Body",
  "conditions": [
    {"id": "base_thickness", "source": "学生确认的图纸底厚标注",
     "measurement": {"kind": "plane_distance", "selectors": [{"native_ref": "Body.Face1"}, {"native_ref": "Body.Face2"}]},
     "expected": 8, "tolerance": 0.1, "unit": "mm"},
    {"id": "hole_spacing", "source": "学生确认的孔中心距标注",
     "measurement": {"kind": "axis_distance", "selectors": [{"native_ref": "Body.Face3"}, {"native_ref": "Body.Face4"}]},
     "expected": 116, "tolerance": 0, "unit": "mm"}
  ]
}
```

`host.check` 逐条返回原条件、SI 期望与公差、实际数值、定位、pass/fail/unknown。未知原因包含缺失、歧义、单位不符、待重建、不支持的量测组合。任何一项 fail 则总状态 fail；否则有 unknown 则总状态 unknown。模型读取与截面的修订不同则整个请求拒绝，不混用新旧模型。输入无效或宿主调用失败仍作为错误返回，不伪装成几何不符。

旧 `freecad.*` 轴类流程与 Windows 特有写命令仍有现存调用方，本轮未将它们改为兼容别名；新增任意零件检查只走上述公共入口。工作副本、写入回执和权限逻辑保持原执行器检查。

## 样本与原生验收

`tests/fixtures/model_inspection/` 收录原试验9份 STEP 的逐字节副本，manifest 保存 SHA-256。`cases.json` 为共同检查条件。8件参与正反验收；P7端部R9是缺尺寸假设敏感性样本，不当错误扣分。

- P7槽错移：右端半圆轴线 x 应为14 mm，变体为15 mm；总体积和包围盒不参与判定。
- P8漏筋：z=10 mm 截面理论面积为40×8 + 12×8 =416 mm²，漏筋为320 mm²。
- 另检验φ12错孔、漏槽、高28、漏底孔；参考体应逐项通过。
- 同时建立原生草图和带平移、旋转的Body，检查约束状态、世界坐标、只读前后内容相同，以及手改后旧修订被拒绝。

沙箱外运行原生采集验收（不会读取用户当前文档；仅创建并关闭测试文档）：

```sh
cd /Users/huaiyi/.codex/worktrees/f755/gongke-workbench
/Applications/FreeCAD.app/Contents/Resources/bin/python tests/e2e/model_inspection_freecad.py
```

脚本在 FreeCAD 初始化后固定当前 checkout 的包路径，并清除本验收进程中预载的 `freecad.gongke` 模块，防止旧安装工作台覆盖待测源码；不修改已安装工作台。启动时打印 bridge、native_shaft、native_inspection 和公共检查模块的实际来源，来源不符立即报错。通过会写 `out/model-inspection/freecad.json`（包含模块来源），并输出8件STEP及原生草图验收结果。失败保持非零退出，不能用替身结果替代。

公共入口验收：在新插件中手动打开样本，工作台启动服务并打开一个工程，然后用普通应用Python（已安装 app 依赖）运行：

```sh
python tests/e2e/model_inspection_host.py --state-dir /实际服务状态目录 --project /实际工程目录 --host-id freecad --case p7_slot_shift_1 --output out/model-inspection/freecad-mcp-slot.json
```

此脚本通过真实 MCP SDK / stdio / 应用服务检查当前活动文档。多个对象必须传 `--object-ref`，不会猜测。依次打开两个参考体和6个错误变体重复运行；结果必须满足 cases.json 的预期。ACP与WorkBuddy使用同一MCP入口，不另起一套宿主连接。

### FreeCAD API 探查

`tests/e2e/freecad_api_probe.py` 不导入采集器，逐件读取9份STEP，并建立与原生验收一致的Body、Sketch、Diameter约束和Pad。记录模块版本/路径、各实例的完整 `dir()`、关键属性、全部动态工程属性类型和值、几何读取与截面调用结果；覆盖Shape、Face、Edge、Wire、Solid、曲面/曲线、Vector、Placement、Rotation、BoundBox和Quantity。另记录引用尺寸、几何约束及Pocket/Hole/Fillet/Chamfer/Revolution/Groove/AdditiveBox默认实例，后者明确标记为未配置，不充当有效几何。输出还包含两份待核查源码的属性使用清单和哈希。

```sh
/Applications/FreeCAD.app/Contents/Resources/bin/python tests/e2e/freecad_api_probe.py > /tmp/fc-api-probe.log 2>&1
/Applications/FreeCAD.app/Contents/Resources/bin/python tests/e2e/model_inspection_freecad.py > /tmp/fc-inspect-rerun.log 2>&1
```

探查结果为 `out/model-inspection/api-probe.json`，单项不存在或读取失败会记录异常并继续；包含已知不存在的旧方法对照，因此 `completed_with_errors` 不代表探查中止，`aborted` 才是中止。每个临时文档关闭后落盘，原样本不修改。验收成功仍写 `freecad.json`；失败需查看本次日志，不能将旧结果当成本次成功。

沙箱外第二次验收已确认模块来源正确，随后在原生草图的 `getConstraintName` 处失败。采集器现改为直接读取 `Constraint.Name` 和 `Constraint.Driving`，依据 [FreeCAD 1.1 ConstraintPy 实现](https://github.com/FreeCAD/FreeCAD/blob/1.1.0/src/Mod/Sketcher/App/ConstraintPyImp.cpp)。本次普通Python回归34项通过（包含驱动/引用尺寸属性与探查错误记录）；已知受沙箱端口限制的MCP测试未重跑，原生探查及几何验收待沙箱外执行。

### Windows / SOLIDWORKS

1. 使用目标机器安装的 `SOLIDWORKS/api/redist` 运行 `adapters/solidworks/scripts/build.ps1`，按 adapter README 安装新插件。
2. 原生打开或导入8件验收样本，保持STEP坐标，不自动旋转、更改单位或修复形状；记录单位与轴向。用 `hosts.list` 取得实际 host_id。
3. 用上述公共入口脚本逐件运行，host_id 换为发现的 SolidWorks ID；确认参考体通过及每个错误项被检出。特别验证临时 sheet 与 solid 的 `Operations2` 截面结果、孔面朝向、面积内环。
4. 另建一个带完全约束/欠约束/冲突草图和拉伸、孔、圆角的原生零件，检查特征结构、尺寸参数、草图状态和定位引用；改尺寸、切配置、关闭重开后旧document必须拒绝。
5. 检查前后比较原件字节哈希、GetSaveFlag、GetUpdateStamp、当前选择与活动文档；只读调用不能改变它们。以多实体零件验证 object_ref 只读选定 Body，不合并另一实体几何。

## Qt neon 诊断

2026-11-03 本机 FreeCAD bundled Python 是 arm64，Qt6-main=6.8.3（hc9525f7_4）。两个独立证据：

- `sysctlbyname("hw.optional.neon")` 实际返回 -1，errno=1（EPERM）；不是返回CPU不支持。
- 直接导入 FreeCAD 与运行原生验收脚本均以134退出，打印 `Incompatible processor ... neon`，尚未读取 FreeCAD 用户文档或检查代码。

Qt 6.8.3 的 Darwin ARM 分支只有 sysctl 成功才设置 NEON 标志，随后以编译所需能力比对并中止。该证据指向沙箱拒绝CPU能力查询；没有证据支持清空配置、重装FreeCAD或模型代码错误。当前权限策略不允许申请沙箱外执行，因此保留应用配置，由 Claude 在沙箱外执行上面的原生脚本，并先确认 `sysctl -n hw.optional.neon` 返回1。不使用伪造CPU检测或改二进制绕过。

沙箱外复跑反馈：`hw.optional.neon=1` 且 FreeCAD 成功导入，确认 neon 故障来自沙箱。`/tmp/fc-inspect.log` 随后记录 `DocumentState.inspect_host` 缺失；当前源码有此方法，本机旧安装工作台副本没有。已修复上述验收脚本的导入隔离，并用子进程测试覆盖旧路径优先及旧模块预载两种情况，验证三个 model 调用及过期修订拒绝。修复后仍需沙箱外复跑完整几何验收。

## 本轮实际证据

- Python：134 passed，覆盖公共量测、单位与容差、定位歧义、过期截面、真实MCP SDK/stdio/应用服务调用、回执、原有工作副本保护及独立安装导入。宿主采集使用替身的测试已在文件中注明。
- SolidWorks：net48插件完整编译通过，0 warnings / 0 errors；51项协议/回执/调度检查通过。编译使用本机既有 `Visiativ.SOLIDWORKS.Interop 34.0.0` 再分发程序集，哈希与来源记录在 `out/model-inspection/sw-reference-provenance.json`；不是Windows安装SDK或COM运行证据。
- FreeCAD：沙箱外已通过原生导入，随后遇到并修复旧工作台模块导入冲突；尚无修复后的FreeCAD几何通过记录。
- 导入修复回归：`tests/test_model_inspection_bootstrap.py`、`tests/test_model_inspection.py`、`tests/test_native_bridge_transactions.py`、`tests/test_native_packaging.py` 合计31项通过；1项MCP/桌面共用入口测试在绑定 `127.0.0.1` 时被当前沙箱以 `EPERM` 拒绝，未执行到工具调用。两个验收脚本和新增回归测试均通过 `py_compile`。
- 日志：`out/model-inspection/pytest.log`、`sw-build.log`、`sw-protocol.log`、`freecad-launch.log`、`neon-diagnosis.json`。未运行Windows真机；未把模拟调用链记作ACP Agent/WorkBuddy客户端的实际点击验收。

## 依据

- [FreeCAD TopoShape API](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/TopoShape_API.md)、[TopoShape 实现声明](https://github.com/FreeCAD/FreeCAD/blob/main/src/Mod/Part/App/TopoShape.h)：原生section/slice与B-rep访问。
- [FreeCAD Placement](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/Placement.md)：全局放置；Shape自带对象Placement，不能再重复乘一次。
- [FreeCAD SketchObjectPyImp](https://github.com/FreeCAD/FreeCAD/blob/1.1.0/src/Mod/Sketcher/App/SketchObjectPyImp.cpp)：DoF/冲突/冗余状态读最后一次求解信息，不为只读采集主动solve。
- [SolidWorks ISketch成员](https://help.solidworks.com/2020/English/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.ISketch_members.html)、[GetRelations](https://help.solidworks.com/2016/english/api/sldworksapi/solidworks.interop.sldworks~solidworks.interop.sldworks.isketchrelationmanager~getrelations.html)、[GetErrorCode2](https://help.solidworks.com/2018/English/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.IFeature~GetErrorCode2.html)：只读草图、关系与特征错误。
- [PlaneParams](https://help.solidworks.com/2026/English/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.ISurface~PlaneParams.html?format=P&value=)、[FaceInSurfaceSense](https://help.solidworks.com/2025/English/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.IFace2~FaceInSurfaceSense.html)：法线与参数坐标含义。
- [CreatePlanarSurface2](https://help.solidworks.com/2022/English/api/sldworksapi/SOLIDWORKS.Interop.sldworks~SOLIDWORKS.Interop.sldworks.IModeler~CreatePlanarSurface2.html)、[CreateTrimmedSheet5](https://help.solidworks.com/2021/english/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.ISurface~CreateTrimmedSheet5.html)、[GetIntersectionEdges2](https://help.solidworks.com/2021/english/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.IBody2~GetIntersectionEdges2.html)：临时平面和临时体计算；官方明确提示Operations2用于sheet/目标体相交。仍须实测当前调用顺序。
- [Qt 6.8.3 qsimd.cpp](https://raw.githubusercontent.com/qt/qtbase/v6.8.3/src/corelib/global/qsimd.cpp)：Darwin ARM CPU探测和能力检查。
- 同类项目：[neka-nat/freecad-mcp](https://github.com/neka-nat/freecad-mcp)展示插件+外部MCP进程；[hjbaard/SolidWorks-MCP](https://github.com/hjbaard/SolidWorks-MCP)强调类型化工具和实际几何回读。借鉴两者的宿主内读取/外部协议分工，未引入它们的建模执行或任意代码入口；其README自报测试数不作为本项目证据。

## 交付状态

改动留在 f755 worktree，未push、未合并。创建 `codex/readonly-model-inspection` 分支时，共享Git目录创建 `refs/heads/...lock` 返回 `Operation not permitted`；当前仍为原来的detached HEAD，未产生提交。Claude审阅后可在沙箱外创建分支并提交，提交信息末尾使用：

```text
Co-Authored-By: Codex <noreply@openai.com>
```

# SOLIDWORKS 原生适配器

Windows x64、.NET Framework 4.8 COM add-in。加载到已有 SOLIDWORKS 进程，由工作台服务通过本地命名管道调用。原生 API 调用经仅消息窗口统一回到 `ConnectToSW` 所在宿主 STA 线程（SOLIDWORKS 2023 实机上 `OnIdleNotify` 不触发）。不会创建另一个 SOLIDWORKS 进程。

源码已完成真实 Interop 引用编译检查，独立协议测试通过；**尚未在 SOLIDWORKS 实机加载和运行**。读写、Undo、图纸更新、保存重开仍需要宿主验收。当前 `native_validation` 固定为 `unverified`，不把编译通过标成原生验收。

## 构建与安装

开发机需要 Microsoft .NET SDK 8，运行机需要已授权安装的 SOLIDWORKS 和 .NET Framework 4.8。使用该安装版本自带的 `api/redist` 引用；不下载或打包宿主 DLL。

```powershell
cd adapters\solidworks
powershell -ExecutionPolicy Bypass -File .\scripts\build.ps1 -InteropDirectory 'C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\api\redist'
```

关闭 SOLIDWORKS，再在提升权限的 **64 位 PowerShell** 中运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install.ps1
```

安装器只复制本适配器和 Newtonsoft.Json 到 `%ProgramFiles%\Gongke\SolidWorks`，使用 Framework64 RegAsm 注册 COM，写入 SOLIDWORKS Addins 与当前用户 AddInsStartup。重新打开 SOLIDWORKS，必要时在“工具 → 插件”启用 Gongke Workbench。安装不会启动宿主。若用另一管理员账户安装，启动勾选需在实际使用账户设置。

```powershell
.\scripts\diagnose.ps1
.\scripts\uninstall.ps1
```

诊断只读取注册信息并调用 `host.info`，不输出连接令牌。加载异常记录于 `%LOCALAPPDATA%\Gongke\diagnostics\solidworks-load.log`。卸载保留模型、图纸和操作回执。若加载失败，应保存诊断输出与 SOLIDWORKS 版本，不通过连续启动宿主排查。

## 服务协议

发现文件：`%LOCALAPPDATA%\Gongke\hosts\solidworks-<pid>.json`，包含 `pipe_name`、`token`、`session_id`、宿主版本、方法列表。目录和命名管道 ACL 仅允许当前 Windows 用户。一个宿主实例对应一个管道，工作台服务串行调用；不得把令牌放进日志或交付包。

管道路径为 `\\.\pipe\<pipe_name>`。UTF-8、每行一条 JSON：

```json
{"id":"request-1","method":"document.context","params":{},"token":"from-discovery-file"}
```

响应：`{"id":"request-1","result":...}` 或 `{"id":"request-1","error":{"code":"...","message":"...","outcome":"..."}}`。每个写方法的成功响应也携带 `outcome`、规范化的 `operation_id` 和 `session_id`。`outcome` 是终态依据，`status=saved` 只表示该方法的保存检查通过。

| outcome | 精确含义 | 后续操作 |
| --- | --- | --- |
| `applied` | 原生调用完成，并通过该方法的读回/文件检查 | 使用响应中的最新 revision；不代表机械专业验收 |
| `needs_review` | 已观察到修改或新文件，但有失败、警告或验证未通过 | 保留产物，检查 `issues`、错误/警告位与原生文档，不自动再写 |
| `not_applied` | 在原生修改调用前拒绝/取消，或同值请求没有调用 setter | 修正输入后重新审阅；原 UUID 的回执不会被重新执行 |
| `unknown` | 已进入原生调用但效果无法确定，或响应/回执丢失 | 查询原 `operation_id`，再读文档/尺寸；禁止换 ID 自动重发 |

`operation.get` 的 `state=finished` 表示调用已结束，**不等于写入成功**；须读取其 `outcome` 和 `response`。`started` 保留为未知。尺寸写入尝试后仅观察到旧尺寸，不能证明其他特征没有变化，因此仍为 `unknown`。

所有目标文档命令使用 `document_path`；零件同时使用 `configuration`。文档必须是当前保存过的原生文档；通过 `document.open` / `document.activate` 在工作台内选择。写操作额外要求：

- `session_id`：此次宿主会话。
- `operation_id`：UUID，同一意图重查或重试保持不变。
- `expected_revision`：最近 `document.context` 的 `GetUpdateStamp`；`document.open/activate` 不要求 revision，`selection.set` 要求。

`document.open/activate` 和 `selection.set` 也改变宿主状态，现在同样写日志并校验 `session_id`。应用 `gongke_app/hosts.py` 对未提供的会话自动补齐发现文件中的值，不覆盖调用方传来的旧会话；直接管道客户端必须显式传入。

`parameter.change`、`drawing.update`、`document.save` 在插件执行端只允许本次会话验证成功的工作副本路径。仅在应用工程文件中登记路径不能绕过插件检查。宿主重启后需要重新创建、验证副本；不新增跨会话授权迁移。`document.save` 仍只在原生插件协议提供，本次不扩大应用侧方法范围。

| 方法 | 额外参数 | 返回或作用 |
| --- | --- | --- |
| `host.info` | 无 | 宿主版本、会话、方法列表、验证状态 |
| `document.context` | 无 | 活动及已打开文档，路径、配置、修改标志、revision |
| `document.open` | `document_path`，零件的 `configuration` | 打开 `.sldprt` / `.slddrw` 并激活 |
| `document.activate` | `document_path`，零件的 `configuration` | 激活已打开的文档与指定配置 |
| `parameters.list` | 文档绑定 | 尺寸全名、SI 值、驱动状态、写入限制和持久引用 |
| `parameter.change` | 写绑定 + `parameter_name`, `expected_value`, `value` | 指定配置修改、重建、读回、可见 Undo 分组 |
| `selection.get` | 文档绑定 | 原生选择和持久引用 |
| `selection.set` | 文档绑定 + `persistent_reference`, `expected_revision` | 在原生文档选择对应对象，允许只读文档，拒绝旧快照 |
| `preview.mesh` | 文档绑定 | 按面组织的平铺三角顶点 `positions`，米，持久引用 |
| `drawing.inspect` | 文档绑定 | `active_sheet`、全部页和视图、模型引用、配置、标注失联和覆盖状态 |
| `drawing.update` | 写绑定 | 重建图纸，重新读取检查结果，不自动保存 |
| `document.save_copy` | 写绑定 + 新 `output_path`；图纸另加新 `output_part_path`, `expected_part_revision` | 从内存保存零件副本，或同时保存并重新绑定图纸与唯一引用零件 |
| `document.save` | 写绑定 | 保存已验证工作副本，返回错误及警告位；不关闭用户正在编辑的文档 |
| `drawing.export` | 写绑定 + `sheet`, 新 `output_path` | 导出已审核的当前页为 DXF；恢复全局多页导出设置 |
| `operation.get` | `operation_id` | 持久回执或明确 `not_found` |

长度使用米。`parameters.list` 的 `value` 与 `parameter.change` 的输入均为 SI，工作台负责显示为 mm。仅驱动的线性/直径尺寸可写；只读、从动、多实体、含设计表或方程的模型拒绝写入。工程语义仍标记 `unmapped`，尺寸可写不代表工程合理。

写操作开始前在 `%LOCALAPPDATA%\Gongke\receipts\solidworks\<session_id>` 落盘 `started` 回执，结束后原子替换为结果；保留方法、参数、指纹与开始/结束时间，便于定位部分输出。终态写盘失败保留未知状态，不将它改写成“宿主没有修改”。同 UUID、相同参数返回既有结果；不同参数拒绝。管道等待超时且尚未执行的命令会取消；已开始的返回 `unknown`，应通过原 operation_id 查询，禁止以新 ID 自动重试。宿主崩溃后保留的 `started` 回执只能结合实际文件和原生状态核对，不能视为未执行。

## 实现约束

- `ConnectToSW` 要求 STA；IPC 线程只处理 JSON/文件，不持有文档 COM 对象。`OnIdle` 检查连接线程并设执行标志，COM 泵消息导致同线程重入时留待下次 idle。入队和卸载共用短锁，锁内不执行 COM；执行中的请求不被卸载伪装成未执行。
- 参数写入分别记录 setter、重建、Undo 结束与读回故障；清理失败不会覆盖首个故障。Undo 只用于可见撤销组，不自动 `EditUndo`。重建后重新枚举尺寸，检查原路径和配置，再读取实际值。只在 setter 成功、重建成功、Undo 成功、读回相符且无异常时返回 `applied`。
- 所有副本先 `SaveAs3(Copy)` 从内存写入新的路径，再在确定目标未打开的条件下 `OpenDoc6` 从磁盘加载。检查类型、绝对路径、活动配置、非只读/非 view-only、当前配置尺寸、原件路径/配置/dirty/revision 与磁盘 SHA-256。只要有保存、打开或最终激活警告，保留副本并返回 `needs_review`。
- 单零件和成对副本都拒绝外部/上下文引用零件及与已打开文档冲突的目标文件名。成对副本限定一个已加载零件、一个配置；在关闭的新图纸上替换引用，先独立打开零件副本，再打开图纸副本，逐视图核对保存引用、实际加载对象和配置。只有完整检查通过才赋予两个文件修改资格。
- 保存前清空选择，避免 `SaveAs3` 受选中面/实体影响；原件内容不保存、不关闭，原有 dirty 标志保留。`source_state_preserved` 核对内容身份与保存状态，不表示保留原选择集或窗口焦点。成功后激活副本，继续编辑。
- 应用侧单零件登记新增强制条件：`reopen_verified`、`parameter_values_verified`、`source_state_preserved` 均严格为 true，返回路径必须等于请求输出路径；成对副本沿用两个文件和引用验证契约。直接返回和 `operation.get` 恢复走同一检查。
- `document.save` 的验证是 Save3 返回值、错误/警告和文件存在性，不宣称重开。DXF 导出仅通过原生保存检查；全局多页导出设置在 finally 恢复并读回，恢复失败保留文件回执、返回需处理。DXF 单位/比例/实体仍需下游检查。

## Windows 实机验证清单

在已安装 SOLIDWORKS 的 Windows x64 上，用其官方 `api/redist` 构建并加载插件。准备专门的练习目录：一个无外部引用、含可驱动长度尺寸的单实体零件（两个配置），一个所有视图引用其中同一配置的两页图纸。另准备只读、方程驱动和外部引用样例。测试不得使用唯一原件。保存请求 JSON（去掉 token）、响应、原始 session_id、操作 UUID、原件 SHA-256 与界面截图。

每次修改前重新调用 `document.context` / `parameters.list`；新意图使用新 UUID，重查和重放原意图保持原 UUID 及全部参数不变。原生路径传绝对路径；经工作台调用时输出路径传工程内相对路径。

| 步骤 | 操作及必须保留的证据 | 预期 |
| --- | --- | --- |
| 1. 加载与线程 | 运行 `scripts/diagnose.ps1`；调试器记录 ConnectToSW、OnIdle、SetSystemValue3 的线程和 apartment | 同一 STA 线程，后台管道线程不调用文档 COM |
| 2. 未保存编辑的单零件 | 在原件手工改长度并重建，不保存；读取原件 hash/dirty/revision；调用 `document.save_copy` 到新 `.sldprt` | 实际打开副本，参数包含未保存编辑；三个验证标志 true，原件 hash/dirty/revision 不变，副本获得修改资格 |
| 3. 选择与同名文件 | 选中一个面后复制；另用与已打开文件同名的新路径复制 | 完整模型副本；同名目标在保存前拒绝，不覆盖任何文件 |
| 4. 成对副本 | 激活图纸；提供 `expected_part_revision`、两个新路径；调用 save_copy | 两个文件分别从磁盘打开；每个视图路径指向副本零件，配置/参数相符；原零件和原图纸保持原状态 |
| 5. 正常改参 | 在已验证副本用当前 revision/value 修改一个长度；随后读回并查看 Undo | `applied`、新实际值正确、rebuilt/undo_recorded=true；手工 Undo 后原生尺寸恢复，旧 revision 请求被拒绝 |
| 6. 修改失败与清理失败 | 用会导致几何重建失败的尺寸；调试构建分别在 setter 后、重建后抛异常，在 Undo finish 返回 false/抛异常（只在测试构建注入） | 已改且可读回为 `needs_review`；`issues` 同时保留原故障和清理故障；绝不宣称回滚。无法读回为 `unknown` |
| 7. 原件保护与旧绑定 | 直接管道尝试修改/保存原件；提交旧 session、旧 revision、旧 expected_value、只读/从动尺寸 | `not_applied`；原件和副本不变；不能通过绕过工作台获修改资格 |
| 8. 回执与去重 | 用相同 UUID/参数重复请求，换请求 id；再用相同 UUID 改 target；通过 operation.get 查询 | 原操作仅执行一次；相同意图返回原结果；改参数报 operation_conflict；查询含原响应与指纹 |
| 9. 超时与重入 | 模态界面阻止 idle 超过 45 秒；另一轮在 setter 后暂停超过 45 秒，恢复后查询；执行期间由调试器触发嵌套 OnIdle | 排队超时 not_applied 且恢复 idle 后不执行；执行中超时 unknown，最终回执仍可查询；嵌套 idle 不消费下一项 |
| 10. 部分副本与警告 | 用仅测试进程持有的目标文件锁制造保存/重开失败；成对副本在第一个文件写成后阻断第二个文件；测试有加载警告的样例 | 保留已有文件，needs_review 或 unknown，应用不登记任何未完整验证的副本，不自动重做 |
| 11. 断连/崩溃/卸载 | 请求发出后断开客户端，再查原 UUID；测试进程在 started 后结束；卸载前留一个排队请求 | 断连不重放；崩溃目录保留 started，结合 params/磁盘/原生值核对；排队项取消，执行项不能假报未执行。新会话不继承旧写权限 |
| 12. 图纸、保存与导出 | 修改已验证副本后 drawing.update；调用原生 document.save；导出指定当前页；检查原全局 DXF 设置 | 更新有明确 outcome；保存返回错误/警告；DXF 只含指定页、preference_restored=true；在 AutoCAD 等下游核对单位/比例/实体 |

`operation.get` 只查当前宿主会话的回执，不重放写入。宿主重启后，旧会话回执在上述目录按原 UUID 读取；不要用新会话的 `not_found` 推断旧操作未执行。将旧回执中的参数、原始文件和新打开的原生状态对照后，再由用户决定后续处理。

## 本次验证与依据

2026-11-03，macOS：使用本机已有 .NET SDK 10.0.403 构建 net48 x64，0 错误、0 警告；协议项目运行于 .NET 8，51 项检查通过（字段/指纹、回执持久化、线程、重入、两种超时、参数故障后的读回与终态）。应用测试 `tests/test_app_service.py` 为 19 passed、1 skipped；新增 `tests/test_app_contract.py` 为 19 passed。未运行上表 Windows 宿主步骤。

编译使用现存 `out/sw-build/refs` 下的 Interop DLL（原有记录为第三方 NuGet `Visiativ.SOLIDWORKS.Interop 34.0.0` 分发）；仅验证 API 签名，不将这些 DLL 打包或作为官方 SDK 来源证明。正式 Windows 构建仍必须用安装机官方 `api/redist`。本机 dotnet 的 NuGet HTTPS 还原遇到证书错误，随后从已有 NuGet 包缓存建立临时本地源完成还原，未关闭 TLS 验证、未增加依赖。

```shell
dotnet run --project adapters/solidworks/tests/ProtocolChecks.csproj -c Release
python -m pytest adapters/solidworks/tests/test_app_contract.py tests/test_app_service.py -q
```

- [COM STA 与同线程重入](https://learn.microsoft.com/en-us/windows/win32/com/single-threaded-apartments)：线程一致不等于不会重入，因此额外设执行标志；不在宿主线程等待 IPC Task。
- [OnIdleNotify](https://help.solidworks.com/2026/english/api/sldworksapi/SOLIDWORKS.Interop.sldworks~SOLIDWORKS.Interop.sldworks.DSldworksEvents_OnIdleNotifyEventHandler.html)：消息处理后的回调入口；[xCAD 的同类实现](https://github.com/xarial/xcad/blob/master/src/SolidWorks/SwApplication.cs)也通过该事件发布 idle，但本插件仍需自己的队列重入保护。
- [StartRecordingUndoObject](https://help.solidworks.com/2025/English/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.IModelDocExtension~StartRecordingUndoObject.html) 与 [FinishRecordingUndoObject2](https://help.solidworks.com/2016/english/api/sldworksapi/solidworks.interop.sldworks~solidworks.interop.sldworks.imodeldocextension~finishrecordingundoobject2.html)：起始方法无返回值，结束方法返回 bool，仅支持 Undo 的操作能撤销；没有异常回滚保证。
- [SetSystemValue3](https://help.solidworks.com/2013/english/api/sldworksapi/solidworks.interop.sldworks~solidworks.interop.sldworks.idimension~setsystemvalue3.html)：可以改只读尺寸，所以必须保留执行端的只读/从动检查。[EditRebuild3](https://help.solidworks.com/2019/english/api/sldworksapi/SOLIDWORKS.Interop.sldworks~SOLIDWORKS.Interop.sldworks.IModelDoc2~EditRebuild3.html)要求活动文档，并仅重建活动配置需要更新的特征。
- [SaveAs3](https://help.solidworks.com/2021/English/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.IModelDocExtension~SaveAs3.html)：核对返回值、错误及警告；清空选择；文件存在不能替代重开验证。
- [OpenDoc6](https://help.solidworks.com/2019/english/api/sldworksapi/SOLIDWORKS.Interop.sldworks~SOLIDWORKS.Interop.sldworks.ISldWorks~OpenDoc6.html)：已打开文件可能复用内存对象，配置不存在时可能使用上次配置，因此重开前检查未打开，之后检查真实配置和路径。
- [ActivateDoc3](https://help.solidworks.com/2023/english/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.ISldWorks~ActivateDoc3.html)：用含扩展名的文件名激活，再核对返回路径，避免同名零件/图纸混淆；返回值非空仍可能带重建警告。
- [ReplaceReferencedDocument](https://help.solidworks.com/2018/English/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.ISldWorks~ReplaceReferencedDocument.html)：引用方必须关闭；替换成功不证明内部 ID、尺寸或关系有效，因此在重开后核对实际引用与尺寸。

## 通用只读建模检查

新增 `model.context / model.inspect / model.section`，由应用层 `host.context / host.inspect / host.section / host.measure / host.check` 使用。读取绑定宿主实例、文档会话UUID、配置与修订；支持未保存零件，使用原生持久引用定位实体。截面仅对临时Body计算，不重建、不保存、不改变选择。特征参数范围为关联原生尺寸，不枚举任意 FeatureData 成员。

公共参数、单位、条件示例、试验样本及 Windows 真机验收步骤见 [通用只读模型检查](../../docs/model-inspection.md)。本机编译通过不代表 Windows COM 行为通过。

# SOLIDWORKS 原生适配器

Windows x64、.NET Framework 4.8 COM add-in。加载到已有 SOLIDWORKS 进程，由工作台服务通过本地命名管道调用。原生 API 调用统一进入 `OnIdleNotify` 所在宿主线程。不会创建另一个 SOLIDWORKS 进程。

源码已完成真实 Interop 引用编译检查，独立协议测试通过；**尚未在 SOLIDWORKS 实机加载和运行**。读写、Undo、图纸更新、保存重开仍需要宿主验收。当前 `native_validation` 固定为 `unverified`，不把编译通过标成原生验收。

## 构建与安装

开发机需要 Microsoft .NET SDK 8，运行机需要已授权安装的 SOLIDWORKS 和 .NET Framework 4.8。使用该安装版本自带的 `api/redist` 引用；不下载或打包宿主 DLL。

```powershell
cd adapters\solidworks
.\scripts\build.ps1 -InteropDirectory 'C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\api\redist'
```

关闭 SOLIDWORKS，再在提升权限的 **64 位 PowerShell** 中运行：

```powershell
.\scripts\install.ps1
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

响应：`{"id":"request-1","result":...}` 或 `{"id":"request-1","error":{"code":"...","message":"...","outcome":"not_applied|unknown"}}`。

所有目标文档命令使用 `document_path`；零件同时使用 `configuration`。文档必须是当前保存过的原生文档；通过 `document.open` / `document.activate` 在工作台内选择。写操作额外要求：

- `session_id`：此次宿主会话。
- `operation_id`：UUID，同一意图重查或重试保持不变。
- `expected_revision`：最近 `document.context` 的 `GetUpdateStamp`。

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
| `document.save` | 写绑定 | 保存该原生文档，返回错误及警告位 |
| `drawing.export` | 写绑定 + `sheet`, 新 `output_path` | 导出已审核的当前页为 DXF；恢复全局多页导出设置 |
| `operation.get` | `operation_id` | 持久回执或明确 `not_found` |

长度使用米。`parameters.list` 的 `value` 与 `parameter.change` 的输入均为 SI，工作台负责显示为 mm。仅驱动的线性/直径尺寸可写；只读、从动、多实体、含设计表或方程的模型拒绝写入。工程语义仍标记 `unmapped`，尺寸可写不代表工程合理。

写操作开始前在 `%LOCALAPPDATA%\Gongke\receipts\solidworks\<session_id>` 落盘 `started` 回执，结束后原子替换为结果。同 UUID、相同参数返回既有结果；不同参数拒绝。管道等待超时且尚未执行的命令会取消；已开始的返回 `unknown`，应通过原 operation_id 查询，禁止以新 ID 自动重试。宿主崩溃后保留的 `started` 回执只能结合实际文件和原生状态核对，不能视为未执行。

## 当前边界与实机验收

- 目标是原生 API 工作流，不嵌入或改造 SOLIDWORKS 窗口。预览网格只作显示，不能用于制造、测量或仿真精度保证。
- 写入前核对路径、配置、revision、当前尺寸；重建/读回失败返回 `needs_review`，不声称撤销或恢复成功。Undo 只包围单文档尺寸修改；没有跨文档原子撤销。
- 零件副本从当前内存保存，拒绝外部/上下文引用。图纸成对副本限定为所有模型视图指向同一已加载零件和同一配置：分别通过 `SaveAs3(Copy)` 写入新的 `.sldprt` 与 `.slddrw`，在未打开的新图纸上调用 `ReplaceReferencedDocument`，再打开新图纸，读取每个视图的保存引用与实际加载模型、配置及零件尺寸。两个目标必须不存在，且文件名不能与宿主已打开文档同名。原件保持打开，不调用原件保存；源文件 SHA-256、原文档路径/配置/dirty/revision 在操作前后必须一致。
- 成对副本返回 `working_copies` 与每项 `verified`；仅当关联、参数读回和原件状态核对均通过时，返回 `status=saved`。失败保留已产生文件并返回 `needs_review` 或 `unknown`，不得自动重做或把它们登记为可改工作副本。当前 API 逻辑通过编译但未在宿主验证，特别是 `SaveAs3(Copy)` 对 dirty 状态、内部文档 ID 与引用重载的实际行为仍待实测。
- 图纸检查覆盖 API 可枚举显示尺寸、失联与数值覆盖；不代表全标注、公差、规范及机械专业验收。
- 图纸 DXF 导出后还需由下游读取验证单位、比例和实体。`SaveAs3` 返回成功与文件存在仍不等于保存重开验收。
- 接收方实测：先加载插件并运行诊断；在练习副本读取版本/文档/参数/网格；修改一个已确认驱动尺寸；检查原生值、重建和 Undo；保存、关闭重开后再读；检查关联图纸并导出 DXF；重新接入 AutoCAD 检查单位和实体。原生操作结果与日志须保留，任何一步未验证都保留该状态。

## 验证与 API 依据

本轮 macOS 上以 .NET SDK 8.0.427 编译 net48 x64，引用来自 NuGet 公共包 `Visiativ.SOLIDWORKS.Interop 34.0.0` 的实际 DLL，仅用于 API 引用检查。它是第三方分发，包内没有许可证文本，不能替代官方 SDK 来源核验；文件只在忽略的 `out/sw-build` 内，不进入仓库或安装包。正式构建脚本要求安装机官方 `api/redist`。构建结果为 0 错误、0 警告，输出未包含宿主 Interop DLL。独立测试用 .NET 8 执行源代码中的协议、持久回执与线程队列逻辑，18 项通过；这些不覆盖 COM、Windows ACL 或宿主行为。

四份 PowerShell 脚本另经 Microsoft.PowerShell.SDK 7.4.6 语法解析，均无语法错误；Windows 注册、加载与卸载尚未执行。

```shell
dotnet run --project adapters/solidworks/tests/ProtocolChecks.csproj -c Release
```

- [官方 Add-in 生命周期](https://help.solidworks.com/2020/english/api/sldworksapiprogguide/Overview/Using_SwAddin_to_Create_a_SolidWorks_Addin.htm)
- [OnIdleNotify 主线程派发入口](https://help.solidworks.com/2025/english/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.DSldWorksEvents_OnIdleNotifyEventHandler.html)
- [指定配置读值 GetSystemValue3](https://help.solidworks.com/2020/english/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.IDimension~GetSystemValue3.html)
- [SetSystemValue3 及只读尺寸警告](https://help.solidworks.com/2025/English/api/sldworksapi/SolidWorks.interop.sldworks~SolidWorks.interop.sldworks.IDimension~SetSystemValue3.html)
- [原生 Undo 分组](https://help.solidworks.com/2018/English/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.IModelDocExtension~FinishRecordingUndoObject2.html)
- [SaveAs3 错误、警告与保存限制](https://help.solidworks.com/2021/English/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.IModelDocExtension~SaveAs3.html)
- [闭合副本上的 ReplaceReferencedDocument 及内部 ID 限制](https://help.solidworks.com/2018/English/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.ISldWorks~ReplaceReferencedDocument.html)
- [CopyDocument 要求无任何打开文档，因此不用于保留当前未保存编辑的会话](https://help.solidworks.com/2019/english/api/sldworksapi/SOLIDWORKS.Interop.sldworks~SOLIDWORKS.Interop.sldworks.ISldWorks~CopyDocument.html)
- [面三角网格及显示用途限制](https://help.solidworks.com/2018/English/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.IFace2~GetTessTriangles.html)

# AutoCAD 原生连接

Windows 完整版 AutoCAD 2026 的 Managed .NET 插件。工作台通过本机命名管道读取活动工程，操作真实实体；CAD API 只在 AutoCAD UI 线程执行。本文是安装集成和开发接口说明。

当前已用 Autodesk 官方 NuGet 引用分别编译 .NET 8 和 .NET 10 版本，并运行本机管道、回执、取消和不覆盖文件检查。尚未在 Windows AutoCAD 内执行，安装、原生编辑、Undo 和保存重开均须现场验证。不能将 SDK 编译结果标为原生接入通过。

## 版本与安装

| 宿主 | 构建 | 真实编译引用 |
|---|---|---|
| AutoCAD 2026 至 Update 1.1 | net8.0-windows | AutoCAD.NET 25.1.0 |
| AutoCAD 2026 Update 1.2 及后续 | net10.0-windows | AutoCAD.NET 25.1.1 |

Autodesk 官方兼容表明确列出了 2026.1.2 的运行时切换。安装器只读检查宿主 `AcMgd.dll` 的 `TargetFrameworkAttribute` 标记选择包，不仅判断产品年份。首版 bundle 仅声明 R25.1；未声明 AutoCAD LT、Mac、2025、2027 或专业垂直产品支持。

产品安装器应提升权限运行生成包中的 `Install.ps1`，关闭 AutoCAD 后将匹配的 `.bundle` 安装到 `%PROGRAMFILES%\Autodesk\ApplicationPlugins`。下一次启动自动加载，无需 NETLOAD、宏、手动复制 DLL 或修改 SECURELOAD/TRUSTEDPATHS。脚本校验插件身份、宿主运行时、程序集 SHA-256；不会启动或关闭用户 CAD。AutoCAD 如果由管理员设定 `APPAUTOLOAD=0`，仍需由管理员处理该设置，本插件不静默绕过。用户升级 AutoCAD 运行时后应重新运行产品的连接安装。

```sh
python adapters/autocad/scripts/build.py --dotnet dotnet
```

构建需要 .NET 10 SDK（同时可构建 net8），通过 `packages.lock.json` 锁定官方引用；首次生成锁文件后，正式构建使用 locked restore。输出为 `adapters/autocad/artifacts/` 的两组 bundle、安装/卸载脚本和摘要清单。包只含本项目程序集，不携带 Autodesk DLL 或固定宿主运行时的 runtimeconfig。

## 本机协议

发现文件：`%LOCALAPPDATA%\Gongke\hosts\autocad-{pid}.json`。

```json
{"host_id":"autocad-<session>","host":"autocad","instance_id":"<session>","pid":123,"transport":"named_pipe","pipe_name":"gongke-autocad-123","token":"<random>","protocol_version":1}
```

客户端以当前 Windows 用户访问 `\\.\pipe\gongke-autocad-{pid}`，每行一个 UTF-8 JSON，长度至多 1 MiB。所有请求带发现文件中的 token；文件仅限本地连接使用，不进入诊断包、模型上下文或远程日志。

```json
{"id":"request-1","token":"<random>","method":"documents.list","params":{}}
{"id":"request-1","result":{"documents":[]}}
```

错误结构为 `{id,error:{code,message,outcome}}`，`outcome` 为 `unchanged` 或 `unknown`。写入成功结果含 `outcome:"committed"`。不向客户端暴露任意命令、AutoLISP、脚本或 shell。

| method | params | 结果 |
|---|---|---|
| `host.describe` | `{}` | 版本、运行时、能力、验证边界 |
| `documents.list` | `{}` | 文档会话、revision、路径、活动状态、单位；非活动文档 dirty 为 null |
| `document.snapshot` | `document_id, offset?, limit?` | 直接模型空间/图纸空间实体，分页、类型计数、真实几何/文字/测量值；后续分页必须带 `expected_revision` |
| `document.select` | `document_id, expected_revision, handle` | 选中真实实体并切换其所属布局 |
| `drawing.edit_text` | `operation_id, document_id, expected_revision, handle, text` | 仅 TEXT/MTEXT 普通文字；原生事务、重生成、读回 |
| `drawing.move_dimension_text` | `operation_id, document_id, expected_revision, handle, position:[x,y,z]` | 仅原生 DIMENSION 文字位置；保持测量值、显示覆盖文本不变 |
| `drawing.import_dxf` | `operation_id, source_path, target_path` | 用全新空 Database 导入 DXF，新 DWG 保存及磁盘重开 |
| `document.save_copy` | `operation_id, document_id, expected_revision, target_path` | 复制当前内存数据库（包括未保存修改），保存新 DWG，磁盘重开；原窗口保持打开 |
| `document.open` | `path` | 打开或激活现有 DWG；返回新文档会话 |
| `operation.status` | `operation_id` | queued/running/completed/failed/unknown 与原回执 |
| `operation.cancel` | `operation_id` | 仅取消尚未开始的操作；运行中的原生事务不会被强杀 |

文件路径必须为 Windows 绝对路径；目标 DWG 必须不存在。先写同目录唯一暂存文件，再原子移动且禁止覆盖，避免检查后文件出现的竞态。`save_copy` 不修改原文档名称，也不会自动切换活动文档。因此工作台应先 `save_copy` 创建工作副本，再 `open` 副本，之后才编辑；不能把用户原工程的活动内存当作新修订。

文档身份是进程会话＋原生 Document 实例，实体以 handle 定位。对象增加、修改、删除事件推进 revision，包括宿主内的人工修改；旧 revision 的写入会拒绝。快照包含 WCS 坐标、图层、实体类型、样式和支持的几何信息。LWPOLYLINE/POLYLINE 保留 bulge；圆弧保留法向；DIMENSION 保留 subtype、真实 measurement、text_override、Dimlfac、Dimscale。不能把导出的 LINE/TEXT 片段当作尺寸。嵌套块/Xref只显示其原生类型，不展开、不允许写入；锁定图层及字段驱动文字拒绝编辑。

管道线程只收发消息；Idle UI 回调调度原生操作。文字与标注操作通过 `ExecuteInCommandContextAsync` 进入命令上下文，持有 DocumentLock 和原生事务。普通文字不接受字段表达式；MTEXT 输入为纯文本并转义格式控制；标注仅移动文字，不修改测量或伪造显示数值。

每个写请求必须有唯一 operation_id。同一请求再次送达只返回状态和原回执，不重做；同 ID 不同参数拒绝。调用超时、断连、程序退出之后，客户端必须查询 operation.status 并核对快照。插件重启后未知 ID 返回 unknown，不解释成未执行。会话内回执和本机 JSONL 运行记录供诊断；不是跨重启恰好执行一次的保证。

## 验证入口

```sh
dotnet run --project adapters/autocad/Gongke.AutoCAD.ContractTests -c Release
python adapters/autocad/scripts/make_fixture.py out/autocad-native-fixture.dxf
```

协议检查实际运行本机命名管道，验证 token、队列、回执去重、取消和原件保护；它不使用伪造 Autodesk SDK。由本项目生成的 DXF 包含 LINE、LWPOLYLINE、ARC、CIRCLE、TEXT、MTEXT 和真实 DIMENSION，仅为合成测试图，不是机械设计依据。

`Test-Host.ps1` 是开发/现场验收入口：在已安装桥的 AutoCAD 中，通过同一管道导入合成 DXF、读取实体、修改文字、拒绝过期快照、移动尺寸文字、另存修订、重新打开并核对文字与源文件摘要。它只使用新路径，不覆盖图纸，不自动开 CAD。输出的 evidence 带实际通过状态；当前仓库没有声称执行过它。原生 Undo、人工修改后过期、复杂原生 DWG 的块/尺寸样式视觉检查仍需要真人宿主验收。

## 官方依据

- [Managed .NET 兼容版本表](https://help.autodesk.com/cloudhelp/2026/ENU/AutoCAD-Customization/files/GUID-A6C680F2-DE2E-418A-A182-E4884073338A.htm)
- [Autodesk .NET 10 更新说明](https://blog.autodesk.io/autodesk-desktop-products-2025-2026-net-10-updates/)
- [Autodesk 官方 AutoCAD.NET 25.1.0](https://www.nuget.org/packages/AutoCAD.NET/25.1.0) / [25.1.1](https://www.nuget.org/packages/AutoCAD.NET/25.1.1)
- [DocumentLock 与原生事务](https://help.autodesk.com/cloudhelp/2022/ENU/OARX-DevGuide-Managed/files/GUID-A2CD7540-69C5-4085-BCE8-2A8ACE16BFDD.htm)
- [DxfIn 要求全新空数据库](https://help.autodesk.com/cloudhelp/2026/ENU/OARX-ManagedRefGuide/files/OARX-ManagedRefGuide-Autodesk_AutoCAD_DatabaseServices_Database_DxfIn_string_string.html)
- [.bundle 安装与受信任目录](https://help.autodesk.com/cloudhelp/2026/ENU/AutoCAD-Customization/files/GUID-5E50A846-C80B-4FFD-8DD3-C20B22098008.htm)
- [PackageContents 格式](https://help.autodesk.com/cloudhelp/2025/ENU/AutoCAD-Customization/files/GUID-BC76355D-682B-46ED-B9B7-66C95EEF2BD0.htm)

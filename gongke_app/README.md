# 应用服务

桌面主进程通过子进程标准输入输出调用此服务。发行包内包含解释器、工程核心、数据表和示例；开发入口为 `python -m gongke_app.service --state-dir <目录>`。服务标准输出只包含 JSON Lines，第三方库的输出转入标准错误。

请求为 `{"id":1,"method":"system.status","params":{}}`，响应为 `{"id":1,"result":...}` 或 `{"id":1,"error":{"message":"..."}}`。事件没有 `id`，以 `event` 区分。请求不自动重放，原生写操作超时后必须读回或查询原操作 ID。

| 方法 | 参数与结果 |
| --- | --- |
| `system.status` | 服务版本、是否打包、当前工程、模型配置状态；配置成功不代表连接已验证 |
| `project.create` | `path,name?,teaching?`；默认创建明确标记的教学工程，界面可传 `teaching:false` 创建空工程 |
| `project.open` | `path`，选择包含 `gongke-project.json` 的目录 |
| `project.current` / `project.files` | 工程清单、实际文件；不读取工程目录外的符号链接 |
| `project.set_task` | `task,teaching?`；校验条件后持久保存 |
| `project.read_file` | `path`，工程相对路径；最多 4 MiB 的 SVG、JSON 或文本 |
| `design.schema` / `design.example` | 任务书格式，或 `{teaching:true,task}` 教学条件 |
| `design.calculate` | `task?`；真实核心计算，返回全部检查和未通过项，不修改 CAD |
| `design.generate` | `task?,name?,step?,drawings?,report_docx?,full_teeth?`；返回异步任务，文件写入新的 `revisions/` 子目录 |
| `task.list` / `task.get` / `task.cancel` | 当前工程任务；详情和取消使用 `task_id`；详情包含真实工具执行收据 |
| `freecad.context` / `freecad.scene` | 当前原生上下文、带修订的实际显示网格和 TechDraw 页面 |
| `freecad.select` | `session_id,object_name,expected_revision`；同步原生选择，不修改几何，不要求工作副本 |
| `freecad.operation` | `session_id,operation_id`；只读查询原操作是否已提交，不重试写入 |
| `freecad.read` / `freecad.review` | `session_id,entity_id`；实际原生对象和受限工程复核 |
| `freecad.preview` | `session_id,entity_id,segment_id,diameter_m`；候选计算，不改几何 |
| `freecad.apply` / `freecad.undo` | 会话、候选/操作标识；实际原生事务和受限撤销 |
| `freecad.save` | `session_id,path`；只能保存为工程内尚不存在的 `.FCStd` 工作副本 |
| `freecad.update_drawing` | `session_id,page_name,expected_revision` |
| `freecad.export_drawing` | 同上，可选工程相对 `path`；省略时新建 `revisions/native-drawing-<id>/page.dxf` |
| `hosts.list` | 实际探测 FreeCAD 和已发现的 Windows 命名管道；发现文件存在不等于连接成功 |
| `host.command` | `host_id,method,params`；仅限应用允许且宿主声明的能力，原生参数由宿主验证 |
| `agent.configure` | `base_url,model,api_key`；仅保存在内存，不写清单、任务记录或日志 |
| `agent.run` | `message,allow_writes?`；真实 SSE 工具调用循环，返回异步任务；默认不允许工程写入 |
| `agent.disconnect` | 清除后续任务使用的模型配置；不自动终止已开始的任务 |

`task.updated` 提供执行阶段，`task.receipt` 提供工具结果，`agent.delta` 是模型文字增量，`agent.message` 是该轮完整文字。界面不应将任务 `complete` 解释为工程验收通过，须继续检查结果的 `calculation_ok`、`exports_complete`、`failed` 和来源缺口。部分导出失败为 `partial`；取消不等于撤销，正在运行的导出将结束后返回真实结果。

工程清单可携带，SQLite 任务和操作收据位于应用状态目录。进程中断后未完成任务标为 `interrupted`，不会恢复或重试原生写入。一个状态目录只允许一个服务进程。原生修改只允许针对清单中 `working_copies` 登记的副本；只有工作台收到成功保存/导入回执、核对目标路径并确认文件实际存在后才登记。放进工程目录的原件不会因此获得修改资格。保存与导出不覆盖现有文件。

发送原生保存副本或 DXF 导入前，工程清单中的 `copy_operations` 会保存原操作 ID、命令、参数、宿主会话与请求 ID。响应丢失后，查询同一操作可以核对终态成功回执并恢复副本登记，不重发写操作；SOLIDWORKS 还核对宿主保存的命令参数指纹。成对副本必须全部存在且引用与读回验证通过才一次登记。查询不属于当前工程记录的操作、宿主换会话、结果未知或文件缺失，均不会授予修改资格。此恢复可跨应用重启，不跨原生宿主会话。

`host.command` 的发送前校验拒绝返回 `error.outcome=not_applied`，用户可以随后另存工作副本。实际发送、结果读回或登记失败仍需保留原操作并查询，不能把这些失败当作没有执行。重复查询成功操作不会重复登记。

模型服务采用 Chat Completions SSE 的函数工具调用协议。服务发送受限工具列表、当前工程摘要和用户目标，逐轮消费真实工具结果，最多执行 12 轮。没有 shell、任意代码或宏执行工具。缺少凭据时明确不可用；手动操作仍能使用。协议测试通过不代表某个真实账号或目标 CAD 宿主已经验收。

开发构建：安装项目 `desktop` 可选依赖后运行 `python tools/build_app_service.py`，产物位于 `desktop/service/gongke-service/`。Windows 包必须在 Windows 构建，macOS 包必须在对应架构上构建；PyInstaller 不交叉编译。数据表与示例在构建时按工程核心的资源路径放入包内，运行不依赖源码目录、`PYTHONPATH` 或用户 Python。

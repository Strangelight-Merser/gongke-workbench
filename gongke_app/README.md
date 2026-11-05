# 应用服务

桌面主进程通过子进程标准输入输出调用此服务。发行包内包含解释器、工程核心、数据表和示例；开发入口为 `python -m gongke_app.service --state-dir <目录>`。服务标准输出只包含 JSON Lines，第三方库的输出转入标准错误。

请求为 `{"id":1,"method":"system.status","params":{}}`，响应为 `{"id":1,"result":...}` 或 `{"id":1,"error":{"message":"..."}}`。事件没有 `id`，以 `event` 区分。请求不自动重放，原生写操作超时后必须读回或查询原操作 ID。

| 方法 | 参数与结果 |
| --- | --- |
| `system.status` | 服务版本、是否打包、当前工程 |
| `project.create` | `path,name?`；所有入口均创建空工程，不预置任务、结果或示例文件 |
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
| `freecad.save` | `session_id,path`；保存为工程内新的 `.FCStd` 工作副本，或保存当前文档自身已登记的副本 |
| `freecad.update_drawing` | `session_id,page_name,expected_revision` |
| `freecad.export_drawing` | 同上，可选工程相对 `path`；省略时新建 `revisions/native-drawing-<id>/page.dxf` |
| `hosts.list` | 实际探测 FreeCAD 和已发现的 Windows 命名管道；发现文件存在不等于连接成功 |
| `host.command` | `host_id,method,params`；仅限应用允许且宿主声明的能力，原生参数由宿主验证 |

`task.updated` 提供执行阶段，`task.receipt` 提供工具结果。界面不应将任务 `complete` 解释为工程验收通过，须继续检查结果的 `calculation_ok`、`exports_complete`、`failed` 和来源缺口。部分导出失败为 `partial`；取消不等于撤销，正在运行的导出将结束后返回真实结果。

工程清单可携带，SQLite 任务和操作收据位于应用状态目录。进程中断后未完成任务标为 `interrupted`，不会恢复或重试原生写入。一个状态目录只允许一个服务进程。原生修改只允许针对清单中 `working_copies` 登记的副本；只有工作台收到成功保存/导入回执、核对目标路径并确认文件实际存在后才登记。放进工程目录的原件不会因此获得修改资格。导出不覆盖现有文件；FreeCAD 可以保存当前文档自身已登记的工作副本。

发送原生保存副本或 DXF 导入前，工程清单中的 `copy_operations` 会保存原操作 ID、命令、参数、宿主会话与请求 ID。响应丢失后，查询同一操作可以核对终态成功回执并恢复副本登记，不重发写操作；SOLIDWORKS 还核对宿主保存的命令参数指纹。成对副本必须全部存在且引用与读回验证通过才一次登记。查询不属于当前工程记录的操作、宿主换会话、结果未知或文件缺失，均不会授予修改资格。此恢复可跨应用重启，不跨原生宿主会话。

`host.command` 的发送前校验拒绝返回 `error.outcome=not_applied`，用户可以随后另存工作副本。实际发送、结果读回或登记失败仍需保留原操作并查询，不能把这些失败当作没有执行。重复查询成功操作不会重复登记。

Agent 接入由 Electron 的 ACP 客户端负责；Python 服务不再接收模型凭据或执行模型工具循环。

开发构建：安装项目 `desktop` 可选依赖后运行 `python tools/build_app_service.py`，产物位于 `desktop/service/gongke-service/`。Windows 包必须在 Windows 构建，macOS 包必须在对应架构上构建；PyInstaller 不交叉编译。数据表与示例在构建时按工程核心的资源路径放入包内，运行不依赖源码目录、`PYTHONPATH` 或用户 Python。

## 工程状态

任务书通过 `project.set_task` 校验和持久化。排队的生成任务固定使用提交时的任务书和教学标记。

`project.current` 返回 `generations`（从新到旧）和 `delivery`（符合当前输入的最新一次生成）。每次生成记录输入摘要、产物清单、自动图检和失败状态。阶段完成要求清单中的产物成功且文件实际非空；旧文件或旧成功记录不会覆盖最新失败。条件改变后历史修订仍可打开，显示过期。未携带输入摘要的历史产物不会自动获得当前有效状态。此检查不鉴定用户在外部软件中对导出文件的内容修改。

历史工程中的 `.gongke-conversation.json` 保留原样；移除 Key 助手不删除历史对话或任务收据。新 ACP 会话见 [桌面说明](../desktop/README.md)。任务及独立回执仍保存在应用状态目录 SQLite；任务未结束时不切换工程。

## 统一工具与绑定 MCP

工具定义位于 `tools.py`，执行入口为 `Commands.call()`；服务生成任务、桌面 `host.command`、ACP Agent 与外部 MCP 均经过该入口。`tools.list` 返回唯一清单。原生候选/对象的身份与修订仍由现有宿主契约校验，工具层没有另建宿主协议。

服务随桌面启动一个带令牌的本机连接端点，发现文件为 `<state-dir>/service.json`。外部进程使用发行包中的 `gongke-service mcp --state-dir ... --project ... [--allow-writes]`。`--project` 必须是桌面当前工程；绑定后切换工程使旧连接失效，不跟随新工程。默认只读。每次 MCP 调用都登记为桌面可见任务并返回同一个 task_id。

`mcp.configure {"allow_writes":true}` 先预览用户级 WorkBuddy 工程专属配置；明确同意后增加 `confirm_user_config:true`，备份并写入。CLI 对应 `gongke-service workbuddy --state-dir ... --project ... --allow-writes --confirm-user-config`。撤销与实测差异见 [配置说明](../docs/workbuddy-conflicts.md)。配置默认使用运行中桌面服务的入口：发行包使用自包含程序，开发版保留 Python 虚拟环境入口并显式传源码 PYTHONPATH；均设置工程 cwd。开发与测试须安装 `.[app]` 或 `.[dev]`，可直接运行 `python -m gongke_app workbuddy ...`。真实 WorkBuddy、FreeCAD 与桌面收据的逐轮验收见 [操作清单](../docs/workbuddy-validation.md)。

收据在执行前持久保存为 prepared，完成后更新同一条为 finished；事件仍使用 task.updated 与 task.receipt。正在运行的任务取消后不自动回滚，也不重发结果未知的原生写入。纯桌面刷新查询不新增任务。

完整参数、CLI 迁移、协议取舍与官方资料见 [Agent 接口](../docs/agent-api.md) 和 [绑定决定](../docs/project-bound-mcp.md)。

任意零件的只读建模自查使用统一 `host.context`、`host.inspect`、`host.section`、`host.measure`、`host.check`；FreeCAD 与 SolidWorks 共用文档/对象/单位/结果契约，工具通过现有桌面服务和绑定工程的 MCP 提供。详见 [模型检查契约与复跑](../docs/model-inspection.md)。

FreeCAD 的 `freecad.connect` 与 `system.prepare_close` 由同一个宿主管理器执行；会话发现、单实例锁、进程归属、未保存文档和验收清理契约见 [FreeCAD 生命周期](../docs/freecad-lifecycle.md)。

# 工程绑定与统一执行的决定

- 工具清单归应用层，MCP 使用官方 Python SDK 2.3 API，发行包携带 SDK；core 与 FreeCAD 的 Python 不需要加载 SDK。
- 绑定冻结工程规范路径与本次打开的 epoch。切换后拒绝旧连接，即使重新打开同一路径也必须重连。运行中任务仍阻止切换，沿用桌面现有行为。
- 外部调用默认只读，`--allow-writes` 明确授权本次连接；不能通过工具参数升级权限。应用继续检查工作副本、路径与宿主文档契约。
- 桌面 `host.command` 仅按内层方法转发为注册表的 `host.read/write`，不再直调宿主；保留桌面当前传输形状以避免修改另一会话负责的 UI。生成和 ACP Agent 的 MCP 调用同样经过 `Commands.call`。
- MCP 每次调用对应一个持久任务。桌面只读刷新查询不制造任务，避免 `task.updated -> refresh` 形成事件循环；桌面写操作与计算仍登记任务。ACP 一轮中的每次 MCP 调用分别登记任务。
- 写前请求与完成结果使用同一条 SQLite 收据，事件携带 phase。宿主内部的事务身份/修订校验与原操作回读仍由当前 adapter 负责，不另建宿主抽象。
- 生成输入在提交时固定。用户可在生成期间编辑下一版条件，完成的旧输入修订自动显示过期。
- 原生只读审查 CLI 迁为绑定服务的 `revision.inspect`；旧 `--out` 改为工程内新目录，由 `revision.export` 写出检查记录；只读查询仍使用 `revision.inspect`，结果回到 stdout 与桌面收据。core 离线批处理生成器仍是 FreeCAD 子进程的领域入口，不暴露为 MCP 工具。
- MCP 结果外层增加 task_id、project、status，工具领域结果放在 result；协议客户端可以用同一个任务 ID 找到桌面收据。
- WorkBuddy 配置使用打包程序自身；不把宿主和应用的授权令牌写入项目配置。项目配置只保存启动路径、状态目录、工程路径与写授权开关。

实现与官方来源见 [Agent 接口](agent-api.md)。没有改 `desktop/src/main.tsx`；Agent 面板可调用 `tools.list`、`mcp.configure`，沿用已有 `task.updated` 订阅。

原生写请求报错后的回读单独保存在收据 `readback` 中；不能用同 ID 的历史成功回执把本次拒绝改写成成功。保存响应未知时也不自动登记副本资格，避免仅凭已有文件存在就声称本次保存完成。

## 运行记录（2026-11-03）

- 相关 Python 回归：132 passed，含真实官方 SDK stdio 客户端、工程切换、授权、原件/路径/过期修订拒绝、提交前持久收据、取消、原操作回读及 CLI 迁移。
- 桌面构建通过，6 项桌面测试通过。其中新增 MCP 测试使用实际 Electron Service 通信模块及其 Python 子进程，核对 running/complete 事件和 prepared/finished 收据。
- PyInstaller 自包含入口构建通过。清除 PYTHONPATH/PYTHONHOME、PATH 仅保留 `/usr/bin:/bin` 后，打包程序生成 WorkBuddy 配置，并完成读取、计算、生成；任务 ID `709b0c26e69e4b88a5d3ebe0579444d4` 与应用查询和事件一致。此轮使用 36 个实际注册工具，生成了非空 report.md。
- 扩展 Python 运行（排除 geometry/fem 目录）记录为 710 passed、1 failed。唯一失败为 `test_real_ccx_orphan_is_stopped_by_product_restart`：当前沙箱拒绝 `ps`，测试未能获得真实 ccx 进程身份；未修改该测试或求解器代码。
- 本机未连接 FreeCAD 桥接。安装的 FreeCAD 启动在 Qt 的 `neon` 检查处中止；Electron GUI 自动启动返回 `Process failed to launch`。真实原生只读查询和可视任务列表仍须在可运行 GUI 的环境完成，协议与桌面通信测试不替代这两项实机证据。

构建及运行日志位于本 worktree 的 `out/mcp-evidence/`；打包入口实测的配置、工具结果、任务收据、事件及二进制摘要位于 `out/mcp-packaged-final/`。可重跑 `tests/e2e/app_mcp_client.py --state-dir ... --project ... --executable <打包入口>`；宿主已连接时该脚本还会执行 `freecad.context`。

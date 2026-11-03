# 窗口内 Agent 接入

2026-11-03 的实现决策：

- Electron 用官方 `@agentclientprotocol/sdk` 稳定 ACP v1。React 通过专用 IPC 管理连接，不提供任意协议调用、文件写入和 terminal 能力。
- 启动配置为 `command + args[] + env`；Agent 与工程 MCP 都采用这一形式。工程目录作为 `session/new.cwd`，`${project}` 可出现在参数和环境变量中。MCP 固定以 `gongke` 名称注入。DeepSeek 要求 MCP 命令为绝对路径，因此启动前解析 PATH。
- ACP 登录方式由 `initialize.authMethods` 决定。支持 Agent 自己处理的 `authenticate`；不宣称支持 terminal 登录。DeepSeek 当前官方实现返回空认证列表，依赖 Harness 自己的账号配置。
- DeepSeek 通过官方 Cordis 插件接口隐藏全局工具、拒绝非 `mcp__gongke__` 调用，并要求每次工程调用授权。OpenCode 使用独立工程 agent 的 permission 配置：默认 deny，`gongke_*` ask。ACP 不是操作系统沙箱；自定义 Agent 需自行落实同样的工具限制。
- 取消先答复未决权限为 cancelled，再发送 `session/cancel`；直到 `session/prompt` 结束才允许下一条任务。断开不重放调用；工程切换前结束连接，忙碌时阻止切换。
- 默认 MCP 已接入绑定桌面工程的统一入口：开发版 `python -m gongke_app mcp --state-dir <userData>/state --project <工程>`，打包版使用随包 `gongke-service`，默认只读。已删除旧联调 MCP 替身；读取和计算使用 `project.current`、`design.calculate`，工具结果带 task_id、project、status 和 result。

依据：

- [官方 TypeScript SDK](https://github.com/agentclientprotocol/typescript-sdk)（本次安装 2.4.0；默认入口为稳定 v1）
- [ACP 初始化与消息流程](https://agentclientprotocol.com/protocol/v1/overview)
- [ACP 认证](https://agentclientprotocol.com/protocol/v1/authentication)
- [DeepSeek ACP 官方源码与契约](https://github.com/deepseek-ai/deepseek-harness/tree/master/packages/acp/acp)
- [DeepSeek tools 官方扩展接口](https://github.com/deepseek-ai/deepseek-harness/tree/master/packages/core/tools)
- [OpenCode ACP](https://opencode.ai/docs/acp/)
- [OpenCode 权限](https://opencode.ai/docs/permissions/)

## ACP 分支合并前运行记录

- `npm run build`：TypeScript 主进程/renderer 和 Vite 构建通过。构建前清空生成的 `dist-electron`，防止已删除的凭据模块残留进安装包。
- `npm test`：8 项通过，覆盖真实子进程 stdio、认证、MCP 注入、增量消息、拒绝/取消、重复权限答复、断连、新会话生命周期，以及既有工程通信/工作流。客户端拒绝 `fs/write_text_file` 和 `terminal/create`。
- `python3 -m pytest tests/test_app_service.py tests/test_project_workflow.py tests/test_host_paths.py -q`：23 passed、1 skipped；历史对话文件逐字节保留，旧 `agent.*` 方法不再可调用。
- DeepSeek Harness：本机官方源码 `687f282e86`，CLI `0.2.1-rc.2`；真实模型，`project_current` 和 `design_calculate` 各一次权限批准，返回 Y132S-4、5.5 kW。会话 `82b3f436-341d-488e-a202-08795bb5760a`，原始事件在 `out/acp-live/deepseek.json`。
- OpenCode `1.17.15`：独立 ACP 实现、同一只读 MCP、两次权限批准，返回相同电机和功率。会话 `ses_e5fb57804ffexvGfW7m7KsxGbq`，事件在 `out/acp-live/opencode.json`。原配置的第三方服务连接失败，免费模型也拒绝请求；成功运行使用隔离的 OpenCode 官方 DeepSeek 服务配置、沿用已有 DeepSeek 凭据，未改用户原配置，密钥未写入工作台设置或证据。
- 以上两条真实运行由 `tests/acp-live.cjs` 驱动并自动批准只读测试工具，**不是 Electron 窗口点击验收**。MCP 传输由测试替身提供，工程读取及计算使用真实 Application。
- Electron `40.10.6` 在进入应用前于 macOS `_RegisterApplication` 调用链发生 SIGABRT；Playwright 报 `Process failed to launch`。修复本地开发 Electron 的签名后仍复现，不能据此声称桌面端到端已通过。`tests/acp-flow.cjs` 已准备好窗口选择、登录、授权、结果和截图验证；真实配置通过 `GONGKE_TEST_AGENT_CONFIG` 传入。
- 已在 Chrome 中加载生产 renderer，回放上述实际 ACP 事件，目视核对面板、权限区、输入框和设置弹层。页面明确标为“界面回放（非桌面实测）”。
- 当前 worktree 是 detached HEAD。创建 `codex/acp-desktop` 时，共享 Git 元数据目录 `/Users/huaiyi/Documents/gongke-workbench/.git` 被执行环境拒绝写入，因此没有创建分支、提交、push 或合并。

尚需在可启动 Electron、可写 Git 元数据的环境完成：

1. 运行 `node tests/acp-flow.cjs`；再以两个真实 Agent 配置运行该脚本，实际在窗口中点击授权并核对结果。
2. 若 Agent 要求首次终端登录，先完成其账号配置；本次不实现终端登录嵌入。DeepSeek 未提供 ACP 账号登录，OpenCode 1.17.15 的登录方法说明要求 `opencode auth login`。
3. 真实 Agent 重跑使用新的绑定工程 MCP；`acp-live.cjs` 的配置必须指向运行中服务的状态目录与同一工程，保留默认只读。此前替身的运行记录不能算作新入口验收。
4. 将本 worktree 的改动提交到独立分支，提交尾部包含 `Co-Authored-By: Codex <noreply@openai.com>`。

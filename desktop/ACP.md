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

## Agent 首次引导（2026-11-03）

入口在 Agent 面板内部。`main.tsx` 未改；Electron 主入口只注册引导模块，preload 暴露固定动作。引导控制器、安装器、发现逻辑与界面分别位于 `electron/onboarding/`、`src/agent/AgentOnboarding.tsx`。未新增依赖。

### 使用与完成判断

- 启动时检测 dsh 和 WorkBuddy。dsh 优先采用官方 Desktop 自带 CLI，macOS 为 `DeepSeek Harness.app/Contents/Resources/runtime/cli/bin/dsh`，Windows 为 `<安装目录>\resources\runtime\cli\bin\dsh.cmd`；也查 PATH。Windows 额外读取已安装应用的卸载登记 `InstallLocation` / `DisplayIcon`，并检查用户级 Programs、LocalAppData、Program Files 下的候选目录。WorkBuddy 检测应用本体，不把 `.workbuddy` 数据目录当安装证明。官方没有承诺恒定安装目录，因此始终保留手动选择目录。
- 未安装时展示版本、实际大小、来源与摘要；勾选同意后才下载。运行原厂交互安装器，安装位置、许可及 Windows 权限由用户在原厂向导确认。安装器返回后重新检测；返回 0 本身不表示安装成功。
- dsh：注册/登录 → 充值 → 创建 Key → 打开 dsh 的 Settings → Models → DeepSeek → 保存 → 连接当前工程 → 发送首次对话。在 dsh 中已配置的用户可跳过账户引导。
- 构想引擎不提供 Key 输入框，不读取 dsh 的凭据文件、剪贴板或认证 URL，不复制 Key，不输出 Agent stderr。只有 dsh 自己读取凭据。原始上游异常只用于分类，界面收到固定的操作提示；401/缺 Key 去 dsh 配置，402 去充值，429/5xx 稍后重试，网络问题检查网络并重连。
- **dsh 完成条件**：本轮 `session/prompt` 返回 `end_turn` 且出现非空模型回复；回复/工具事件中的 `task_id` 必须对应本轮开始以后、当前工程、`kind=mcp`、`status=complete`、`project.current` 成功收据，返回工程路径也相符。握手、取消、拒绝、空回复、历史回执、其他工程回执均不完成引导。首次验证收起引导，给工程授权与回复留出位置。
- **WorkBuddy 完成条件**：生成项目级 `.workbuddy/mcp.json` 后，在 WorkBuddy 选中同一个工程目录，登录、信任 gongke，检查 MCP 绿色状态并完成一轮读取工程的真实对话。用户确认看到正确回复并填写该回复的 task_id，工作台核对本次配置之后的工程读取回执。标注为“工程读取回执已验证；WorkBuddy 回复由你确认”，不把生成配置、进程存在或 MCP 绿色灯等同于模型对话成功。
- WorkBuddy 没有在所查官方资料中提供可嵌入的 ACP 会话/回复回读契约，因此保留这一步人工确认；不读取其会话数据库，也不推断调用来源。回执证明工程操作，用户确认补足外部对话来源与回复内容。
- WorkBuddy 首次配置默认只读，合并 `gongke` 项、保留其他 MCP 服务。打包版仍使用随包 `gongke-service`；开发版的 `mcp.configure` 现在使用当前 Python 的绝对路径、`-m gongke_app` 与源码 PYTHONPATH，便于直接验证。请求 schema、工程绑定、权限和回执语义未改。
- `userData/agent-onboarding.json` 原子保存所选 Agent、步骤、安装路径、版本、绑定工程及成功任务编号/时间。错误消息、下载内容、对话与 Key 不写入这个文件。下载中断后重启会重新检测并保留可重试步骤；付款页面打开、Key 页面打开及用户点击“下一步”都不等于已验证账号可用。

### 固定下载清单与签名

运行时只读取随应用编译的 `electron/onboarding/releases.cts`，不读远端 latest 或自动换版。2026-11-03 两个 Windows x64 安装包均从下列官方版本 URL 完整下载，复算大小与 SHA-512；dsh 的摘要同时与官方更新 feed 一致。

| Agent | 版本 | bytes | SHA-512（Base64） |
| --- | --- | ---: | --- |
| dsh Desktop | 0.2.1-rc.5 | 289408544 | `gu2dH+aTr678c0P8DGAH/h4B1GaWfQIjpsPrLjl/ukLrQIh6DLVq/MhX4FZvJ8o1GCMocOhix6XbLa6KmtjXXg==` |
| WorkBuddy | 5.9.3 | 450174440 | `xFkEczgJjx5F5yyF9bUgHKbydwbeshaULAKWbPeJ6dNnD8g+/LWuxb3KQyktnIIaBmN2ud/AEXJUu8o7JLKY4A==` |

- [dsh 固定版本 EXE](https://download.deepseek.com/dsh-desk/bin/win-x64/deepseek-harness-0.2.1-rc.5-win-x64.exe)，发现来源为 [官方 nightly feed](https://download.deepseek.com/dsh-desk/feeds/win-x64/nightly.yml)。feed 会变化，不能拿未来 feed 内容代替已固定清单。
- [WorkBuddy 固定版本 EXE](https://acc-1258344699.cos.ap-guangzhou.myqcloud.com/workbuddy/saas/win32-x64-user/WorkBuddy-win32-x64-user-5.9.3.42398134-d4692421.exe)，来自[官方历史版本页](https://www.codebuddy.cn/docs/workbuddy/Download-History)。摘要为本次完整下载实算，不宣称腾讯另行发布了摘要。
- 从安装包 PE 的公开 Authenticode 证书表读取签名者标识：dsh 为 `Hangzhou DeepSeek Artificial Intelligence Co., Ltd.`，证书 SHA-1 thumbprint `84032578657219876E273E0D1BD303CFE1B82E6F`；WorkBuddy 为 `Tencent Technology (Shenzhen) Company Limited`，thumbprint `2BC94A2110F6F412AB416D53EB755664D320590C`。这里只提取了证书标识；**本机 macOS 未验证 Windows 信任链、时间戳与吊销状态**。
- 每次安装都先校验完整文件大小与 SHA-512，再运行系统 PowerShell `Get-AuthenticodeSignature -LiteralPath`，要求 `Status=Valid` 且签名者 thumbprint 等于清单。校验异常或 PowerShell 不可用就停止安装，不关闭系统验证；失败提示可重试或检查权限/网络。SHA-1 仅作为 Windows 证书标识，文件完整性用 SHA-512。
- 下载流有大小上限、15 分钟超时及取消；签名检查 30 秒超时；失败与成功均清理本次临时下载。安装由原厂向导处理剩余磁盘空间与目录选择。当前自动安装限 Windows x64；macOS 支持检测/连接现有 Agent，不另添未经校验的下载路径。
- 维护清单时重新从官方版本页/发布元数据取固定 URL，完整下载校验大小/摘要，提取签名者，并在 Windows 实跑签名与安装/对话验收后一起更新清单。证书轮换须明确更新清单，不能放宽为“任意有效签名”。

### Windows 命令与恢复

裸 `dsh` 解析包括 `.exe/.cmd/.bat`。`.cmd` 经系统 `cmd.exe /d /s /v:off /c` 启动，路径与参数逐个引用、外层再引用，使用 `windowsVerbatimArguments`，支持空格与中文目录；没有把完整命令拼入 `shell:true`。cmd 会在双引号内展开 `%`，因此明确拒绝含百分号、双引号或换行的命令/参数，并要求选择其他目录；不静默改变路径。

断开 Windows Agent 时用 `taskkill /T /F` 结束包装进程及其子进程。初始化 30 秒、建会话 60 秒超时；同步启动异常会结束 `starting`，允许重选位置。取消对话仍等待本轮结束，不重放操作。

### 本次验证与仍待实机步骤

- 构建：`npm run build`（desktop）通过。
- 自动测试：`GONGKE_PYTHON=<项目 venv 的 Python> npm test`：27 passed，1 skipped（Windows 专属）。新增 `tests/onboarding.test.cjs` 覆盖引导恢复、安装同意、取消与重入、网络/截断/摘要失败、签名状态及发布者不符、错误映射、路径引用、错误工程/旧回执、WorkBuddy 人工确认，以及真实 ACP 替身进程的本轮完成/取消。Windows 专属 cmd 执行测试在非 Windows 明确 skip。
- Python：`python -m pytest tests/test_workbuddy_onboarding.py tests/test_app_service.py tests/test_mcp_server.py -q`：27 passed。新增测试核对开发/打包两种配置形式、只读默认值与保留其他服务。
- macOS 现场检测：`/Applications/DeepSeek Harness.app/.../bin/dsh --version` 返回 **0.2.1-rc.5**；检测到 `/Applications/WorkBuddy.app`。
- 真实 dsh + 真实工程服务：使用新建、无凭据的 `DSH_HOME` 完成 ACP `initialize`、`session/new` 与工程 MCP 绑定，状态为 `ready`，模型选项为 `deepseek-official/deepseek-v4-flash`。此项只验证连接，不算首次模型对话完成。当前工作区记录：`out/onboarding-connection-final/connection.json`。
- 当前执行沙箱禁止 dsh 写默认用户目录，启动报 `EPERM`；Electron 在 `_RegisterApplication` 中 SIGABRT，Chromium 报 `MachPortRendezvousServer ... Permission denied (1100)`，浏览器预览工具也返回 host unavailable。因此**本轮没有真实窗口截图、视觉验收或已配置账户的真实模型回复**，不能用前述隔离连接或替身补作这些证据。

在普通 macOS 终端，已有 dsh 配好 Key 后，运行下列真实验收入口（产生 API 用量，只批准 `project.current`）：

```sh
cd desktop
npm run build
GONGKE_PYTHON=/absolute/project/.venv/bin/python node tests/onboarding-live.cjs
```

脚本创建独立教学工程，在真实 Electron 面板点击检测/连接/首次对话、批准只读请求，保存截图和 task_id/session/result 到 `out/onboarding-live`，重载检查持久化。无窗口的控制器/真实 ACP 验证入口为 `tests/onboarding-smoke.cjs`；`--connect-only` 只验证建会话，可用 `GONGKE_TEST_DSH_HOME` 指向空白测试目录，不能据此宣称账号已验证。

Windows 真机交接清单：

1. 干净 Windows 10/11 x64、无 Node/Python/dsh：打开打包版，确认检测结果；不勾选同意不得下载。显示的版本/大小/URL 与清单一致。
2. 下载两个固定包，核对 SHA-512 和上述 thumbprint；Windows `Get-AuthenticodeSignature` 必须返回 Valid。篡改/截断安装包、替换其他发布者、断网/取消不得启动安装器。
3. dsh 安装到含空格、中文的用户目录；验证自动注册表定位与手选目录。普通用户安装和 UAC 取消均有可重试结果；退出向导不误报已安装。
4. 注册/充值/Key 创建由学生自行完成；返回 dsh 保存 Key；关闭构想引擎再开，继续原步骤。检查本工作台的配置/日志没有 Key。
5. 从实际面板连接 Desktop 的 dsh.cmd，无需 Node/Python/PATH 修改；完成一轮真实 `project.current`、批准只读授权、核对工程名/路径/task_id；只握手/取消不能标记完成。错误 Key、无 Key、余额不足时分别验证更新 Key/充值入口及重试。
6. 更新 Key 后重连，切换工程后重新验证；关闭、断开、新会话确认任务管理器中旧 cmd/dsh/MCP 子进程结束。
7. WorkBuddy 既有安装和新安装各测一遍：检测、选择当前工程目录、生成配置、信任 gongke、绿色状态、真实读取回复。填旧 task_id/其他工程 task_id 不通过；正确回执和人工确认才完成。
8. `npm test` 在 Windows 执行专属 cmd 测试；真实面板在 1080×740 和 1440×960 检查滚动、错误提示、授权按钮和收起/恢复。原生安装器与联网/签名测试记录为 Windows 证据。

### 调研依据

- [WorkBuddy Windows 安装](https://www.codebuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Installation-Win-Guide)、[首次任务与登录](https://www.codebuddy.cn/docs/workbuddy/FirstTask)、[MCP 配置与状态](https://www.codebuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/MCP-Guide)：项目级配置位置、绿色状态及外部对话流程。
- [dsh 官方发布流程](https://github.com/deepseek-ai/deepseek-harness/blob/master/apps/desktop/publishing/README.md)、[固定版本 dsh.cmd](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.2.1-rc.5/apps/desktop/cli/dsh.cmd)；账号入口与凭据边界继承 `docs/research-dsh-onboarding.md`。
- [DeepSeek 官方错误码](https://api-docs.deepseek.com/zh-cn/quick_start/error_codes/)：401、402、429、500、503 的操作提示。
- [Node 官方 .bat/.cmd 启动说明](https://nodejs.org/api/child_process.html#spawning-bat-and-cmd-files-on-windows)、[Microsoft Authenticode 查询](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.security/get-authenticodesignature?view=powershell-5.1)。
- 同类实现参考 [electron-updater Windows 签名验证](https://github.com/electron-userland/electron-builder/blob/master/packages/electron-updater/src/windowsExecutableCodeSignatureVerifier.ts)：要求 Windows 正向验证和指定发布者，校验失败停止。这里固定完整包摘要与证书指纹，不引入自动更新框架。

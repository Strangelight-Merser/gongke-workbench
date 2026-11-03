# 构想引擎桌面应用

一个工程窗口管理原生模型、图纸、计算和工程助手。

## 使用

1. 新建工程时选择一个专用文件夹，直接填写任务书的拉力、带速、卷筒直径及寿命条件；也可明确载入教学条件。已有工程选择 `gongke-project.json` 所在目录。
2. 在左侧“原生模型”选择 FreeCAD、SOLIDWORKS 或 AutoCAD，读取已打开的工程。FreeCAD 需启用 GongKe 工作台；两款 Windows CAD 的插件安装说明分别位于 `adapters/solidworks` 和 `adapters/autocad`。
3. 先“另存工作修订”，再修改受支持的原生参数。已有文件不会被覆盖。修改后读回原生尺寸；FreeCAD 候选会在外部编辑后失效。
4. 在右侧 Agent 面板选择 DeepSeek Harness 或 OpenCode，点击“连接”。程序启动你本机已有的 Agent，完成 ACP 初始化并把工程 MCP 注入新会话。账号与模型配置由 Agent 自己管理，构想引擎不再保存 API Key。
5. 输入任务，查看流式文字、工具参数和结果；需要授权时在面板中选择“允许一次”或“拒绝一次”。取消等待当前 ACP 回合结束，不撤销已经完成的工程动作。新会话会关闭旧 Agent 进程再建立连接；忙碌时不能切换工程。

### Agent 启动配置

“设置”编辑 `agents.json`，内容只有 Agent 列表和一个工程 MCP 的 stdio 启动描述。`command` 是可执行文件，`args` 每个元素是一个参数，`env` 是环境变量映射，不经过 shell。需要不同模型时使用 Agent 自己的配置；不要在此写入账号密钥。macOS 从 Finder 启动时也会检索 Homebrew 常用目录；其他安装位置填写绝对路径。

```json
{
  "agents": [
    {
      "id": "my-agent",
      "name": "我的 ACP Agent",
      "command": "/absolute/path/to/agent",
      "args": ["acp"],
      "env": {}
    }
  ],
  "mcp": {
    "command": "/absolute/path/to/python",
    "args": ["-m", "gongke_core", "mcp", "--profile", "batch"],
    "env": {"PYTHONPATH": "/absolute/path/to/gongke-workbench"}
  }
}
```

**当前默认 MCP 是旧批处理入口，未绑定桌面当前工程，仅用于联调。** “核心入口”交付后，将 `mcp.command/args/env` 换成新入口约定即可，无需改 ACP 客户端。`${project}` 在参数和环境变量中会展开为当前工程绝对目录。打包版也需要配置真实存在的 MCP 可执行文件；本次没有把旧批处理入口冒充为发行版内置工程 MCP。

DeepSeek 默认使用 `dsh --profile acp --patch <应用管理的策略文件>`。策略插件通过 Harness 官方工具扩展接口限制为 `mcp__gongke__*`，工程调用逐次请求授权；本次实测源码 CLI 为 `0.2.1-rc.2`。OpenCode 默认使用 `opencode acp`，独立 `gongke` agent 将其他工具设为 deny，工程 MCP 设为 ask。自定义 Agent 的内建工具需要按其官方能力限制；ACP 本身不是操作系统沙箱。

登录按钮来自 Agent 的 `authMethods`。支持 Agent 处理的 ACP `authenticate`，不声明 terminal 登录能力。DeepSeek 当前返回空认证列表，需先在 Harness 自己的账号设置中完成登录/配置。已有授权直接复用。历史 `.gongke-conversation.json`、任务数据库及旧 `provider.json` 均不删除、不迁移；旧 Key 助手的代码和 IPC 已删除。当前新 ACP 对话由 Agent 自己持久化，面板只展示本次连接，尚未提供历史会话列表与恢复。

协议依据、取舍和本轮运行记录见 [ACP.md](ACP.md)。

任务书可载入明确标记的教学条件，输入工程单位，计算并生成新的 STEP、DXF/SVG、PDF、Word/Markdown 修订。修改条件后旧成果标为过期；图纸与说明书按修订分组，阶段状态核对当前清单和实际文件。它复用确定性计算模块；这些批处理图纸与原生 TechDraw/SOLIDWORKS 关联详图具有不同来源。

## 开发与打包

```sh
python -m pip install '.[desktop]' pytest
cd desktop
npm ci
npm run build
# 若 python3 并非安装上述依赖的解释器，设置 GONGKE_PYTHON 的绝对路径。
npm start
```

安装包内置独立 Python 服务，用户无需安装 Python。须在目标系统上构建：

```sh
python tools/build_app_service.py
cd desktop
npm ci
npm run package
```

产物位于 `desktop/release`。当前是开发构建：macOS 使用本地 ad hoc 签名并校验包完整性，没有 Apple Developer ID 或公证；Windows 未签名，安装过程仍待现场验证。CI 构建 Windows/macOS 目录包，AutoCAD 另有 .NET 8 与 .NET 10 两种原生插件包。商业 CAD 安装与授权不包含在本应用中。

## 验证

```sh
python -m pytest tests/test_app_service.py tests/test_project_workflow.py tests/test_host_paths.py
cd desktop
npm run build
npm test
node tests/desktop-flow.cjs
node tests/workflow-flow.cjs
# 确定性 ACP 窗口流程（含登录、权限）；真实配置使用 GONGKE_TEST_AGENT_CONFIG。
node tests/acp-flow.cjs
# 可选的商业 CAD 界面协议回归：替代宿主，不计作原生软件验收。
npx playwright install chromium
node tests/commercial-flow.cjs
```

桌面验收使用真实 Electron、真实 Python 服务和真实文件：新建工程、计算、生成 STEP/图纸、SVG 预览、Agent 未连接时禁用发送。结果与截图写入 `out/desktop-validation`。`tests/e2e/desktop_native_flow.py` 在单个真实 FreeCAD GUI 中核对网格、图纸、编辑、原生导出与重开。准备该隔离教学宿主后，可设置 `GONGKE_FREECAD_SESSION` 指向它的 `session.json`，运行 `node tests/freecad-flow.cjs`，从桌面按钮完成工作副本、轴径修改、校核、图纸和 DXF；不要指向个人工作中的 FreeCAD 会话。`GONGKE_TEST_EXECUTABLE` 可指定待验收安装包的可执行文件。

ACP 确定性协议测试使用独立 stdio Agent 替身；真实 Agent 联调和 Electron 窗口点击另行记录。SW/AutoCAD 的 SDK 编译、管道协议检查与真实宿主运行分开记录。当前 AutoCAD 视图按 WCS 平面显示支持的实体，不模拟未解析的块、字体排版和完整原生标注。

## 代码边界

- `electron/main.cts`：受限 IPC、原生文件选择、应用服务与 ACP Agent 生命周期。
- `electron/acp`：官方 SDK 客户端、启动配置与 DeepSeek 工程工具策略。
- `src/agent/AgentPanel.tsx`：独立 Agent 面板。
- `src`：工程树、原生模型/图纸、计算、任务与助手界面；不直接调用网络或任意进程。
- `gongke_app`：统一命令、工程清单、工作副本登记、SQLite 任务回执。
- `freecad/gongke`、`adapters`：各宿主自己的对象、线程与事务语义。

预览三角形只用于显示，不能作为持久化特征身份。工程计算通过不等于疲劳、装配、制造或专业审核通过。

独立 Linux FreeCAD 1.1.4 GUI 的合成轴验收已通过 8 项：真实网格与 SVG、原生对象选择、显示时保留源文档状态及子元素选择、40→38 mm 修改与读回重算、关联原生标注更新、原生 DXF 导出、人工修改后结果过期与 Undo、保存重开且原件不变；DXF 独立读回为 2 个 CIRCLE 和 1 个 DIMENSION，测量值约 38 mm，Unicode 转义解码后文字为“⌀38”，文件审计无错误。证据位于 `out/desktop-native-validation`，它证明该 Linux 原生流程，不代表 macOS FreeCAD 故障已修复，也不代表 Windows SOLIDWORKS/AutoCAD 宿主验收通过。

本机交付范围、验证结果与外部环境待验项见 [交付说明](../docs/delivery-2026-11-02.md)。

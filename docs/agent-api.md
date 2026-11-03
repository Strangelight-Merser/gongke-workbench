# 工程 Agent 接口

工程工具由 `gongke_app/tools.py` 定义，`Commands.call()` 执行。桌面、ACP Agent、外部 MCP 和绑定工程 CLI 使用同一份参数格式、写入分类、路径与工作副本保护。`gongke_core` 提供计算与领域逻辑，不再提供独立 MCP 服务器或原生工程 CLI 旁路。

## 连接桌面当前工程

先启动桌面并打开工程。外部 Agent 通过 stdio 启动发行包内的程序：

```json
{
  "mcpServers": {
    "gongke": {
      "command": "/absolute/path/to/gongke-service",
      "args": ["mcp", "--state-dir", "/absolute/application/state", "--project", "/absolute/project", "--allow-writes"]
    }
  }
}
```

省略 `--allow-writes` 时只读。写权限在应用执行端检查，隐藏工具列表不能替代授权检查。MCP 无权创建、打开或切换应用工程，也不能配置模型凭据、执行 shell、Python 或宏。

应用服务只监听随机本机回环端口，`<state-dir>/service.json` 保存本实例地址与令牌（POSIX 文件模式 0600；Windows 使用应用状态目录的用户访问权限）。客户端禁用代理和重定向。服务退出删除发现文件；重启不会恢复旧绑定。

启动时 `--project` 必须等于桌面当前工程的规范路径。绑定同时记录本次打开的身份，切换工程或重新打开同一路径都会使旧连接失效。调用接收与切换工程在同一把锁内检查，已登记的任务运行期间不能切换工程。MCP 进程不能因为绑定失效自动跟随新工程。

## WorkBuddy 项目配置

发行包入口可生成 `<项目>/.workbuddy/mcp.json`：

```sh
/path/to/gongke-service workbuddy --state-dir /absolute/application/state \
  --project /absolute/project --allow-writes
```

只更新 `mcpServers.gongke`，保留其他服务器。命令使用打包程序自身的绝对路径，不使用用户 Python。开发时可用 `python -m gongke_app workbuddy ... --executable /path/to/packaged/gongke-service` 指定已构建入口。桌面服务也提供 `mcp.configure {allow_writes: true|false}`，供 Agent 面板接入；本次未修改面板 UI。

## 工具与结果

`tools/list` 来自运行中应用的清单，不在 stdio 代理里复制定义。`tools.list` 是桌面/CLI 的同一清单查询。ACP Agent 通过同一个工程 MCP 调用这些工具，不另设函数名适配。

| 工具 | 用途 |
| --- | --- |
| `project.current/files/read_file` | 绑定工程、实际文件、受限文本预览 |
| `project.set_task` | 保存条件与教学标记；输入变化后旧结果过期 |
| `design.schema/example/validate` | 条件格式、明确标记的教学示例、输入校验 |
| `design.calculate/explore/report` | 当前条件计算、参数对比、说明书；不改变 CAD |
| `design.generate` | 新建工程内 `revisions/<name>`，返回真实产物与失败状态 |
| `standards.lookup` / `drawing.check` | 标准数据与工程内 DXF 检查 |
| `revision.inspect` / `revision.export` | 既有零件与原生图纸的严格只读核对；`capture` 明确标为离线证据 |
| `freecad.*` | 现有 FreeCAD 会话、对象、候选、事务、保存、出图与任务接口 |
| `hosts.list` / `host.read` / `host.write` | 宿主能力发现及声明的读写操作 |

完整参数以 `tools/list` 为准。批处理任务书单位为 mm、N、m/s、r/min，摘要使用 MPa、kW；FreeCAD 轴快照使用 SI，长度 m、应力 Pa。host 参数遵循能力发现给出的当前宿主契约，不能猜单位或对象身份。

每次 MCP 工具调用返回：

```json
{"task_id":"...","project":"/absolute/project","status":"complete","result":{}}
```

同一 `task_id` 出现在桌面 `task.list/get` 和 `task.updated` / `task.receipt` 事件中。写前收据为 `phase=prepared,result=null`；完成后同一条收据更新为 `phase=finished`，保留准备与完成时间。任务中断时保留待核对收据。`complete` 只表示执行完成，仍需阅读 `calculation_ok`、`failed`、`exports_complete` 和来源缺口；部分导出状态为 `partial`。

MCP 客户端在发请求前确定任务 ID。若提交响应丢失，只查询该 ID，不重发工具调用。MCP 取消只停止后续步骤，已提交的原生操作/导出安全结束后保存实际结果，不声称自动撤销。

## 原生工程保护

先读取真实文档身份与修订；原件必须先另存工作副本。文件位于工程目录并不等于获得修改授权，必须有成功保存/导入回执并验证文件后登记为工作副本。原件、工程外路径、符号链接逃逸和过期文档修订均由公共执行路径及宿主事务检查拒绝。

FreeCAD 保存允许新文件及当前文档自身已登记的工作副本。其他文件不能覆盖。候选应用的修订与对象内容由现有 FreeCAD 事务执行端核对，`expected_revision` 工具也在提交前核对当前上下文。FreeCAD 结果未知时查询原 `operation_id`；保存响应丢失时回读原会话的当前路径与实际文件。Windows 宿主保留原操作查询和副本登记恢复机制。

## CLI 迁移

绑定工程 CLI 与 MCP 使用相同服务，不建立另一套执行器：

```sh
/path/to/gongke-service call --state-dir /absolute/application/state --project /absolute/project tools.list
/path/to/gongke-service call --state-dir /absolute/application/state --project /absolute/project design.calculate
/path/to/gongke-service call --state-dir /absolute/application/state --project /absolute/project \
  --allow-writes design.generate --params '{"name":"revision-1","drawings":false,"report_docx":false}'
/path/to/gongke-service call --state-dir /absolute/application/state --project /absolute/project \
  revision.inspect --params @inspect-params.json
```

需保留磁盘检查记录时，使用迁移后的专用 CLI（原生模型仍严格只读，报告写入须授权）：

```sh
/path/to/gongke-service inspect-revision --state-dir /absolute/application/state --project /absolute/project \
  --allow-writes --case /absolute/case.json --capture /absolute/capture.json --out revisions/review-01
```

`--out` 只接受工程内尚不存在的相对目录，经 `revision.export` 写出 ASCII 文件名 `revision.json`。保留旧 CLI 的检查退出码：0 为声明范围内通过，1 为失败或未确认，2 为输入/连接/写入错误。结果同时进入桌面收据。

`inspect-params.json` 是 `{"case": <完整修订任务>, "capture": <可选离线采集>, "previous": <可选上次结果>}`。结果由 stdout 返回，同时保存在桌面任务收据；`--out` 不再接受绝对路径或工程外目录。`python -m gongke_core mcp`、旧工具别名和 `gongke_core inspect-revision` 已删除。core 的离线计算/导出 CLI 仍供既有 FreeCAD 批处理子进程使用，不是应用工程或 Agent 的入口。

## 实现依据

- [官方 MCP Python SDK low-level Server](https://py.sdk.modelcontextprotocol.io/advanced/low-level-server/)：按既有注册表提供 schema 与处理函数；参数校验由应用执行层负责。
- [官方 SDK stdio 示例](https://github.com/modelcontextprotocol/python-sdk/blob/main/examples/snippets/servers/lowlevel/direct_call_tool_result.py)：使用 `Server`、`stdio_server`、`CallToolResult`，不手写 MCP JSON-RPC。
- [WorkBuddy MCP 配置](https://www.codebuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/MCP-Guide)：项目级 `.workbuddy/mcp.json`，`mcpServers` 下以 `command/args` 启动服务。

- [MCP 官方 filesystem 参考服务](https://github.com/modelcontextprotocol/servers/blob/main/src/filesystem/README.md)：参考其启动目录边界与符号链接目标校验。本应用以桌面工程和服务端绑定为权限来源，不接受客户端改变工程边界。

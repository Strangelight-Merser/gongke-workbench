第七轮诊断、后台运行和矢量 PDF 实测见 [第七轮记录](agent-modeling-round7.md)。

# 真实 Agent 读图建模验收

当前状态：第五轮 P7 dimensions 首次自主完成原生建模、保存与独立几何审核（1/1）；vision 已实际收到图并完成原生模型，但底板和槽贯通关系理解错误（图纸符合性 0/1）。原 `failed_or_review_required` 还混入重开包围盒误判，已修复实现并拆分状态，尚待第六轮真实 GUI 复验。样本各一次，不宣称稳定。

## Claude 当前运行

在沙箱外终端执行，使用本 worktree，不要换成主线目录：

```sh
cd /Users/huaiyi/.codex/worktrees/7115/gongke-workbench
(
  set +e
  set -o pipefail
  /private/tmp/gongke-modeling-venv/bin/python scripts/agent_modeling_trial.py --cases p7 --delivery vision --repeats 2 2>&1 | tee /tmp/trial6-p7-vision.log
  /private/tmp/gongke-modeling-venv/bin/python scripts/agent_modeling_trial.py --cases p6 --delivery dimensions --repeats 2 2>&1 | tee /tmp/trial6-p6-dimensions.log
  /private/tmp/gongke-modeling-venv/bin/python scripts/agent_modeling_trial.py --cases p6 --delivery vision --repeats 2 2>&1 | tee /tmp/trial6-p6-vision.log
)
```

Python 需要项目 `[dev]` 依赖和 Pillow，本机上述环境已补齐。脚本在需要时安装本 checkout 的 npm 锁定依赖和 Electron，再构建桌面。默认明确使用 `/Applications/DeepSeek Harness.app/Contents/Resources/runtime/cli/bin/dsh`；本次现场核对为 **0.2.1-rc.5**，PATH 中 `/opt/homebrew/bin/dsh` 则为 **0.2.0-rc.2**。不更新这两个安装，不复制或改写 Key。

脚本依次启动独立 FreeCAD 验收宿主、真实 Electron（由它启动应用服务）、窗口内 dsh ACP 会话。通过产品的“打开图纸”导入局部图，点击发送，在窗口逐次批准本轮允许的工程 MCP 工具。系统文件选择器由 Playwright 返回本轮图片路径，其他 UI 和工程入口实际执行。它不会调用预写建模配方，也不会把参考 STEP、建模配方或独立检查条件放进 Agent 工程。dimensions 模式只导入人工读图尺寸与视图关系解释，不计为自动读图。

每个零件默认最多 1200 秒；超时取消，不重发写操作。原 FreeCAD 验收进程保留现场，PID 在 `host/process.json`。脚本关闭自己启动的 Electron/Agent；另一个短时 FreeCAD 进程重开已保存 FCStd、只读检查并截图后退出。结束后可人工关闭这些验收窗口，不关闭学生已有 FreeCAD。

输出目录为 `out/agent-modeling-<时间>/`，脚本会打印完整路径。重复试验的父目录保存汇总 `summary.json`，各次完整记录在 `runs/<零件>-<次数>/`，子目录仍有自己的 summary/runner 和 `<零件>-<次数>/result.json`。将三个父目录路径交回即可；失败时也不要删目录或改原记录。学生原图及局部图只在本地，不能提交仓库。无需把整目录打包外传，其中含图纸和本地会话内容。

## 后续对照命令

先分析当前轮次输出，再决定是否修改。每轮均生成新目录，不覆盖旧证据。对比 MCP 读图途径：

```sh
/private/tmp/gongke-modeling-venv/bin/python scripts/agent_modeling_trial.py --cases p7 --delivery mcp
```

此模式仍先在工作台打开图纸，发送前切到建模页；只给模型工程图片路径，要求它调用 `project.read_image`，不同时附带 ACP 图片。附件与 MCP 图片都不能绕过模型本身的视觉能力；如果 dsh 拒收图片或把图片替换为不可用提示，应记录为读图失败。

未有参考体的 P6 可单独运行：

```sh
/private/tmp/gongke-modeling-venv/bin/python scripts/agent_modeling_trial.py --cases p6 --delivery vision
```

P6 原图上缘被截、部分标注模糊，没有独立参考体。候选尺寸与空间关系见 `tests/fixtures/agent_modeling/p6-reading.json`，其中只有右平台长 15 mm 计为已复核读数，其余均标明候选或假设。脚本收集原生树、自查、保存和重开证据；这些通过后结论为 `review_required`，不能把模型自行选取的期望值与自身比较当作图纸符合性证明。`construction_passed` 只表示建模/自查/保存/重开链路通过。

修正后确认重复性，用新工程、新 ACP 会话重跑：

```sh
/private/tmp/gongke-modeling-venv/bin/python scripts/agent_modeling_trial.py --cases p7 --delivery vision --repeats 2
```

两次是操作性复测口径，不是统计上的稳定性保证。每次新宿主、新工程、新 ACP 会话，前次模型不会进入后次 host.context；全部指定试次都会执行并分别记录，某次失败不提前取消后次。`automatic_pass_rate` 只表示自动验收通过率，待复核不算自动通过；`construction_pass_rate` 单列构建链路通过率。P6 通过人工复核后，应另记人工结论及依据，不更改原始自动报告。

## 记录与判定

| 文件 | 证据 |
| --- | --- |
| `manifest.json` | checkout、源码哈希、CLI 版本、原图/裁剪哈希、输入方式、重复次数 |
| `host/bootstrap.json`、`host/freecad.log` | FreeCAD 版本、实际加载模块路径和哈希、宿主启动日志 |
| `<零件>-<次数>/initialization.json` | ACP 能力协商及初始会话；模型不声明图片能力时，附件模式明确失败 |
| `prompt.txt`、`conversation.json/txt` | 实际任务、完整 ACP 快照及可读对话 |
| `user/agent-events.jsonl` | 带时间戳、session id 的逐事件记录，进程中断前已收到的内容也保留；图片记录路径、MIME、哈希 |
| `dsh-session.jsonl`（如能定位） | 仅按本次 session id 读取 dsh 最新持久化代次，脱敏保留；不扫描其他会话正文 |
| `agent-tasks.json`、`tool-calls.jsonl` | 同一应用服务的全部任务和调用参数/回执/错误，绕过 `task.list` 的最近100条展示限制 |
| `auditor-calls.jsonl`、`audit.json` | 模型停止后的独立只读检查，和模型自查分开记录 |
| `project/*.FCStd`、`reopened.json`、`model-reopened.png` | 模型自己保存的文件、另一进程重开后的实体/树/尺寸一致性和真实截图 |
| `drawing.png`、`final.png`、`result.json`、`summary.json` | 桌面实际画面、耗时、停止原因、授权、用量及试次结论 |

P7/P8 自动通过需同时满足：有效单 Body/单实体、真实草图和 PartDesign 特征树、当前修订的成功自查与保存回执、FCStd ZIP 完整、独立尺寸/截面/体积/包围盒检查、重开后的树与几何一致。几何比较沿用已有参考体及其显式假设，约定坐标方向，不做自动配准。不同的合理尺寸假设或坐标选择产生差异时，需要分类判读，不能直接说模型错误。有限几何检查通过也不能代替图纸人工终审。

耗时分别记录整轮与 prompt。ACP usage 原样保留；dsh 会话中的顶层 usage 事件单独摘出，不重复累加内嵌 stream，也不将上下文占用误称为计费 token。未报告金额时费用未知，不套当前价格反推。

## 首轮改动与取舍（历史）

| 改动前的可确认问题 | 当前改动 | 待真实运行确认 |
| --- | --- | --- |
| 图纸页面的“当前参考”只拼接路径，ACP 只发 text | 当前工程 PNG/JPEG/WebP 通过主进程读取，按 ACP image block 发送；能力不支持时明确拒绝，历史显示附件路径 | 已安装 dsh 的实际模型是否接收并理解标注 |
| MCP 无图片读工具 | `project.read_image` 经相同工程绑定和调用收据，返回标准 image block，base64 不进入模型文本结果 | dsh MCP 图片投影是否完整，是否优于附件 |
| 建模 GUIDE 仅在 resource/prompt；工程策略只开放 `mcp__gongke__` 工具 | 同一 GUIDE 同时作为 MCP server instructions，不新增通用资源执行或 shell 权限 | 模型是否遵守单位、法向、修订与检查顺序 |
| ACP 只显示内存中的事件，prompt 结果用量被丢弃 | 持久化增量事件并保留 prompt 响应、图片哈希、能力协商；结构化脱敏保留数值类型 | 中断路径、模型用量记录完整性 |
| 自定义 userData 在单实例锁之后才设置 | 在锁之前设置，让隔离验收不抢占现有桌面实例 | 真实 Electron 隔离启动 |

公共协议变化：新增只读 `project.read_image(path)`；前端 `agent.prompt(text, imagePaths?)` 增加工程内图片附件。没有改变原生写入、对象身份、工作副本或 operation_id 语义。工程工具仍是一批草图/一个特征；没有尚未经真实失败支持的粒度重构。

首轮交付验证：桌面构建通过；桌面测试 44 通过、1 跳过；相关 Python 测试 54 通过、1 跳过；P7/P6 裁图与 manifest 生成已执行。协议测试使用专门的确定性图片替身，不能算真实模型建模结果。GUI/FreeCAD 运行留给本节沙箱外命令。

## 依据

- [ACP Content](https://agentclientprotocol.com/protocol/v1/content)：支持标准图片内容块，不能用文件路径代替图片；按初始化能力协商发送。
- [ACP Prompt Turn](https://agentclientprotocol.com/protocol/v1/prompt-turn)：保留 session updates、工具活动和 prompt 结束响应。
- [MCP Tools](https://modelcontextprotocol.io/specification/2025-06-18/server/tools)：工具结果的 image content 与 structured content 分离。
- [DeepSeek Harness 官方源码](https://github.com/deepseek-ai/deepseek-harness)：本机公开源码 `packages/acp/acp/src/content.ts` 显式检查当前模型 image modality；`packages/mcp/mcp-client/src/tools.ts` 可能将不可接收的图片投影为不可用提示；`packages/acp/acp/src/updates.ts` 的 usage_update 是上下文占用。源码为调查依据，安装版本行为以本轮实际记录为准。
- [neka-nat/freecad-mcp](https://github.com/neka-nat/freecad-mcp)：同类项目也采用 FreeCAD 内插件与外部 MCP 分离，并有从二维图建模示例；其通用 Python 执行接口不纳入本项目，本次复用已有受限原生工具。

每轮收到输出后，在此追加实际结果、典型失败、修改与下一轮命令；未跑的轮次不填成功率。

## 第 1 轮：连接等待提前结束（2026-11-03）

原始证据保持原样：`out/agent-modeling-20261103-044907/`，完整控制台 `/tmp/trial1.log`。P7 在 4.837 秒结束，`initialization.json`/`conversation.json` 为 `starting`、空 events；工程任务数为 0，宿主能力正常、documents 为空。统计为 **1 次端到端试验失败，0 次建模 prompt**，不据此评价模型能力。

根因：验收脚本向 `page.waitForFunction` 传了 async 谓词。当前安装的 Playwright 1.64.1 实现直接执行 `const success = predicate(); if (success) fulfill(success)`，把 Promise 当作真值；等待 Promise 解析为 false 后也直接返回，未继续轮询。脚本立即取得 `starting` 并在 finally 调用 disconnect。`agent-errors.jsonl` 的 `initialize / ACP connection closed` 是清理引发的连接关闭，原 `final.png` 也拍在清理之后，不能当作启动参数或 Key 错误的证据。

第二轮改动：

- 在 Node 侧逐次 `await` 状态 IPC，必须拿到 `ready` 与 session id，再核对工程/Agent；120 秒为上限，不是固定睡眠。真实错误即时退出，最后状态和阶段写入 `lifecycle.jsonl`。
- dsh 的权限请求可只有 `toolCallId`（官方源码 `packages/acp/acp/src/index.ts`）；客户端按同 ID 汇总先前 tool_call/update，补齐显示名称与参数。脚本按具体 permission id 点击，记录实际选项，避免误拒合法调用或误点其他请求。
- 发送后核对真实 user event 中的图片路径与哈希；MCP 对照模式必须没有 ACP 图片，且独立审计确认读取了对应哈希的图。完成响应还需有同会话的 `end_turn` 和学生可读回复。
- final.png 在取消/断开前拍摄；取消后短暂等候结束响应再导出对话。控制台实时输出阶段；`prompts_sent` 与总试次数分开记录。
- 中断回执 result=null 不再使审计崩溃；成功自查必须匹配最终 Body 及修订。部分审计出错仍保存已有证据和异常；保存、独立参考检查及重开规则保留。

下一轮仍仅跑 P7，保留新输出目录：

```sh
cd /Users/huaiyi/.codex/worktrees/7115/gongke-workbench
set -o pipefail
/private/tmp/gongke-modeling-venv/bin/python scripts/agent_modeling_trial.py --cases p7 2>&1 | tee /tmp/trial2.log
```

原 `acp-flow.cjs` 中也有相同异步等待写法，本轮未改动已有验收程序；它此前跑通不能证明那个等待条件可靠。新增回归在真实 ACP stdio 协议替身上覆盖延迟初始化/建会话、会话错误、仅 ID 的权限和交错工具事件；它不生成模型，不计入真实试验成功率。

第二轮交付验证：桌面构建通过；完整桌面测试 47 通过、1 跳过；相关 Python 测试 31 通过。日志在 `out/agent-modeling-dev/round2-build.log`、`round2-desktop.log`、`round2-python.log`；最后的权限字段整理另经 TypeScript 编译及 5 项连接/图片专项回归通过。

## 第 2 轮：连接通过，当前路由未声明图片（2026-11-03）

原始目录 `out/agent-modeling-20261103-045855/`、控制台 `/tmp/trial2.log`。ready/session id 正常，选中 `deepseek-official / deepseek-v4-flash`；初始化 `image=false`，在 image-capability 阶段停止，0 次建模 prompt、0 个模型。两轮均未进入真实推理，模型建模成功率尚无可用样本（0 次建模任务），不能用 0/2 描述模型能力。第 1 轮连接等待修复已被第 2 轮真实运行验证。

第 3 轮前修改：

- 新增 DXF/PDF 确定性提取工具、MCP 引导及窗口参考文件传输，详见 [图纸输入契约与模型调研](drawing-input.md)。图片能力不足时有切换模型/矢量/人工尺寸替代，不新增 Key 管理。
- `--delivery dimensions --cases p7` 从已有本地 `dimensions.json` 的 **P7 读图记录**生成 `inputs/p7-dimensions.json`，包含源图和裁图哈希、标注区域、明确值、总高语义、俯视关系及 R10 假设。关系描述经原裁图复核，不含草图/特征配方、工具调用顺序或参考实体。原图、提取记录、测试参考体保持原样，输出 JSON 和裁图仅在 out/。
- 真实窗口先打开原裁图，再通过同一个“打开图纸”入口导入并展示 JSON。发送的实际 ACP user text 必须含文件路径和 SHA-256，且不能带图片；要求模型再调用 `project.read_file` 核对，审计核对对应回执哈希。`input_scope=human_transcribed_dimensions` 单独记录，不计为自动读图成功。
- 修正审计的 `input_read`：先前 attachment 模式即使未发 prompt 也会写 true，现在核对 conversation 中真正发送的图片哈希；结构化模式同时检查实际文本和 MCP 读取回执。既有第 2 轮证据不改写。
- 保留授权、原生自查、最终修订保存、独立参考几何检查和第二 FreeCAD 进程重开；不因换输入方式降低建模验收标准。

下一轮沙箱外运行（沿用已有环境，依赖已在此环境安装；无需改 dsh 配置）：

```sh
cd /Users/huaiyi/.codex/worktrees/7115/gongke-workbench
set -o pipefail
/private/tmp/gongke-modeling-venv/bin/python scripts/agent_modeling_trial.py --cases p7 --delivery dimensions 2>&1 | tee /tmp/trial3.log
```

仍收集 summary、runner、conversation、工具收据、FCStd、自查/独立检查、截图、用量与耗时。该轮先回答“真实模型能否根据尺寸自行建模”；自动读照片、真实学生 DXF/PDF 的完整尺寸理解，以及新零件 P6 仍需后续各自验收。

第三轮交付前验证：桌面构建通过，桌面测试 50 通过、1 跳过；Python 专项 34 通过，应用/MCP/工程与检查集成 45 通过、1 跳过，随后新增的输入证据回归连同 2 项原审计回归共 3 通过（合计不同用例 80 通过、1 跳过）。日志见 `out/agent-modeling-dev/round3-{build,desktop,python,integration,audit-final}.log`。`--prepare-only` 已生成 `out/agent-modeling-20261103-050837/` 的 P7 尺寸资料和 manifest；未启动 GUI、未调用真实模型。共享 `.git` 的 index.lock 写入被沙箱拒绝，本轮未产生提交，代码留在当前 worktree。

## 第 3 轮：授权脚本误拦正常工具（2026-11-03）

原始目录 `out/agent-modeling-20261103-051403/`、控制台 `/tmp/trial3.log`。模型第一项调用 `mcp__gongke__project_current_50a8c7a5bd98`；原正则只接受没有哈希的固定名称，脚本拒绝并取消。实际收到 1 次建模 prompt，执行端工程任务为 0，模型能力尚未得到有效检验。前两轮亦未执行建模，不能将三次基础设施/脚本中断算作模型建模失败率。

第四轮修改：

- 仅限定工程 MCP 来源，全部只读工程工具与执行端已授权的写工具均放行。不匹配固定工具清单，不要求预设调用顺序。外部参考答案不进入工程，越界读取和写入继续由执行端阻止；无任意代码或实体导入接口。
- 去掉“已经收到结构化文本后还必须重复调用 project.read_file”的要求。输入证据检查实际发送内容和来源哈希，不以重复某个工具调用作为验收条件。
- 新增标准 session/set_config_option 及窗口会话模型选择器，保留返回的 configOptions。`--delivery vision` 在连接后明确选择 deepseek-official / deepseek-flash，不把 image=false 当作工作台拒绝条件。
- vision 模式只导入原裁图，不导入尺寸 JSON。先用一轮读出 9 个明确标注，与 manifest 中的本地人工复核值比较（R10 假设不参与）；期望值不发给 Agent。再于同一会话继续建模，保留模型自行使用工具的路径。误读/回复格式不符记录为未验证通过，但不取消后续建模，也不向模型补答案。若协议层直接拒收，则保留错误，不伪造后续读图成功。
- 两轮对话分别切分事件、检查 end_turn、记录耗时；共享原设定的任务超时预算。保存 model-selection-request/result、vision-read-prompt/result、vision-check、modeling-prompt/result、完整 conversation、工具收据及 CAD 产物。`modeling_prompt_sent` 区分只读图和真正开始建模，`modeling_passed` 与 vision.verified 分开报告。
- dsh 会话目录实际为 `<project>/<session-id>/session.v4.jsonl.zstd`，去掉误加的 session- 前缀。断开前对支持的 Agent 请求 session/close，等其持久化刷新后再终止子进程；关闭请求失败留诊断，仍完成进程清理。close.json 与已有会话 trace 保留关闭记录；文件存在但无用量时 usage_available=false，不编造 token/费用。

沙箱外依次运行两个独立试验，第一项失败也继续第二项；每项输出新目录：

```sh
cd /Users/huaiyi/.codex/worktrees/7115/gongke-workbench
(
  set +e
  set -o pipefail
  for input_mode in dimensions vision; do
    /private/tmp/gongke-modeling-venv/bin/python scripts/agent_modeling_trial.py --cases p7 --delivery "$input_mode" 2>&1 | tee "/tmp/trial4-$input_mode.log"
  done
)
```

真实 dsh 是否仍在 ACP 层拒绝图片，以这一轮的 session/prompt 实际返回为证据。当前只知道官方源码保留了初始化 imageEnabled 检查；没有把源码推断写成已运行结果。若拒收，conversation 中 request 事件证明已向 SDK 提交图片块及其哈希，errorDetails/agent-errors.jsonl 保留返回原因；初始化与模型切换响应可判断问题发生在何层。

交付验证：桌面构建通过；完整桌面测试 51 通过、1 跳过（含初始化 image=false、session/set_config_option、实际图片传输/拒收及哈希工具名回归）；Python 输入/审计专项 7 通过。vision 的 prepare-only 已生成 `out/agent-modeling-20261103-052027/`。日志在 `out/agent-modeling-dev/round4-{build,desktop,python}.log`。上述测试使用协议替身，不计真实视觉或建模成功。

## 第 4 轮：原生约束崩溃与 ACP 图片准入（2026-11-03）

证据目录保持原样：dimensions=`out/agent-modeling-20261103-052623/`，vision=`out/agent-modeling-20261103-053324/`。

- dimensions 的读数、总高语义和 R10 假设均已在真实回复中体现。第一张草图因冗余约束返回可恢复错误，第二张草图成功且欠约束；删除后第三张草图的第一项为 `fixed(geometry=0, point=center)`。旧实现拼出 `Sketcher.Constraint("Block", 0, 3)`。`host/freecad.log` 记录 `uncaught exception of type Py::TypeError` 并终止进程；不能把它称为已证实的求解器死循环。当前只剩新建时保存的空 Body，不计建模通过。
- vision 已确认切到 `deepseek-official / deepseek-flash`。`conversation.json.errorDetails` 和 `user/agent-errors.jsonl` 的原始错误是 `session/prompt`、`code=-32602`、`Invalid params: inline image prompts were not advertised by this connection`。总耗时 7.039 秒，prompt 阶段约 0.108 秒。错误发生在 dsh ACP 的图片准入，未进入模型请求；不能将其计为视觉识别失败或模型不支持图片。原 result.json 遗漏详情是试验收集器缺陷。

第五轮修改及取舍：

1. FreeCAD 在调用原生约束构造器前检查几何类型、点位置和重载组合，非法组合返回事务错误。`fixed whole` 使用单几何 Block；`fixed point` 只锁该点：原点用 Coincident，其他位置用 DistanceX/Y，零坐标用 PointOnObject 到草图轴。不会固定圆弧半径；非原点命名展开为 `_X`、`_Y`，回执返回所有原生约束索引。数值统一 float，整批创建约束，避免逐个求解改变后续固定点的基准。这是 FreeCAD 的工具语义修正，SOLIDWORKS 实现不变。
2. 新增原始失败参数夹具 `tests/fixtures/native_modeling/fixed-center.json` 和真实宿主回归。每轮在**独立进程/工程**测试 8 种情况：原始组合并拉伸保存、整圆 Block、非零坐标固定、轴上固定、非法 Block/点/半径组合、矛盾半径。每次用原 ID 查回执，再 context/save，证明错误返回后仍可读写；回归进程随后退出，不让真实 Agent 看到回归模型。结果在 `constraint-preflight/{calls,results,summary}.json*`。失败不开始 Agent，保留日志；没有将这些脚本生成物算作真实模型成果。
3. vision 使用官方 `--patch` 的 `id: acp / config.provider / config.model` 在 initialize **之前**选择 deepseek-official/deepseek-flash，随后仍实际执行 session/set_config_option、发送图片和比较 9 个读数。只改本轮 user 目录的 patch，不改全局 dsh 配置、模型目录或凭据，也不替换图片内容。dimensions 维持原模型设置，便于观察宿主修复效果。
4. result.json 新增 `acp_error`（code/message/details/operation/stderr）及 `dsh_stderr` 路径/尾部；独立保存 `acp-error.json` 与完整逐行脱敏的 `dsh-stderr.log`。先保存故障再取消/关闭，不以 session/close 故障覆盖根因。主进程持久记录 stderr，协议替身测试验证 -32602/data 和脱敏。
5. 桥接连接失败保留底层异常类型和消息，明确写入结果未知、不自动重发。FreeCAD 子进程仅接收所需环境，避免 macOS 启动器把 Agent 凭据环境输出到宿主日志。

超时边界：HTTP 主线程等待仍为 25 秒，客户端 30 秒；未执行的排队请求取消，已执行但未返回的请求记为 unknown，必须查询原 ID。**这不是对任意 C++ 死循环的强制中断保证**，Python 无法安全抢占卡住的 CAD 主线程，也不能从 C++ abort 恢复。此次修复阻断已知的非法构造路径，并用真实进程验证错误后的存活；未引入会丢失手工修改的自动重启。若要求所有原生内核故障后同一实例仍可建模，需要另行设计进程隔离/工作副本恢复；当前没有声称已完成这层保证。

依据：[FreeCAD Constraint 构造重载](https://github.com/FreeCAD/FreeCAD/blob/main/src/Mod/Sketcher/App/ConstraintPyImp.cpp)、[dsh 初始化图片门](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/acp/acp/src/index.ts)、[dsh 图片准入检查](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/acp/acp/src/content.ts)、[官方 ACP profile 的初始模型配置](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/bundle/acp-app/cordis.patch.yml)。已安装版本的真实拒收以第四轮日志为准；启动 patch 的效果须第五轮确认。

下一轮沙箱外命令（两组独立运行，每组自动先做宿主回归）：

```sh
cd /Users/huaiyi/.codex/worktrees/7115/gongke-workbench
(
  set +e
  set -o pipefail
  for input_mode in dimensions vision; do
    /private/tmp/gongke-modeling-venv/bin/python scripts/agent_modeling_trial.py --cases p7 --delivery "$input_mode" 2>&1 | tee "/tmp/trial5-$input_mode.log"
  done
)
```

本地验证：桌面构建通过，桌面测试 51 通过/1 跳过，Python 原生建模/事务/审计相关测试 56 通过。日志 `out/agent-modeling-dev/round5-{build,desktop,native}.log`。这些是参数、事务和协议测试，不冒充 FreeCAD/真实模型运行。

最终补充验证：桥接客户端 22 项通过（Python 合计 78 项）；新增“ACP 真正返回 -32602 → 收集器写入 acp-error.json/result 字段 → 清理错误不覆盖原始错误”的协议回归连同试验辅助测试 7 项通过。两种 prepare-only 均成功，宏/脚本语法及 git diff --check 通过。共享 `.git` 的分支锁写入被沙箱拒绝，未创建新提交；全部修改保留在当前 worktree，供 Claude 审阅后提交。

## 第 5 轮：首次自主建模通过，视觉理解仍有偏差（2026-11-03）

原始证据：dimensions=`out/agent-modeling-20261103-055425/`，vision=`out/agent-modeling-20261103-055938/`。历史文件不改写；本轮诊断派生记录放在 `out/agent-modeling-dev/round6/`。

| 观测 | dimensions | vision |
| --- | --- | --- |
| 总耗时 / 工程工具调用 | 296.022 s / 37 | 608.941 s / 51 |
| 输入理解 | 人工尺寸均采用；明确说明 R10 假设 | 9 个标注读对 8 个；底板 8→6；随后将贯通槽解释为盲槽 |
| 原生模型 / 最终修订保存 / 自查 | 均完成 | 均完成，但自查依据含错误假设 |
| 独立图纸审核 | accepted=true，全部 8 条通过 | accepted=false，底厚及 z=4 mm 截面不符 |
| 模型体积 | 7745.026283 mm³ | 7575.751919 mm³，较参考少 169.274364 mm³ |
| host.sketch / host.feature / host.check | 6 / 5 / 5 | 13 / 5 / 4 |
| host.measure / host.section / host.inspect | 8 / 1 / 2 | 4 / 9 / 4 |
| 应用执行失败 | 2 | 10 |
| 成功返回但被 dsh 拒收的负零结果 | 7 | 5 |

vision 首轮 `vision-check.json` 已把底板读为 6，其余为总高 11/20、筒径 20/14、圆心距 14/18、R5/R3。建模据此使用底板 6、凸台增高 5、筒增高 14；槽切深 5，到底板顶面停止。最终回复用剖面和轴测图暗色槽底解释其盲槽假设，并说明需确认。它没有在后续纠正 6 mm 或盲槽。最终较完整的一次 host.check 有 16 条且 pass，验证的是这套自选解释；独立检查在 z=4 mm 得到 800.221225 mm²，正确贯通槽参考为 687.946891 mm²。z=9/15 mm 截面通过，说明上部轮廓基本一致。由此可把主要几何偏差归到读图/空间解释，而不是特征执行失效。

dimensions 的旧失败状态**不是单纯“待目视复核”标记**：重开检查把显示网格包围盒的 51.97203797 mm 与建模时的 52 mm 比较，从而否决。体积、有效性、单实体和原生树均保持。直接从已保存 FCStd 取出 BREP，用另一进程 OCCT 读取，长度仍为 52 mm（`saved-brep-bounds.json`）；修复 `host.inspect` 和重开检查的包围盒实现，不放宽容差、不修改已保存模型。此次可确认 dimensions 自主生成的模型符合既有参考；修复版重开 GUI 仍须下一轮验收。

进一步离线复现：对该保存 BREP 以线偏差 0.1、角偏差 0.3 生成显示网格，再按 FreeCAD 源码调用 Add + SetGap(0)，得到 **51.9720379718118 mm**，与第五轮误判完全相同；AddOptimal(False, False) 在四组网格参数下均为约 52.0000001 mm。证据 `meshed-brep-bounds.json`，明确区分离线内核复现与真实 GUI 验收。

耗时方面，dimensions 有 37 项、vision 有 49 项服务回执包含起止时间，累计仅 3.330466 / 4.713430 s（vision 另两项参数校验失败没有结束时间）。不能把 296/609 s 主要解释成 FreeCAD 计算慢。vision 6 次草图求解冲突/冗余、1 次追加时遗漏 body_ref，另有空 Body 检查及猜测 snapshot 命令失败；这使模型多次试约束、读上下文。两组均因负零传输失败重复 inspect 或转向旧读取入口。第五轮 dimensions 使用旧目录项 deepseek-v4-flash，vision 使用 deepseek-flash，因此耗时差不能仅归因于图片输入。

第六轮修改与可观察差异：

1. MCP 出口统一负零。原始 37/51 项结果离线经过生产函数，再调用 dsh 公开 `snapshotJsonValue`：拒收 7→0、5→0，其他数值不舍入、原回执不改。真实 SDK 集成测试同时核对 text 与 structuredContent。依据见 [检查接口补充](model-inspection.md)。
2. 原生包围盒改为无显示网格的精确方法，重开保留旧 display_bbox 及误差字段。截图关闭相机动画，避免第五轮立即截图留下俯视起点。状态改成 passed、review_required、drawing_mismatch、reopen_failed、modeling_failed、verification_failed、run_failed；初次误读不否决后续已纠正的最终模型。截图/关闭日志的非核心错误单独留证，不把正确模型改判失败。
3. MCP 引导减少冗余约束和重复检查：端点 tangent 已含重合，fixed whole 不再叠尺寸，有效欠约束可继续；追加草图须 body_ref，取最近修订。按需 inspect 获取拓扑，批量 check 尺寸/截面，检查依据与读图假设分开。不增加“必须按某条调用路线”的限制。
4. 图片工具增加 crop/scale，原文件不改，只输出原像素的局部/最近邻放大。vision 首轮增加槽/孔贯通关系及 evidence/uncertain，允许 null，不将标准答案反馈模型。各字段结果单独记录，工具和读图引导见 [图纸输入](drawing-input.md)。
5. P6 新用例的尺寸台账明确区分已复核 15 mm、候选小字和因裁边而设的假设，不含 CAD 配方。dimensions 只接收台账，vision 只接收原裁图；manifest 保存台账/源图/裁图哈希，期望值不进入 vision 工程。P6 暂无足够独立图纸真值，构建链路成功单列，符合性保持 review_required。需要更清晰的竖向尺寸或人工复核后才能报告其建模正确率；不将这些候选数当成自动验收答案。
6. 每次重复使用独立 FreeCAD/应用/ACP/工程，防止 host.context 泄露上一次答案。dimensions 与 vision 均通过隔离启动 patch 和会话选模选中 deepseek-flash；仍不改变全局模型配置/凭据。六次均执行，失败也保留。每次自动先做 8 项宿主约束回归，未通过则不消费模型 token。
7. 用量收集修复：dsh 的 [Zstd 持久化](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/session/session-persistence-jsonl/src/zstd.ts) 是多帧追加；旧一次性解压只得到 session 头。现在按 Node 公共 [info/bytesWritten](https://nodejs.org/api/zlib.html#zlibbyteswritten) 继续解码剩余帧，完整脱敏保存，按顶层事件类型汇总，不重复累计内嵌 stream。重读两组既有会话分别恢复 315/446 条事件、37/54 条 assistant/message 用量。派生证据在 `recovered-055425/`、`recovered-055938/`，原试验记录保持原样。

恢复的真实 dsh 用量（各条 assistant/message 的 usage 累计，含缓存输入；不是 ACP 当前上下文长度）：

| 字段 | dimensions | vision |
| --- | ---: | ---: |
| inputTokens（未含缓存命中） | 50,114 | 69,215 |
| outputTokens | 38,989 | 82,948 |
| cacheReadTokens | 1,659,136 | 4,148,096 |
| totalTokens | 1,748,239 | 4,300,259 |

cacheWriteTokens 均为 0；持久化用量未报告金额，费用仍未知，不按模型显示名猜价格。

第六轮命令见文档开头：P7 vision×2、P6 dimensions×2、P6 vision×2。前三种输入的 prepare-only 已执行，确认 vision 工程输入不含尺寸 JSON。当前修改通过 Python 相关 89 项、桌面 53 项（另 1 跳过），桌面构建通过；日志为 `out/agent-modeling-dev/round6/{python-tests,desktop-tests}.log`。协议/宿主替身测试与离线 BREP/会话重读不计入新的真实模型成功样本；速度和稳定性改善须由第六轮六次沙箱外结果衡量。

提交：本轮 `git add` 创建共享 `.git/worktrees/gongke-workbench12/index.lock` 被沙箱以 Operation not permitted 拒绝，未产生提交。修改留在当前 worktree，未 push/合并；Claude 审阅后可代为提交，提交尾注沿用 `Co-Authored-By: Codex <noreply@openai.com>`。

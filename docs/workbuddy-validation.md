# WorkBuddy 实机验收

完成条件是：真实 WorkBuddy 在验收工程中加载项目 MCP，实际调用 gongke 读取工程和尺寸，在独立 FreeCAD 中建立可编辑 P7 零件，同一构想引擎桌面出现对应任务和操作回执。配置文件存在、SDK 探针通过、WorkBuddy 显示绿色各自只证明其中一步。以下操作由 Claude 在沙箱外执行；本清单不代表实机已经通过。

本机 5.9.3 的项目级加载实验失败，现采用经用户明确同意的用户级工程专属连接器，详见[实测与撤销](workbuddy-conflicts.md)。下文提示词中的 `gongke` 必须替换为引导显示的实际专属名称，本轮为 `gongke-1dd0f773059c`。旧 `gongke` 保留但不可用于验收。初次写入及升级写权限均须征得用户同意。

## 每轮准备与启动

始终使用当前 checkout；不要直接复制其他验收文档中的旧 worktree 路径。三个终端使用同一组变量。`RUN` 必须是新目录；修改源码后停止本轮独立进程，换新 `RUN` 重启，保留旧证据。

终端 A，准备工程并启动本轮 FreeCAD 与 Electron：

```sh
cd /Users/huaiyi/.codex/worktrees/7658/gongke-workbench
export ROOT="$PWD"
export RUN="$ROOT/out/workbuddy-$(date +%Y%m%d-%H%M%S)"
export GONGKE_PYTHON=/private/tmp/gongke-modeling-venv/bin/python
export GONGKE_MODELING_ROOT="$ROOT"
export GONGKE_FREECAD_SESSION="$RUN/runtime/host/session.json"
export GONGKE_DESKTOP_USER_DATA="$RUN/runtime/desktop"
"$GONGKE_PYTHON" tests/e2e/workbuddy_prepare.py \
  --study /Users/huaiyi/Documents/gongke-workbench/out/drawing-to-model-study \
  --output "$RUN"
mkdir -p "$RUN/screenshots"
(cd desktop && npm run build) > "$RUN/desktop-build.log" 2>&1
"$GONGKE_PYTHON" scripts/run_desktop_acceptance.py --output "$RUN/runtime" --timeout 7200
```

`GONGKE_PYTHON` 必须指向已经安装当前项目依赖的 Python 3.11+ 虚拟环境；不存在时先在沙箱外创建独立环境并安装 `.[desktop]`。保留虚拟环境解释器路径，不把它替换成符号链接最终指向的系统解释器。准备脚本把尺寸、检查条件和原图逐字节复制到 `project/references/`，原材料保持不变，`preparation.json` 保存来源与哈希。

FreeCAD 菜单“视图 → 面板 → 报告视图”中应出现“原生建模验收桥接已启动”。检查 `$RUN/runtime/host/bootstrap.json` 的 `root` 为当前 checkout，三个源码路径也在当前 checkout。桥接文件不存在或加载了旧安装工作台就停止本轮，回传日志；不要改个人工作台配置。截图 `00-freecad-host.png` 保留 FreeCAD 窗口和启动信息。

启动器使用全新 userData 与桥接端点，不需要关闭其他窗口。关闭本轮桌面、Ctrl-C 或达到 `--timeout` 后，只按启动句柄回收本轮进程；验收文档应在结束前保存，文件证据保留。首次安装依赖才需要 `npm ci`。

启动后在构想引擎顶部点击“打开工程”，选择 **`$RUN/project` 目录**。底栏应显示同一绝对路径、“就绪”和“FreeCAD”。保持此工程打开，不另起 `native_modeling_freecad.py`：后者会启动自己的服务和工程，不能证明 WorkBuddy 操作了桌面当前工程。

终端 C 同样复制变量，用来运行下面的配置、探针和回执命令。桌面服务状态目录固定为 `$RUN/runtime/desktop/state`；`GONGKE_FREECAD_SESSION` 必须在启动 Electron 前设置，不能只设置给 MCP 客户端。

## 第一轮：默认只读接入

1. 构想引擎右侧 Agent 引导选择“WorkBuddy”，检测安装后点击“预览 WorkBuddy 配置”。应停在连接页，显示用户配置路径、专属名称、保留的冲突项和固定工程范围；保存截图。获得用户同意后点击“同意备份并写入用户配置”，应进入首次对话，显示工程路径和备份路径。默认只读。
2. 查看 `~/.workbuddy/mcp.json` 的本工程专属条目：绝对 command；`--state-dir`、`--project` 分别为本轮状态目录和工程；开发版 PYTHONPATH 指向当前 checkout；无 `--allow-writes`。保留安装返回的备份路径与摘要；验证其他条目不变。本轮验收的是用户级专属连接器，项目级加载已记录失败。
3. 先运行协议探针，分离配置或服务故障与 WorkBuddy 客户端故障：

```sh
cd /private/tmp
"$GONGKE_PYTHON" "$ROOT/tests/e2e/workbuddy_acceptance.py" probe \
  --project "$RUN/project" --require-freecad \
  --output "$RUN/probe-readonly.json"
```

探针按生成文件中的 command/args/env/cwd 启动 MCP，配置未指定 cwd 时使用临时目录，读取工程和宿主，核对任务收据。这样可检查配置离开源码目录后的启动能力。退出码为零且输出 `status=passed` 后再继续。此探针调用的 task_id 只属于探针，不能拿来完成 WorkBuddy 引导。

4. 点击构想引擎引导中的“打开 WorkBuddy”，登录已有账号。记录实际版本。WorkBuddy 点击“新建任务”，在输入框左下角点击“选择工作空间”，选择 `$RUN/project`；核对路径后再发消息。不是仓库根目录，也不是 WorkBuddy 默认工作目录。工作区信任弹窗出现时，在核对验收目录后选择正常打开/信任；受限模式不能作为 MCP 加载成功。保存 `01-workbuddy-workspace.png`。
5. 进入 WorkBuddy MCP 页面。官方旧指南入口为“插件 → 右上角 MCP 服务器 → 配置 MCP”；新版导航为“专家·技能·连接器 → 连接器”。在当前版本的自定义 MCP 列表找到 **引导显示的工程专属名称**，打开详情，核对其 command、工程参数与生成文件相同；若有“信任”或服务启用开关，信任并启用这一个服务。记录实际点击路径，不把官方新版菜单冒充本机 5.9.x 的实测界面。
6. gongke 应显示绿色/已连接。展开工具列表，截图应能读到 `project.current`、`project.files`、`project.read_file`、`hosts.list`、`host.context`、`host.inspect`、`host.check`，此轮不应出现 `host.model_new` 或 `host.feature`。保存 `02-workbuddy-gongke-readonly.png`。如果新版界面要求为任务启用连接器，在输入框“+ → 连接器”开启 gongke。
7. 发送以下提示；出现 gongke 工具授权时，检查工具及工程范围后允许本次操作。保留实际工具卡片和返回正文，不只保留总结：

```text
这是构想引擎 WorkBuddy 只读接入验收。请只调用 gongke 的 project.current，
告诉我工具返回的工程名称、绝对路径和状态，并逐字列出返回的 task_id。
不要用文件读取、终端命令或记忆代替这次工具调用；不要修改任何文件。
```

成功条件：WorkBuddy 明确显示 `gongke / project.current` 实际调用，结果 `status=complete`，路径为 `$RUN/project`，返回 32 位十六进制 task_id。保存 `03-workbuddy-project-current.png`。把此 ID 填回构想引擎“回复中的 task_id”，勾选已看到绿色状态和真实回复，点击“核对工程回执并完成”。预期“工程读取回执已验证；WorkBuddy 回复由你确认”。保存 `04-desktop-onboarding-verified.png`。

没有 gongke 时先确认任务工作空间；再检查“设置 → 安全中心 → Tool 管控 → MCP”的自定义 MCP 总开关和 gongke 工具启用状态，不修改无关服务。只有绿色没有工具调用，或工具仅从对话里被列举，均不计通过。

## 第二轮：原图、尺寸与写权限

1. 在 WorkBuddy 同一验收工作空间的对话框拖入 `$RUN/project/references/drawing.jpg`，确认图片缩略图出现，再发送：

```text
请查看附件原图中的 P7（原图区域约 x=77..451、y=1282..1574）。
同时必须调用 gongke project.read_file，path="references/dimensions.json"，
再读 references/cases.json。请列出 P7 的已标注尺寸、坐标约定、缺失尺寸和假设，
比较原图与 JSON；每次工具调用列出 task_id。本轮不建模。
特别确认 20 和 11 是总高，长度单位 mm 是本试验假设，左端外轮廓 R10 是假设。
看不清的标注请明确说明，不把 JSON 数值说成自己从图片识别出的结果。
```

`project.read_file` 目前只读文本/JSON/SVG，不能读取 JPEG 像素；本轮原图由 WorkBuddy 的图片附件能力读取，结构化尺寸由 gongke 读取。若模型无法查看附件，记录“原图阅读未通过”，不要以 JSON 读取成功替代。保存 `05-workbuddy-drawing-dimensions.png`，包含附件、实际 `project.read_file` 调用及来源说明。

2. 本试验采用如下 P7 数值（mm）：底厚 8；凸台总高 11；筒总高 20；筒外/内径 20/14；槽两端圆心距 14；槽右端至筒轴 18；凸台/槽半径 5/3；底板端部半径假设 10。槽左圆心 `(0,0)`，右圆心 `(14,0)`，筒轴 `(32,0)`，底面 `z=0`。这些是本次试验输入，不增加未标注公差或宣称可直接制造。
3. 用户明确同意后，终端 C 授予本验收工程建模权限，并保存本次配置输出：

```sh
cd "$ROOT"
"$GONGKE_PYTHON" -m gongke_app workbuddy \
  --state-dir "$RUN/runtime/desktop/state" --project "$RUN/project" \
  --allow-writes --confirm-user-config > "$RUN/configure-write.json"
cd /private/tmp
"$GONGKE_PYTHON" "$ROOT/tests/e2e/workbuddy_acceptance.py" probe \
  --project "$RUN/project" --require-freecad \
  --output "$RUN/probe-write.json"
```

4. 回到 WorkBuddy 的 gongke 详情：检查是否已经读到新的 `--allow-writes` 和建模工具。若没有，先用界面提供的重启/重新连接该 MCP 操作；仍未刷新则退出 WorkBuddy 后重新打开，新建任务并选同一工程目录。记录实际生效方式、是否重新弹出信任，不声称外部改文件必定即时重载。不要再次点击构想引擎“重新生成配置”，该引导默认只读，会撤掉建模授权。
5. 保存 `06-workbuddy-gongke-writes.png`，能看到 `host.model_new`、`host.sketch`、`host.feature`、`host.model_save`。保留已有 WorkBuddy 账号、其他 MCP 配置，不启用全局“完全访问权限”。

## 第三轮：WorkBuddy 调用工具建立 P7

在已启用写权限的 WorkBuddy 任务中发送以下提示。若第二轮为重载而创建了新任务，重新附原图并让它先读尺寸和检查条件。

```text
请通过 gongke 工具，在当前构想引擎工程的新文件 p7_workbuddy.FCStd 中建立 P7。
先调用 project.current、hosts.list、host.context，确认当前工程和 FreeCAD 实例。
读取 references/dimensions.json 与 references/cases.json。采用刚确认的试验 mm 单位和
底板端部 R10 假设；实际建模 API 长度换算为 m，角度为 rad。

只能用 gongke 的 host.model_new / host.sketch / host.feature 等原生工具建模，
不得运行 shell、Python、宏，也不得导入参考 STEP 代替草图与特征。
若支持 MCP resource/prompt，先读 gongke://modeling 或 native-modeling；不支持时按工具描述。
文件必须是新的，若已存在先停止并报告，不覆盖也不自行换名重复执行。

采用 5 张原生草图、5 个原生特征：
Base：XY 底面，圆心 (0,0) 与 (32,0)、端半径 10 mm 的胶囊轮廓，pad 8 mm。
Boss：XY 偏移 8 mm，圆心 (0,0) 与 (14,0)、半径 5 mm 的胶囊轮廓，pad 3 mm。
Tube：XY 偏移 8 mm，圆心 (32,0)、直径 20 mm，pad 12 mm。
Bore：XY 底面，圆心 (32,0)、直径 14 mm，pocket through_all=true、reversed=true，
不传 length，使通孔从底面向上贯穿。
Slot：XY 偏移 11 mm，圆心 (0,0) 与 (14,0)、半径 3 mm 的胶囊轮廓，pocket 11 mm。
胶囊以两条直线与两条三点圆弧组成闭合轮廓。设置命名半径/直径约束；
如草图欠约束如实报告，不添加固定约束来声称完全约束。

每次写入使用新的 UUID operation_id，并使用上一回执最新 document 与真实 body_ref、
sketch_ref、feature_ref；不要猜对象身份或面编号。写入结果未知时只查询原 operation_id，
不要换 ID 重发。先新建并保存到工程内，再操作登记的工作副本。
每个特征后调用 host.inspect，最后用 references/cases.json 的 p7 条件调用 host.check，
逐项报告实际尺寸。全部通过后 host.model_save，再 host.model_operation 查询保存回执。
列出各次调用的 task_id，尤其是 model_new、最后 inspect、check、model_save 和 operation。
```

授权弹窗只允许本任务声明的 gongke 操作。若 WorkBuddy 提出安装依赖、执行生成脚本或调用其他 CAD MCP，停止该替代路线，回传它为何未使用 gongke。可纠正参数错误，但保留失败调用与修复过程；不要把手工建模或探针建模计为 WorkBuddy 完成。

成功条件：

- FreeCAD 中出现 `p7_workbuddy` 文档，Body 下有 Base/Boss/Tube/Bore/Slot 及对应 Sketch；模型为有效单实体。`host.inspect` 中至少 5 个 `Sketcher::SketchObject`，没有用 `PartDesign::Feature` 导入体代替本次建模。
- `host.check` 总状态和各项均为 `pass`，尤其是 14 mm 筒内径、20 mm 筒总高、8 mm 底厚及槽位置；`unknown` 不算通过。
- 保存返回成功，路径位于 `$RUN/project`；原 operation_id 查询返回同一保存操作。生成文件存在且非空。
- 保存后在 FreeCAD 展开树，选择 Tube，属性“长度/Length”为 12 mm；查看 Bore 的贯通类型和整体孔槽外观。保留 `07-freecad-p7-tree.png` 与 `08-workbuddy-model-check-save.png`。不要为验截图修改参数或原始资料。

## 第四轮：同一桌面任务与回执

1. 不重启构想引擎，也不重新打开同路径工程。点击底栏右侧“操作记录”（执行时显示“n 项执行中”）。应已自动出现 WorkBuddy 刚执行的工程操作，状态“已完成”。
2. 对读取工程、新建、最终检查、保存等记录点击“查看操作回执”，再展开 `project.current`、`host.model_new`、`host.check`、`host.model_save`。核对参数、时间、原生 operation_id 及返回结果与 WorkBuddy 实际工具结果一致。当前桌面未直接显示 task_id，下一步用数据库记录完成 ID 对照；不能声称截图里已有该字段。保存 `09-desktop-tasks.png`、`10-desktop-save-receipt.png`。底栏路径须入镜；“已完成”仅证明工具执行结束，尺寸通过还须检查 `host.check` 的 `result.status=pass`。
3. 用 WorkBuddy 实际回传的 task_id（不是 probe 的 ID）运行只读收据核对：

```sh
cd "$ROOT"
"$GONGKE_PYTHON" tests/e2e/workbuddy_acceptance.py receipts \
  --project "$RUN/project" --output "$RUN/workbuddy-receipts.json" \
  --task-id '<project.current 的 task_id>' \
  --task-id '<读取 dimensions.json 的 task_id>' \
  --task-id '<host.model_new 的 task_id>' \
  --task-id '<最终 host.inspect 的 task_id>' \
  --task-id '<最终 host.check 的 task_id>' \
  --task-id '<host.model_save 的 task_id>' \
  --task-id '<host.model_operation 的 task_id>'
```

实际运行前替换尖括号内容，可追加其他真实 ID。此命令不发起建模，只核对工程数据库；“由 WorkBuddy 发起”的来源需要工具截图交叉证明，数据库不会自行鉴定客户端身份。

## 失败回传与验收记录

每轮回传 `$RUN` 的绝对路径、当前 checkout/提交、WorkBuddy 实际版本、完成到哪一步、第一处失败。附 `preparation.json`、`host/bootstrap.json`、两个 probe JSON 和 stderr、`workbuddy-receipts.json`（已生成时）、FreeCAD/Electron 日志、对应截图以及模型文件。共享前遮盖 WorkBuddy 账号信息；不要回传 `$RUN/runtime/desktop/state/service.json` 中的服务令牌。

针对故障补充：

| 现象 | 回传内容与下一步 |
| --- | --- |
| 未看到 gongke | 工作空间路径、MCP 页面及相关开关截图；生成配置的 gongke 部分；区分“未加载项目文件”与“被禁用/未信任” |
| 红色/启动失败 | gongke 详情中的原始错误；probe stderr；确认配置解释器、状态目录和 PYTHONPATH。不要清空 WorkBuddy 配置或重装 |
| probe 通过但 WorkBuddy 失败 | 保留这两个事实；回传 WorkBuddy 实际 command/env/工具错误。SDK 成功不能替代客户端成功 |
| 工具列表缺写工具 | 检查配置是否确有 allow-writes，记录重连/重启后变化；不绕过执行端权限 |
| 宿主或修订错误 | FreeCAD bootstrap、原始工具输入输出、当前 context；源码变化重启独立宿主，旧修订不能直接重试写入 |
| 超时/写入结果未知 | task_id、operation_id、最后返回；只查询原 operation，保留文件与 FreeCAD 现场，不换 ID 重做 |
| 图纸理解或尺寸检查失败 | 原图附件截图、读取工具结果、逐项检查结果；不删失败条件，不改原始 cases/dimensions |
| 后端有回执但桌面没出现 | 同一 task_id 的数据库报告、桌面底栏路径、操作记录截图、desktop.log；标记桌面同步未通过 |

收尾报告分别填写“项目级加载（本机失败）”“用户级专属连接器加载”“MCP 工具列表”“真实只读调用”“原图阅读”“原生建模与检查”“桌面回执显示”的通过/失败/未运行及证据文件。没有对应实机证据的项目保持未运行。

官方入口依据（核查日期 2026-11-03）：[MCP 配置文件与状态](https://www.codebuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/MCP-Guide)、[创建任务与工作空间](https://www.codebuddy.cn/docs/workbuddy/Create-Task)、[连接器入口及任务启用](https://www.codebuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Connector)、[工作区信任与权限](https://www.codebuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Permission-Modes)。配置规则和 CLI/ACP 能力的证据范围见 [工程 Agent 接口](agent-api.md)。

## 本轮已运行证据（2026-11-03）

- 本机应用 Info.plist 为 WorkBuddy **5.9.3**；未启动或操作 WorkBuddy GUI。
- `tests/test_workbuddy_onboarding.py`、`tests/test_workbuddy_configuration.py`、`tests/test_mcp_server.py`、`tests/e2e/test_workbuddy_acceptance.py` 共 **16 passed**，日志 `out/workbuddy-tests.log`。包括真实虚拟环境入口、配置保留其他服务器、绑定/权限、SDK 调用与持久收据核对。
- 单独启动测试应用服务，经开发 CLI 生成实际配置，再从 `/private/tmp` 运行验收探针：列出 **29 个只读工具**，`project.current`、`project.files`、`hosts.list` 三次调用均与服务收据一致。证据 `out/workbuddy-protocol-run/probe.json`、`configure.json`。该服务已关闭，配置仅作为证据，不可直接用于 GUI 验收。
- 准备脚本已逐字节复制真实尺寸、检查条件及 JPG，三个 SHA-256 一致，证据 `out/workbuddy-prepared/preparation.json`。没有改写原材料。
- 本轮没有运行 FreeCAD/Electron/WorkBuddy GUI；以上四轮的真实项目加载、图片阅读、P7 建模及桌面显示仍待 Claude 执行并回传。

# IDE 工作台布局验收

本文前半记录初次交付；合并后复验见文末。

2026-11-03；分支 `codex/ide-workbench-layout`，改前基线 `a238113`。

## 交付

外层采用标题命令中心、活动栏、资源管理器、编辑器组、底部 Panel、右侧 Agent 和状态栏。命令/文件搜索、预览/常驻标签、右键菜单、文件分屏、原生选择面包屑已接入现有工程入口。完整元素放置表、官方依据和快捷键见 [DESIGN.md](../desktop/DESIGN.md#工作区)。

`desktop/src/agent/` 无改动；宿主写入命令、工作副本、对象身份及修订检查没有替换。没有启动付费模型或发送 Agent prompt。

## 运行证据

| 检查 | 结果 | 文件 |
| --- | --- | --- |
| `npm run build` | 通过；仍有依赖的 use-client 和大 chunk 警告 | [build.log](../out/ide-workbench/logs/build.log) |
| `npm test` | 62 项：61 通过，0 失败，1 Windows cmd 专用项跳过 | [tests.log](../out/ide-workbench/logs/tests.log) |
| `node tests/workbench-flow.cjs` | 8 组交互断言通过，无页面异常 | [checks.json](../out/ide-workbench/interactions/checks.json) |
| `node tests/workbench-live.cjs` | 生产 Electron + 实际 Python：新建工程、导入并读取 SVG；Cmd+P/Cmd+W 有效；Agent 保持 disconnected | [checks.json](../out/ide-workbench/live-final/checks.json) |
| `node tests/workbench-capture.cjs` | 改前、改后各 4 张；1366×768 / 1920×1080 × 浅色/深色；PNG 尺寸逐一核对 | [改后错误列表](../out/ide-workbench/after/errors.json) |

本机 Python 使用 `/Users/huaiyi/Documents/gongke-workbench/.venv/bin/python`，通过 `GONGKE_PYTHON` 显式传入。默认 Python 首轮有 3 项服务启动失败，切换到项目现有依赖环境后全部相关测试通过；没有修改测试断言来绕过失败。

布局对照与交互脚本使用生产 renderer 和仓库已有确定性服务/CAD 样例；样例图纸明确标注界面评审。生产截图另用真实导入的 SVG，未模拟服务成功或原生 CAD 连接。初次前台使用前已截屏确认没有目标窗口被占用；后续均使用独立 userData 的后台 Electron，未操作其他会话窗口。

## 截图

[并排对比索引](../out/ide-workbench/index.html)

| 尺寸 / 主题 | 改前（相同样例） | 改后（相同样例） | 生产 Electron（实际工程） |
| --- | --- | --- | --- |
| 1366×768 浅色 | [查看](../out/ide-workbench/before/1366-light.png) | [查看](../out/ide-workbench/after/1366-light.png) | [查看](../out/ide-workbench/live-final/1366-light.png) |
| 1366×768 深色 | [查看](../out/ide-workbench/before/1366-dark.png) | [查看](../out/ide-workbench/after/1366-dark.png) | [查看](../out/ide-workbench/live-final/1366-dark.png) |
| 1920×1080 浅色 | [查看](../out/ide-workbench/before/1920-light.png) | [查看](../out/ide-workbench/after/1920-light.png) | [查看](../out/ide-workbench/live-final/1920-light.png) |
| 1920×1080 深色 | [查看](../out/ide-workbench/before/1920-dark.png) | [查看](../out/ide-workbench/after/1920-dark.png) | [查看](../out/ide-workbench/live-final/1920-dark.png) |

附：[问题 Panel](../out/ide-workbench/interactions/problems-panel.png)、[分屏](../out/ide-workbench/interactions/split-editors.png)、[命令面板](../out/ide-workbench/interactions/command-palette.png)。截图与日志保留在本 worktree 的 `out/ide-workbench/`，不把运行用户数据提交到 Git。

已目视检查四组改后矩阵及问题、分屏、命令面板。主要变化：顶部全局按钮归入视图标题；检查不再挤占编辑标签；右侧会话入口归位；分屏工具栏在窄宽度下使用图标；修复 Fluent Portal 复制全屏外框遮挡底层工作台的问题。

## 取舍与接续

- 文件可分屏；原生 CAD 与可写计算文档只保留一个编辑实例。完整原生特征树继续在 CAD/原生检查视图，资源管理器按工程文件分类；面包屑使用已经读取的 FreeCAD 特征 parent 链，不从名称猜 Body。
- 历史入口已定位，但现有 AgentAPI 未提供历史枚举/恢复。对话框明确告知实际能力；下一步由 Agent 会话提供该接口，不能用操作记录冒充历史。
- 初次交付的标题栏 CSS 锚点已在合并后复验中替换为实际 `headerActions` 插槽，见下文。
- 本轮未运行 Windows CAD 原生窗口。Windows 合并验收需确认：打开命令面板/右键菜单时 HWND 隐藏、关闭浮层后恢复、面板 resize 后宿主区域对齐、原生焦点下快捷键仍由 CAD 接收。
- 初次交付尚未更新的旧流程选择器，已按本次用户授权更新并复跑，见下文。


## 合并后复验（2026-11-03）

本分支先快进合入 `codex/windows-delivery-20261102` 的 `9b7b5ae`，再修复流程定位和 Agent 衔接。

- 工程操作经资源管理器菜单进入；问题、操作记录经活动栏进入；固定图纸先双击后验证切页、重开与视角保留。菜单常态/悬停/图标对比度、禁用状态、对象身份和修订断言保留。
- Agent 详情优先显示回执或请求中的中文名称；缺名时显示已知类型与尺寸。内部引用仍保存在原始回执，并继续用于定位。无类型数据时明确显示未提供名称，不猜测设计用途。
- 新会话按钮实际位于 Agent 标题栏；历史入口由 `headerActions` 注入。删除跨组件的绝对定位样式。现有协议仍无历史枚举/恢复能力，入口如实告知，没有伪造会话列表。

| 实际运行 | 结果 | 证据 |
| --- | --- | --- |
| `npm run build` | 通过 | [build.log](../out/merged-validation-logs/build.log) |
| `npm test`（指定项目 Python） | 66 项，65 通过，1 Windows 专用项跳过，0 失败 | [tests.log](../out/merged-validation-logs/tests.log) |
| `node tests/visual-review.cjs ../out/merged-layout-review-final` | 16/16 截图，2/2 交互，0 失败 | [review.json](../out/merged-layout-review-final/review.json)、[failure.json](../out/merged-layout-review-final/failure.json) |
| `node tests/agent-visual-review.cjs ../out/merged-agent-review-final after` | 四种尺寸/主题通过；每组 36 次调用；名称、尺寸回退、标题栏与历史断言通过 | [after-evidence.json](../out/merged-agent-review-final/after-evidence.json) |
| `node tests/desktop-flow.cjs` | 生产 Electron/Python 的创建、计算、生成与图纸读取通过 | [result.json](../out/desktop-validation/1793757215883/result.json) |
| `node tests/workflow-flow.cjs` | 实际生成 STEP、图纸、说明书，过期、重开与工程隔离通过 | [result.json](../out/workflow-validation/1793756979172/result.json) |
| `node tests/acp-flow.cjs` | 确定性 ACP 测试 Agent 会话与授权通过 | [日志](../out/merged-validation-logs/acp.log) |
| `node tests/commercial-flow.cjs` | 测试宿主的修订、工作副本、待核实与同 ID 恢复检查通过 | [日志](../out/merged-validation-logs/commercial.log) |

桌面流程在一次并发构建期间启动 Electron 超时；构建完成后顺序重跑通过。所有 Electron 使用独立后台窗口，未抢占其他会话前台。Agent 截图使用明确标注的确定性会话/图纸样例，没有调用付费模型，也不充当原生 CAD 验收。

四组截图已目视检查，并核对 PNG 实际尺寸：

| 尺寸 | 浅色 | 深色 |
| --- | --- | --- |
| 1366×768 | [查看](../out/merged-agent-review-final/after-1366x768-light.png) | [查看](../out/merged-agent-review-final/after-1366x768-dark.png) |
| 1920×1080 | [查看](../out/merged-agent-review-final/after-1920x1080-light.png) | [查看](../out/merged-agent-review-final/after-1920x1080-dark.png) |

尚未执行：`freecad-flow.cjs` 已更新定位，但需独立 `GONGKE_FREECAD_SESSION` 才可做真机复跑；`agent-modeling-live.cjs` 已更新导入按钮定位，但真实付费 Agent 流程未启动。两项不计入上述通过数。

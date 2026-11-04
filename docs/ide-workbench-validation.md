# IDE 工作台布局验收

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
- 合并另一会话时，保留 `.agent-panel > .panel-heading` 与新会话按钮的样式锚点；如对方改了标题结构，按 DESIGN.md 的 `headerActions` 插槽约定一次替换，删除原定位样式。
- 本轮未运行 Windows CAD 原生窗口。Windows 合并验收需确认：打开命令面板/右键菜单时 HWND 隐藏、关闭浮层后恢复、面板 resize 后宿主区域对齐、原生焦点下快捷键仍由 CAD 接收。
- 旧 `desktop-flow.cjs` / `visual-review.cjs` 的顶部“工程命令”与检查编辑页选择器针对旧布局，本轮保留其原始测试材料，新增工作台脚本验证新入口；后续若恢复运行旧脚本，需要同步其界面选择器。

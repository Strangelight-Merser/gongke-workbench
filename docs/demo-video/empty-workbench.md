# 桌面减速器界面删除与空工程验收

本轮只删除桌面减速器 UI，不改 gongke_core 或减速器计算实现。删除 ReducerTask、ConditionFields、CheckViews、专用 workflow；去掉树固定入口、路由、自动计算及其专用类型与样式。打开已有工程不再暗中计算。新建工程统一为空，Python、stdio、桌面均不写 api.example_task；project.create 不再接受 teaching。后端任务上的 teaching 来源标记保留。

## 保留待用户决策的应用入口

未发现 project.example 命令。现有对应入口为 design.example（取示例条件）、design.schema（条件字段定义）、project.set_task、design.calculate、design.generate。前两项曾供课程设计表单使用，仍可被 CLI/Agent 调用；后三项为共享后端计算链。本轮均未删除。应用侧未发现仍需删除的独占桌面实现；commands.py 与计算核心保持原样。

## 通用验收替代

desktop-flow 与 workflow-flow 共用真实通用工作台步骤，各自运行独立目录、进程和证据；不再有教学计算 UI 路径。仅文件选择对话框由脚本指定路径，工程、宿主、模型和结果都真实执行。

- 全新用户目录首次启动无工程；新建后任务为空、成果为空、工作副本为空、会话与工程任务列表为空。清单文件不作为用户文档展示。
- 导入独立生成的测试 PDF，逐字核对原文件；预览居中、适应可用宽度，面包屑为“图纸 › plate.pdf”，隐藏 inputs/哈希目录。
- 通过绑定工程的统一命令执行真实 FreeCAD 草图、拉伸、测量检查、保存。特征树、场景和检查回执使用同一原生文档修订；修改 4→5 mm 后旧检查显示已过期，不再保留旧通过覆盖层。旧修订操作被拒绝。
- 正常关闭应用和独立宿主，重启并打开已保存 FCStd，验证文件、树和任务回执仍在；新建第二工程不带入旧标签、文件与任务。
- 后端“一次结果供三维/二维/报告复用及条件变化标过期”的既有测试继续保留，以显式设置测试条件替代隐式新建示例。通用 UI 的同一原生修订/过期检查和后端成果复用分别验证，不冒称任意零件能自动生成减速器报告。

## 本地打包实测

npm run build 与 macOS electron-builder --dir 完成。以下均为新打包可执行文件、全新用户目录：

| 流程 | 宽度 | 证据目录 |
|---|---:|---|
| desktop | 1366 | `out/desktop-validation/1793799109538-1366` |
| desktop | 1920 | `out/desktop-validation/1793799186128-1920` |
| workflow | 1366 | `out/workflow-validation/1793799151807-1366` |
| workflow | 1920 | `out/workflow-validation/1793799216097-1920` |

每个目录包含 first-launch-empty.png、new-project-empty.png、import-centered-pdf.png、native-model-and-receipts.png、old-check-stale.png、reopened-project.png、isolated-empty-project.png 与 result.json/geometry.json。

Windows CI 配方同步改成空工程及显式后端计算测试，并以随包 FreeCAD 跑通用流程；本轮未触发新版 Windows CI，不将历史 41ec469 的安装成功推广为本次源码验收。

## 测试结果

- `npm run build` / `npm run package` 成功；macOS 签名验证通过。
- `npm test`：68 通过，1 项 Windows 专用测试在 macOS 跳过。
- Python 相关回归（空工程、应用服务、工程修订、MCP、资源枚举、工作副本、WorkBuddy 配置/隔离/引导）：77 通过。包含真实 STEP/图纸导出。
- 冻结服务复制到源码外、清除 Python 环境变量/PATH 后，显式设置测试条件，真实 STEP、DXF、SVG、PDF、DOCX、Markdown 导出均通过：`out/demo-video/service-clean-room-final-02/result.json`。示例条件仅在验收脚本显式注入，不影响新工程默认值。
- 初次扩大回归发现测试错误地把设置条件的回执当成生成回执，已匹配 generation 任务后复测通过；原失败日志保留。未修改生成算法或弱化导出断言。

视频制作因第二次 robot4 独立图纸验收失败停止，费用与原片见 handoff.md。此前完整影片与 89 秒片段均为历史产物，尚未替换为删除减速器后的完整新版。

# 无叠层原始录屏

产品基线：`b339f7b`，石墨与信号橙，录制前通过主题按钮切换深色。

`capture.cjs` 提供 `startCapture([ownPid], outputDirectory)`，返回 `mark(description)`、`switchWindow(ownPid)`、`stop()`。调用者负责真实界面操作、窗口 16:9 比例、光标平滑移动，以及避免显示图纸水印；此模块不添加任何画面元素。启动和停止各保留一秒静止，期间调用者不能操作界面。

采集使用 macOS 15 的 ScreenCaptureKit，仅选择显式传入的自有 PID 窗口，保留系统光标。原片为 `capture.mp4`；`clip.mp4` 仅规范为 H.264、2560×1440、60 fps。`events.json` 的时间取采集器媒体时钟；`probe.json` 保存最终规格。没有屏幕录制权限时直接失败，不用 CDP 截图或绘制光标替代。

当前进度（2026-11-04）：Swift 编译成功；Node 语法检查通过。系统 `CGPreflightScreenCaptureAccess()` 返回 false，实际录制和七段场景均未验收。负责启动本任务的应用为 Claude.app，需由用户授予屏幕录制权限后继续。没有调用付费 dsh。

已核对的入口限制：当前桌面没有文件拖放导入处理，应使用“导入图纸”按钮；空工程没有可分栏的 PDF 文件，不应为全貌镜头预置示例。第二次模型的两条错误斜边还需要通过实际 Sketcher 界面修正并复查，尚未完成此项操作。

Logo 概念位于 `out/demo-video/logo-concepts/`，共四张 1024×1024 PNG，说明在各自同名 txt，生成来源在 sources.json。尚未描成 SVG；生成位图仍有轻微纹理，不能视为最终纯色品牌资产。

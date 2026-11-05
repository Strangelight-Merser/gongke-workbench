# 最终演示视频工具

交付：`out/demo-video/final/film.mp4`，163 秒、1080p、30fps、H.264/AAC。字幕、旁白、来源清单与每镜抽帧在同目录。当前分镜 `docs/demo-video/storyboard.md`，事件完整性和检查缺陷记录在 handoff.md。本轮没有启动 dsh 推理会话；不要再使用 run_paid.py。

## 原始资料与录制

媒体和学生图纸只在本地 out，不提交 Git。复现需要首次真实成功会话 `paid-robot4/robot4-1`、用户允许展示的 robot4.pdf、历史真实参数编辑录像 manual-02 及其保存的 5 mm 工作副本。这些不是脚本生成的假数据。

- `record-final.cjs OUTPUT`：启动自有 Electron/FreeCAD，展示首次真实模型；仅在工具脚本中替换 ACP 接收通道，封禁 Agent 执行 IPC。71 个原始事件按顺序逐条回放，保留失败；完整 text/rawInput/rawOutput 不改。旧版用户参考全文进入新版已有折叠区，显示前缀等于原始 prompt。`replay-integrity.json` 校验全部事件逐项相等。没有产品回放入口。
- `record-pdf.cjs OUTPUT`：独立 Electron 原生 PDF 阅读器连续采集，不需要系统屏幕录制权限。
- `record-guide.cjs OUTPUT`：全新用户目录的开始页、空工程、已有 Agent 入口、安装引导，不连接 Agent。
- `capture.cjs OUTPUT`：真实 FreeCAD 凸台建模、检查不符、定位和修改；确定性工程工具操作，无模型推理。
- `session.cjs OUTPUT`：已有模型工作副本的真实 UI 录屏，stdin JSON 动作存档。最终修改后模型的操作在 actions/final-edited-01.jsonl，启动时 GONGKE_DEMO_MODEL 指向 manual-02/robot4-workcopy.FCStd。历史 manual.FCMacro 的 Qt 输入事件记录在 actions/manual.jsonl。

所有录制入口要求新目录，避免覆盖原片。只关闭自己启动的进程。recorder.cjs 保存真实起始帧并逐重绘采集，避免静止窗口的首帧丢失。重新录制会改变时间，按 recording.json 中 marks 重新选择区间；不能机械套用旧时间。

## 重建最终片

在仓库根目录执行，Python 环境需 Pillow 和 edge-tts，系统需 ffmpeg/ffprobe。当前机器可用 `/private/tmp/gongke-demo-video-venv/bin/python`。

```sh
GONGKE_DEMO_VOICE=out/demo-video/voice-final python tools/demo-video/voice.py
# 对 sources.json 中每个原片目录执行一次；manual-02 已有原片。
python tools/demo-video/encode_recording.py out/demo-video/final-main-03
GONGKE_DEMO_OUTPUT=out/demo-video/final GONGKE_DEMO_VOICE=out/demo-video/voice-final python tools/demo-video/render_film.py
GONGKE_DEMO_OUTPUT=out/demo-video/final python tools/demo-video/validate_film.py
```

最终 timeline.json 仅使用 final-main-03、final-guide-03、final-pdf-02、final-check-02、final-edited-01 和 manual-02；旧版其他原片均不进最终片。会话原运行 210.421 秒，完整回放约 40 秒，角标写总时长压缩约 ×5.3；存档缺少逐 ACP 事件时间戳，回放只保证原文、原序和总时长比例，不伪造逐事件原始延迟。

`validate_film.py` 验证完整解码、格式、所有区间、71 个事件完整性、失败保留和 Windows 原始 result.json 的 ok=true，并逐镜从最终 MP4 抽取两帧、生成来源哈希。`ocr-qa.swift` 用 macOS Vision 对抽帧辅助扫描路径/调试字段，不控制桌面；OCR 不能替代目视检查。

无音乐；使用 Edge zh-CN-XiaoxiaoNeural 和项目 OFL 字体。Windows 历史 CI 41ec469 与本版 macOS 验收严格分开。第二次 Agent 应用检查未发现轮廓偏差，因此最终片只用明确标记的凸台检查示例；该产品缺陷不在本轮修复。

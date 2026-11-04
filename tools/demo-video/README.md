# 构想引擎演示视频

正式片为 `out/demo-video/film.mp4`，184 秒、1920×1080、30 fps、H.264/AAC。中文字幕烧录，另附 `film.srt`、`narration.txt`、`sources.md`、`sources.json`、`validation.json`、`qa/`。大文件不提交；`style-preview.mp4` 是上一阶段截图预览，不是正式片。

## 从现有原片重现成片（不启动 Agent）

环境：Python 3.13、Pillow 13.0.0、edge-tts 7.3.1、ffmpeg 8.1.1/libx264；Node 使用项目已有环境。字体为 `desktop/src/assets/preview-font.ttf`，OFL。没有配乐。

```sh
/private/tmp/gongke-demo-video-venv/bin/python tools/demo-video/render_film.py
/private/tmp/gongke-demo-video-venv/bin/python tools/demo-video/validate_film.py
```

`timeline.json` 是唯一剪辑时间表：各段指向原片采集目录，begin/end 均相对该目录第一帧时间戳，duration 为成片时长。渲染直接按真实时间戳取帧，播放倍率由区间自动计算；快于原速就烧录倍率。静止画面保留采集器最后一帧，不补造动作。每句旁白的 voice_starts 对准操作，保留实际语速、只插入停顿。字幕位于画面外。

原片帧和 `recording.json` 保存在素材目录。独立 MP4 原片通过以下命令编码，保留实际时间跨度：

```sh
/private/tmp/gongke-demo-video-venv/bin/python tools/demo-video/encode_recording.py out/demo-video/showcase-01
```

`validate_film.py` 完整解码成片、检查编码/尺寸/帧率/时长，从最终 MP4 每镜抽帧，写来源表与 SHA256。旁白如需重新生成：`python tools/demo-video/voice.py`，默认保留已生成音频；文本来自已批准分镜。该命令把旁白文本发给微软 Edge 语音服务，不发送工程文件。

## 真实采集

- `recorder.cjs`：Electron CDP 连续帧与真实指针事件。
- `session.cjs`：启动独立 Electron，stdin 每行 JSON `{mark,code}` 操作真实控件；动作存档于 actions.jsonl，`{stop:true}` 收尾。若设置 `GONGKE_DEMO_MODEL`，启动独立 FreeCAD 并复制该文件；使用独立配置，等待模型加载。只关闭自己持有的进程。
- `actions/`：本次采用的 UI 动作及 native 参数编辑动作。它们是录制记录，不是产品功能，也没有填充或替换运行结果。重新录制时必须使用新输出目录，原片时序会变化，需重新剪辑。
- `capture.cjs`：免费确定性凸台检查，真实工程工具，已在 preflight-03 通过。它不是 Agent 自主纠错演示。
- `manual.FCMacro`：在独立 FreeCAD 的本轮副本上，以 Qt 按键/点击操作真实 Pad 编辑器；记录整个窗口。因 Qt 全窗抓取不能可靠包含 OpenGL 区域，正式片只采用参数面板特写。
- `check_current.py`：通过绑定工程 MCP 只读核对修改后厚度，不调用模型。
- `reducer_view.FCMacro`：独立 FreeCAD 导入真实同修订 STEP，持续采集运行中的视口和旋转过程；不是工作台 STEP 预览功能。需设置 GONGKE_VIEW_OUT、GONGKE_VIEW_STEP；另存时间戳及实体/体积记录。

`session.cjs` 使用的图纸导入 dialog 替身只返回本次明确授权的文件路径，实际导入、解析和显示仍由产品完成。没有在测试原件中改写提示词或断言。

## 付费入口：本轮授权已使用完毕

`run_paid.py` / `paid.cjs` 为唯一一次 robot4 的运行与录屏入口。用户已授权的那一次已完成，**不要再次启动**。脚本检查固定输出目录存在即拒绝运行，但这不能替代新一轮的明确授权；也不能删除目录绕过。

本轮 deepseek-flash / low，210.421 秒，passed；完整用量与价格见 `docs/demo-video/handoff.md`。原始会话、独立审计、保存重开、原片都在 `out/demo-video/paid-robot4/`。

## 事实与限制

减速器、凸台检查和 robot4 是三个明确区分的案例。减速器结果取自同一真实修订的工作副本；输入变动后的过期标记是真实 UI。Windows 证据来自指定 GitHub run 的安装工件；片中不宣称 Windows 商业 CAD 真机通过。没有 WorkBuddy 客户端镜头。原生参数编辑自动化展示的是学生可操作的真实入口，不是用户本人操作的实录。

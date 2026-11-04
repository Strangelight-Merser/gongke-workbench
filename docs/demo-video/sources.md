# 素材来源与剪辑清单

成片 184 秒，1920×1080，30 fps，H.264 / AAC。无配乐。全片使用真实连续界面或 CAD 视口采集，没有静态截图镜头。

时间均为相应原片 raw.mp4 起点后的秒数。每一段的画面只做裁剪、缩放、外框、实际光标强调和字幕处理，没有替换界面文本或模型。剪掉的等待不是连续运行耗时；唯一 Agent 任务实际 210.421 秒。

| 镜头 | 成片起点 | 原片 | 原片区间（秒） | 播放倍率 |
|---|---:|---|---|---:|
| 01 | 0.00 | `out/demo-video/showcase-02/raw.mp4` | 78.00–81.00 | 1 |
| 01 | 3.00 | `out/demo-video/paid-robot4/raw/raw.mp4` | 203.00–206.00 | 1 |
| 01 | 6.00 | `out/demo-video/showcase-01/raw.mp4` | 214.00–217.00 | 1 |
| 01 | 9.00 | `out/demo-video/showcase-01/raw.mp4` | 253.00–256.00 | 1 |
| 02 | 12.00 | `out/demo-video/paid-robot4/raw/raw.mp4` | 202.00–214.00 | 1 |
| 03 | 24.00 | `out/demo-video/paid-robot4/raw/raw.mp4` | 1.00–7.00 | 1 |
| 03 | 30.00 | `out/demo-video/showcase-02/raw.mp4` | 78.00–84.00 | 1 |
| 03 | 36.00 | `out/demo-video/paid-robot4/raw/raw.mp4` | 160.00–166.00 | 1 |
| 04 | 42.00 | `out/demo-video/paid-robot4/raw/raw.mp4` | 176.00–188.00 | 2 |
| 04 | 48.00 | `out/demo-video/paid-robot4/raw/raw.mp4` | 188.00–204.00 | 1 |
| 05 | 64.00 | `out/demo-video/showcase-01/raw.mp4` | 52.00–60.00 | 1 |
| 05 | 72.00 | `out/demo-video/showcase-01/raw.mp4` | 89.00–97.00 | 1 |
| 06 | 80.00 | `out/demo-video/paid-robot4/raw/raw.mp4` | 199.00–207.00 | 1 |
| 06 | 88.00 | `out/demo-video/preflight-03/raw.mp4` | 0.00–12.00 | 1 |
| 07 | 100.00 | `out/demo-video/manual-02/raw.mp4` | 97.00–101.00 | 1 |
| 07 | 104.00 | `out/demo-video/manual-02/raw.mp4` | 101.00–105.00 | 1 |
| 07 | 108.00 | `out/demo-video/manual-02/raw.mp4` | 131.00–134.00 | 1 |
| 07 | 111.00 | `out/demo-video/showcase-02/raw.mp4` | 68.00–71.00 | 1 |
| 07 | 114.00 | `out/demo-video/showcase-01/raw.mp4` | 89.00–97.00 | 1 |
| 08 | 122.00 | `out/demo-video/showcase-01/raw.mp4` | 214.00–217.00 | 1 |
| 08 | 125.00 | `out/demo-video/reducer-viewport/raw.mp4` | 3.00–6.00 | 1 |
| 08 | 128.00 | `out/demo-video/documents-01/raw.mp4` | 4.00–7.00 | 1 |
| 08 | 131.00 | `out/demo-video/showcase-01/raw.mp4` | 252.00–256.00 | 1 |
| 08 | 135.00 | `out/demo-video/reducer-01/raw.mp4` | 150.00–158.00 | 1 |
| 09 | 143.00 | `out/demo-video/showcase-01/raw.mp4` | 361.00–368.00 | 1 |
| 09 | 150.00 | `out/demo-video/showcase-01/raw.mp4` | 381.00–388.00 | 1 |
| 10 | 157.00 | `out/demo-video/showcase-01/raw.mp4` | 310.00–317.50 | 1 |
| 10 | 164.50 | `out/demo-video/paid-robot4/raw/raw.mp4` | 207.00–214.50 | 1 |
| 11 | 172.00 | `out/demo-video/showcase-01/raw.mp4` | 410.00–422.00 | 1 |

## 来源说明

- paid-robot4/raw：唯一一次付费 DeepSeek Harness 会话；robot4 矢量 PDF 读图，FreeCAD 原生建模。原片及会话用量、工具回执、独立图纸审计、重开结果一起保留。
- showcase-01：本次生成模型的工作副本；特征树点击、真实鼠标旋转、另存工作修订、Agent 配置/引导、减速器已有结果与 CI JSON 文件查看。
- manual-02：独立 FreeCAD Qt 窗口连续采集，以 Qt 输入事件操作实际 Pad 参数编辑器，4→5 mm，保存副本。Qt 全窗抓取不能可靠包含 OpenGL 视口，因此只采用真实参数编辑器特写，没有补造模型图像。
- showcase-02：重新打开手改后副本；厚度 5 mm 的实际只读检查见 manual-check.jsonl。它是修改练习，不是对原图 4 mm 的符合性声明。
- preflight-03：真实凸台模型的确定性 MCP 检查与修正，明确标为尺寸检查示例，不说成 Agent 自主纠错。
- reducer-viewport：FreeCAD 运行中持续采集真实视口；实际导入同修订 reducer_assembly.step，记录每帧时间，缓慢旋转，不生成或替换几何；110 个实体。不是工作台内 STEP 预览功能的演示。
- 减速器来源：out/desktop-validation/1793769105330/传动设计，修订 6f2c35f49d77；三维 STEP、二维 PDF、report.md/report.docx 均来自此修订。操作发生在复制工程。reducer-01 展示将工作拉力从 2500 改为 2600 并计算后真实出现的过期状态。documents-01 展示恢复 2500 后的当前成果 PDF。
- CI 工件原始 result.json：ci-41822011858/installer/result.json，ok=true。影片中的表格来自产品真实 JSON 查看器对该原文件的渲染（ok 显示为“通过：是”）。GitHub run 41822011858 / 41ec469，详情见 handoff.md。
- 图纸：用户已明确批准 robot4 出镜；源 PDF 不提交 Git，不扩展到其他学生资料。
- 声音：Microsoft Edge zh-CN-XiaoxiaoNeural，逐句使用原始时间边界，剪入停顿而非强行变速；旁白另附 narration.txt。没有配乐。
- 字体：项目 Noto Sans SC，OFL；没有使用第三方演示片的图像、声音或音乐。

## 原片校验

- `out/demo-video/documents-01/raw.mp4` SHA256：`14c842b0b9074bdac0a8e09989171cf8e96a7c4e36b9dcea66250f370f8d4e3e`
- `out/demo-video/manual-02/raw.mp4` SHA256：`632beee338c88404b6f2c579a16768b54f8ca39a6a514117bf119bf5f15fb710`
- `out/demo-video/paid-robot4/raw/raw.mp4` SHA256：`f24ce826592d7223f88547ea27e2da2814c36ccb9ceb05ef585287905ffc88fc`
- `out/demo-video/preflight-03/raw.mp4` SHA256：`99e71b3ecbc4772cad467371d8e15e1677e59cf97c2137cc18d1ff5947d97a04`
- `out/demo-video/reducer-01/raw.mp4` SHA256：`f50609839f28dbc85332edb4536dd481f51af5992c0c8474ff312a50d1ac52bf`
- `out/demo-video/reducer-viewport/raw.mp4` SHA256：`9e675f6134f01372be84bb41ab3afa57c6b8405770992b61bccfd123bbce9978`
- `out/demo-video/showcase-01/raw.mp4` SHA256：`f738973d8455bf38f7a92a6620bd99746065338a1c60d6671b6a5a48650cb1de`
- `out/demo-video/showcase-02/raw.mp4` SHA256：`a1e581b913901c5065207896e5c79833c0596ee863cc6b142b03f8ec551b8c32`

# 最终制作决定与交付（2026-11-04）

本节覆盖下方历史暂停状态。用户授权不再询问视频取舍，不再付费运行 dsh；后端减速器计算和示例保留。本轮只做只读会话回放与本地录制，没有新 dsh 会话。

## 第二次运行检查缺陷

**应用检查未发现截面积偏差 777.5 vs 828.5 mm²。** 会话 b7fd234f-7d1d-4c04-80a7-7a2e86bc3c4d 中，Agent 调用的 host.check 包含 7 项，全部 pass；mid_section_area 的 expected 与 actual 均为 0.0007775 m²。期望值取自错误模型自身面积，缺少独立图纸依据，应用没有拦下这个自证循环。独立审计使用 0.0008285 m² 才报 fail，不能把独立审计的发现包装成 Agent 自检发现。

这是待另行修复的产品缺陷，本次未改检查语义或重跑模型。依据：paid-robot4-02/robot4-1/result.json → audit.agent_self_checks 和 audit.independent_check；精简摘录 final/check-investigation.json。最终检查镜头采用真实、确定性的凸台尺寸检查/定位示例，持续标明“尺寸检查示例 · 确定性工具操作”，旁白不暗示能发现第二次轮廓错误。

## 首次成功会话只读回放

来源 paid-robot4/robot4-1/conversation.json，71 个事件全部原文、原序进入新版 Agent 面板，包含原来的资源枚举失败。原始 text/rawInput/rawOutput 不改；旧版用户输入中的完整 62k 参考文本放进新版已有折叠区域，displayText 仅取 modeling-prompt.txt 的完整原文前缀。project 元数据只改变当前独立播放工程路由。源事件与回放事件逐项相等，校验见 final-main-03/replay-integrity.json。

仅工具脚本 record-final.cjs 在自有 Electron 进程替换 ACP 接收通道；所有 Agent 执行 IPC 拒绝调用，不添加产品入口。旁边模型为首次实际保存的 robot4.FCStd，不按回放进度重建几何。原任务 210.421 秒，事件回放 40.004 秒，成片全程标“真实会话回放 · 总时长压缩约 ×5.3”；存档没有逐 ACP 事件时间戳，因此按原序分配停留时间，不声称恢复原来的逐事件延迟。

## 最终交付

out/demo-video/final/：film.mp4（163 秒，1920×1080，30 fps，H.264/AAC）、film.srt、narration.txt、sources.md/json、source-integrity.json、validation.json、check-investigation.json、qa/。无减速器镜头、预置工程、绝对路径或原始调试 JSON。无系统录屏权限：开场用独立 Electron 原生 PDF 阅读器和已有真实 FreeCAD 参数窗口连续素材；没有截图冒充录屏。素材只在明确的镜头中切换，robot4 工程没有无关文件。

验证：完整 MP4 解码与规格通过，71 个事件与源记录逐项一致，展示模型与首次保存模型 SHA256 一致；每镜两帧目视检查，另对 163 张每秒抽帧做 OCR 扫描，未命中绝对路径、减速器/课程设计、mcp__、工程清单文件名或原始 source JSON。OCR 只是辅助，不声称完成逐帧 OCR。

尚不理想：中文神经配音尚非真人；FreeCAD 参数编辑采用局部窗口素材；会话为明确标注的历史回放；新版 Windows 安装验收尚未重跑，影片标明历史 CI 41ec469 与本版 macOS 验收的区别。检查依据独立性缺陷保留待修。

---

# 当前修订：空工程与通用工作台（2026-11-04）

本节优先于下方历史。用户已批准第二次且仅一次 robot4 dsh 运行；此前“未批准”已失效。2026-11-04 13:23 UTC 开始前核对 dsh 0.2.1-rc.5，deepseek-official/deepseek-flash（DeepSeek-V4.1-Flash-1017），reasoning=low，矢量 PDF；单会话、发送后最多 480 秒、无并行和自动重试，失败保留原片停止。

当时打开核对 https://api-docs.deepseek.com/quick_start/pricing/ ：每百万 token 非高峰缓存命中 $0.003、未命中 $0.15、输出 $0.60；高峰翻倍。本次处于非高峰，按首轮使用量估算约 $0.04，并非费用硬上限。独立目录 out/demo-video/paid-robot4-02，已存在则拒绝运行。

桌面已彻底删除减速器界面，所有新工程 task=null/results=[]；后端保留。两种宽度 1366×768、1920×1080 的 desktop-flow 与 workflow-flow 均已使用新打包应用和全新用户目录通过。后续视频删除旧第 8 镜；历史影片不作为本轮交付。

## 第二次运行结果：停止制作

会话 b7fd234f-7d1d-4c04-80a7-7a2e86bc3c4d，发送后 464.542 秒正常 end_turn（未触及 480 秒上限）；含免费独立审计总计 486.571 秒。原生建模、保存和重开完成，但独立图纸检查失败：外形 45×27×4 mm 正确，截面积实际 777.5 mm²、参考 828.5 mm²，体积少 204 mm³，轮廓拓扑检查不符。不能作为成功读图建模片段交付。没有重试，没有第三次会话。

DSH 上报实际 usage：未缓存输入 141339、缓存读取 1159680、输出 85600、总计 1386619 tokens。按运行前官方非高峰价格估算 $0.07604（高于约 $0.04 的预估），不是账户实际扣款。原始 dsh-session.jsonl、result.json、独立审计、模型、连续帧与 raw.mp4 保存在 out/demo-video/paid-robot4-02；STOPPED.json 汇总停止原因和用量。

按用户“失败就停”约束停止后续正式剪辑和重录。分镜与剪辑计划已删除第 8 镜，预计 163 秒；尚未生成新版完整成片，旧 film.mp4 仍是历史版本，不能当成此次交付。仅完成产品测试、证据归档与提交收尾。失败原片 raw/raw.mp4 为 485.23 秒、1920×1080、30fps、H.264，共保留 13734 个真实原始帧；此时长含连接与免费审计，不等于付费推理时间。最终产品验收清单与截图目录见 [empty-workbench.md](empty-workbench.md)。

---

# 正式制作交接

## 本轮逐帧反馈修订状态（2026-11-04，优先于下方首轮历史）

产品修复、测试与免费修改片段见 [revision-review.md](revision-review.md)。第二次付费运行未批准、未执行；预计同首轮用量约 923k tokens，按今日官方价格约 $0.04 非高峰 / $0.08 高峰，非保证上限。新的 89 秒审阅片位于 out/demo-video/revision-review，旧完整成片保留。独立应用开场被 macOS 屏幕录制权限 -3801 阻挡，已请求用户开启；尚未录成。Windows 历史 CI 41ec469 不含本轮产品改动，勿误称同源码验收。

## 授权与范围（2026-11-04）

用户已审阅分镜与样片，批准正式制作；批准一次 robot4 付费 dsh 会话，从发送任务起最长 480 秒，不并行、不自动重试，失败保存原片并停止汇报。允许图纸进入视频，不提交 samples。可直接启动独立 Electron / FreeCAD / dsh，只结束本次拥有的 PID。分支 codex/demo-video，基线 f777ae0；不触碰 packaging-audit。

## 付费运行前记录

记录时间：2026-11-04 12:00 UTC。客户端 dsh 0.2.1-rc.5。提供商 deepseek-official，模型 ID deepseek-flash，官方当时对应 DeepSeek-V4.1-Flash-1017；reasoning=low，矢量 PDF 输入，robot4 一例、一次会话。

价格来源：[DeepSeek 官方定价](https://api-docs.deepseek.com/quick_start/pricing/)，本轮已实际打开核对。每百万 token 美元：非高峰缓存命中 0.003、未命中 0.15、输出 0.60；高峰分别 0.006、0.30、1.20。官方高峰为工作日 UTC 01–04、06–10（中国公休除外），本次开始时为非高峰。最终记录实际 usage；按价计算只称估算，不冒充账户实际扣款。

入口：tools/demo-video/run_paid.py。输出目录 out/demo-video/paid-robot4；目录已存在即拒绝运行，避免自动重试。原测试与提示词不修改，录屏包装只记录真实页面帧与指针事件。独立验收包含模型几何及保存后重开。

## 当前已验证

- 免费真实录屏预检 preflight-03 成功，17.54 秒、903 帧；真实 FreeCAD 建模、尺寸检查与修正，独立进程已关闭。
- GitHub run [41822011858](https://github.com/Strangelight-Merser/gongke-workbench/actions/runs/41822011858) 的 windows-installer-validation-41ec469561a281fd40313dbaf2a0eeff8fd3b89a 工件已下载；installer/result.json 的 ok=true。中文账户“学生验收”、中文安装目录；真实安装后服务、FreeCAD、原生建模保存与退出验证通过。
- 工件 ID 13318716957；GitHub digest sha256:3a9df964c9e5eccca691ccc88cc170d7b6fae10831e439587ceebb9adcf12b31。
- CI 提交 41ec469 是基线 f777ae0 的后代，只差 adapters/solidworks/tests/Program.cs 两行测试变量改名，产品源码一致；不声称是完全相同的提交。

## 制作约束

正式片使用连续真实录屏；个别静态证据单独标识。长建模明确标加速倍率。WorkBuddy 不展示，使用 DeepSeek Harness。字幕避开操作区；配音随实际动作重新对齐。旧 style-preview.mp4 是截图风格参考，不能充当正式片。

研究中的限制仍保留：国内获奖视频归属未完整核实，参考声音未连续听审。原始素材与大文件保留 out/demo-video，脚本/文档提交。

## 运行后记录

唯一会话 9c2e1634-ea8a-4dd1-9f5a-f3af6be4d0bc：210.421 秒，passed；图纸独立核验通过，保存重开 verified=true，45×27×4 mm、3314 mm³、一个有效实体。未重试、未追加付费会话。

DSH 原始 assistant/message 共 10 条 usage：inputTokens=84285，cacheReadTokens=799744，cacheWriteTokens=0，outputTokens=39210，totalTokens=923239；原始 dsh-session.jsonl 与 result.json 保存在 paid-robot4/robot4-1。注意 ACP used 是上下文占用，不能累计当账单。DSH 上报的未缓存输入与缓存读取分开，按运行前非高峰价格估算约 $0.03857；账户实际扣款未提供，仍未知。

会话中一次资源枚举工具失败，后续工程工具正常完成，最终独立验收通过；不抹去该日志。录屏和所有实际工具回执均保存。


## 正式片交付

- `out/demo-video/film.mp4`：184 秒，1920×1080，30 fps，H.264 / AAC，神经中文旁白，烧录字幕；无配乐。
- 同目录：film.srt、narration.txt、sources.md、sources.json、timeline.json、validation.json、source-integrity.json；qa/ 每镜至少一张从最终 MP4 抽出的检查图。
- 完整 MP4 解码、音视频流规格、11 镜抽帧验证通过。字幕在画面外，不覆盖工程操作区；×2 加速段显式标注。逐句插入停顿配合操作，不靠统一加快配音。
- 原件与第一次工作副本 SHA256 一致，说明原始 robot4.FCStd 未被参数练习覆盖；CI 展示 JSON 与下载的原始 result.json 字节一致。
- 产品源码与测试原件无改动；仅新增 docs/demo-video、tools/demo-video。没有提交 samples、媒体或输出目录。独立 GUI/Agent 进程已关闭，未按名称清理其他进程。

## 尚不理想的地方

1. FreeCAD 的 Qt 全窗抓取不能可靠取得 OpenGL 模型区域，因此参数编辑使用真实编辑器特写，减速器三维使用 FreeCAD 自己的连续视口采集；没有拼贴伪造全窗。
2. 减速器说明书镜头采用产品现有 Markdown 文本预览，视觉表现比图纸和三维朴素。工作台直接 STEP 文件预览未跑通，影片明确标注 FreeCAD 视口，不把它说成已实现的文件预览。
3. 配音为中文神经语音；没有完成逐字人工听审。已保留逐镜音频、旁白全文与字幕，便于真人重录。
4. 这次是真实单例，不宣传普遍成功率或平均提速；原始会话内资源枚举失败也保留在证据中。

## final-v2 画面打磨

- 输出独立目录 out/demo-video/final-v2/，原 final 保留。
- 开场 12 秒：pdftoppm 渲染获准出镜的 robot4 原 PDF，配合新录制的真实 CAD 截图，左右交替聚焦。角标“示意动画 · 真实图纸与 CAD 截图”。不复用学生手改原片。
- 回放改为正常工作台布局，沿真实界面推近工具调用、拉回模型。首次会话 71 个原始事件完整、原序、原文，失败保留；40.003 秒回放 / 原任务 210.421 秒，标注约 ×5.3。
- 用户请求的默认单行折叠属于产品显示改动，展开可读原文；未删改 prompt 或参考文本。两种宽度（1366/1920）真实 Electron 测试验证单行省略、默认折叠、展开全文一致及再次收起，证据 v2-request-review/result.json。
- 交付证据页去掉小截图，保留大字要点；Windows 历史 CI 41822011858 / 41ec469 与 macOS 本地打包流程分开标注。本轮 UI 显示改动完成 build / 68 项测试通过、1 项 Windows 专属跳过；不冒称重新完成 Windows 或打包验收。
- 所有旁白、字幕时间和凸台示例段保持不变。不增加费用，不执行 dsh。第二次模型轮廓漏检缺陷仍按前文记录。
- 原片 v2-main-01 为显示断言放错事件位置后的中止录制，仅留排查，不进入成片；有效新原片为 v2-main-02。按事件 type=user 检查请求，已验证全文一致。
- 剩余边界：开场是明确标注的示意动画；回放仍展示该次实际结果模型，不声称逐步重建。Windows 证据仍为历史版本，未升级其验收结论。

最终 v2 验证：163 秒、1920×1080、30fps、H.264/AAC，全片解码通过；20 张逐镜抽帧、163 张逐秒抽帧及第 50 秒原尺寸图。OCR 未命中路径、减速器或原始工具字段；71 条回放事件一致，跨镜头无同原片区间复用。旁白/SRT 字节一致，凸台镜头剪辑配置一致，原 final/film.mp4 哈希不变。证据见 final-v2/validation.json、source-integrity.json、revision-checks.json 与 qa/。

## final-v3：仅避开图纸水印

用户要求图纸尺寸、线条不改，其他画面不变。采用优先裁切方案：原 2400×1698 栅格图只取 [240,42,1080,424]，展示主视图上部及 45、17、5 等尺寸，避开水印与下部视图重叠处；没有白块遮盖，没有重绘或修改图纸，原 PDF/PNG 不变。开场全部 12 秒使用相同裁切。其余九镜已核对，模型工作台上的 robot4.pdf 只是未打开的标签，没有其他 PDF 页面出镜。旁白、SRT、镜头长度和第2至10镜配置与 v2 一致。

交付目录 out/demo-video/final-v3/；复现用 timeline-v3.json，其余环境和命令同 v2。生成后运行 verify_v3.py，记录逐镜页面复核与范围一致性。v2 不覆盖。

v3 核验：163秒、1080p/30fps、H.264/AAC，完整解码与来源校验通过；20张逐镜抽帧、逐秒抽帧及第50秒原尺寸图。旁白/SRT与v2字节一致，AAC音频流SHA256也一致；原v2成片哈希不变。逐镜页面复核见 final-v3/revision-checks.json，裁切说明已写入来源清单。

## 2026-11-04：按大纲 v2 完全重做，停在样片审阅

本轮交付 `out/demo-video/rebuild/samples/opening.mp4`（12 秒）、`growth.mp4`（13 秒）、`styleboard.png`。都是 1080p60，暂不配音、不放配乐。来源与逐秒抽帧同目录，旧 final/v2/v3 不覆盖。后续以 `docs/demo-video/remake-samples.md` 为准，其中逐条对应大纲第一部分 13 项验收标准。

已合入独立检查 fe402fa（merge 05485f6），补齐图纸与模型同边定位并通过真实错误模型的界面验收。产品提交 5ecb83a。Python 862 项通过（不含 geometry/fem），桌面构建与 70 项测试通过、1 项跳过。Logo/平台图标独立提交 48e0c5f；macOS 包内图标哈希已核对。没有付费，没有调用 dsh。

第 5 段实际经 MCP 重执行首次成功会话的 10 次工程调用，原几何/尺寸/操作 ID/条件保持不变，只重绑定新宿主及文档运行时身份。正式录屏用 `growth-03`，前两次仅为取景与品牌色试录；原始记录与新回执均保留。没有把预存结果注入界面。

第 6 段的事实依据已具备：第二次 robot4 模型的两条斜边核验为 fail，图纸源为 lines/73 与 lines/101，对应真实原生边。第 7 段 GUI 修正、复查通过、保存重开还未制作。按用户明确流程，到两支样片与风格板即停止，等待审阅后才做全片。

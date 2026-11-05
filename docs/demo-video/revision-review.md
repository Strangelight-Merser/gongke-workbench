# 逐帧反馈修订（2026-11-04）

产品修复提交：`28a5c6e`。当前停在第二次付费运行前。未执行新的 dsh 会话。原 `out/demo-video/film.mp4` 保留为第一次交付，不是本轮已修完的新版。

## 产品修复与证据

- 工具命名统一使用 `desktop/src/agent/modelingSteps.ts`：人工操作的 ModelingTimeline、Agent 工具卡和权限确认共用 `stepTitle`。规范化 dsh 的 `mcp__gongke__` 前缀和 12 位哈希后缀，覆盖本次 robot4 用到的全部动作，包括 hosts.list；显示绘制草图、拉伸尺寸、读取图纸、核对图纸尺寸等。
- 图纸参考 JSON 原来由 preparePrompt 拼入用户请求，客户端将完整请求直接展示。现在完整 text 仍保留在审计事件和实际 ACP 请求中，另传 displayText；参考原文默认折叠，不丢弃模型输入。工具参数与回执仍默认折叠。
- 每轮请求中的思考片段合并到一个折叠项，不再在工具之间重复占行。新的用户请求开始新的思考组；真实失败不被成功分组吞掉。
- 文档栏的 FreeCAD 路径按工程根目录转为相对路径；工程外文档仅显示文件名。Windows 盘符、反斜杠、大小写与相似前缀都有测试。读写使用的原始路径不变。

`list_mcp_resources` 根因是**我方 dsh 策略误拦截**，不是 MCP resources 未实现，也不是可忽略的无害红字：

- 原始事件 `paid-robot4/robot4-1/user/agent-events.jsonl`，toolCallId `call_01_HcoYgib6QJBS55ZmvaAl4792`，返回 `Error: 工程操作只能通过构想引擎 MCP 执行`。
- `desktop/electron/acp/deepseek-policy.cts` 之前仅允许 `mcp__gongke__` 名称；dsh 内置目录枚举没有这个前缀。
- 已只放行只读 `list_mcp_resources`，继续尊重上游 deny/cancel/ask。任意资源读取、shell、文件工具和未实现的模板枚举仍不放行。工程工具仍走原来的授权。
- 真实 stdio MCP 测试确认 resources/list 返回 gongke://modeling 与 gongke://drawing-input，二者 resources/read 正常。旧会话失败日志保留，新运行是否正常仍需下一次真实 dsh 验证。

## 验证

- `cd desktop && npm run build`：通过。
- `GONGKE_PYTHON=/private/tmp/gongke-modeling-venv/bin/python npm test`：70 项，69 通过、1 跳过（macOS 不运行 Windows cmd.exe 测试）、0 失败。首次未指定该环境时，默认 Python 缺少项目服务依赖，3 个服务测试退出；指定已有工程环境后通过。
- `/private/tmp/gongke-modeling-venv/bin/python -m pytest tests/test_mcp_resource_listing.py -q`：1 通过，真实服务/官方 MCP SDK，无模型。
- `node desktop/tests/agent-revision-review.cjs out/demo-video/revision-product-qa`：通过；验证中文标题、原文默认折叠/可展开、每轮仅一个思考项、真实失败保留。该 UI 测试使用确定性夹具，输出明确标为 fixture-not-film，**未用于成片**。
- 新检查录屏 revision-check-02：真实 FreeCAD、真实工具操作，尺寸不符与修正过程；不伪称 Agent 自主纠错。无注册充值引导。
- 新说明书：原 report.docx 经独立 LibreOffice profile 转 PDF，21 页；检查第 2 页公式/表格，录制实际工作台 PDF 浏览与放大。

## 审阅片与原片

`out/demo-video/revision-review/film.mp4`：89 秒，1080p30、H.264/AAC；SRT、旁白、逐段 sources.json/md、validation.json、10 张编码后抽帧在同目录。只汇集第 4、5、6、8、9 镜的修改片段，不是最终完整成片。

- revision-model-01：打开第一轮成功模型的副本，查看 Profile/Plate、旋转、另存工作修订；新的相对路径已现场可见。第 4 镜旁白改为实际存在的轮廓草图与拉伸特征，不再宣称展示约束生成。
- revision-check-02：展开实际不符回执，显示要求、定位入口与模型标红，再修正。
- revision-ui-02：新的空工程录制连接配置/安装引导，无 windows-installer-result.json 标签；随后导入渲染后的 report.pdf，清理无关标签及底部面板后录制。
- 第 8 镜保留已有计算/三维/出图/过期状态真实原片，说明书替换为 PDF；推近计算区和报告表格。减速器三维仍为 FreeCAD 原生视口。
- 字幕在内容框外，逐句原速配音；没有音乐。正式总片仍需合并新的 Agent 片段并做全片检查。

## 尚未完成与停止边界

1. 独立应用开场：已准备 Preview、FreeCAD、LibreOffice 的自有进程窗口录屏脚本 `record-native.py` / `window-record.swift`。首次 ScreenCaptureKit 返回 -3801（macOS TCC 屏幕录制权限被拒），没有取得有效开场帧；自有 Preview 进程已结束。已向用户请求开启当前宿主的屏幕录制权限。没有绕过权限，也没有用工作台画面冒充独立软件。授权系统权限后用新的 --output 目录重录。
2. 新 Agent 面板录屏：第二次付费会话尚未批准，因此未运行。拟沿用 robot4、一次会话、最长 480 秒、不并行、不自动重试；失败保留原片并停止。付费前再次记录实际模型及当时价格；结束后记录实际 usage。
3. 预计用量参照首轮：非缓存输入约 84k、缓存读取约 800k、输出约 39k，总约 923k tokens。2026-11-04 再次打开 [官方定价](https://api-docs.deepseek.com/quick_start/pricing/)：deepseek-flash / DeepSeek-V4.1-Flash-1017，每百万美元非高峰为 0.003/0.15/0.60（缓存命中/未命中/输出），高峰翻倍。相同用量估算 **$0.039 非高峰 / $0.077 高峰**，可简记 $0.04–0.08；不是费用上限，实际推理长度与缓存命中可能变化。
4. Windows CI run 41822011858 的 ok=true 仍是 41ec469 的历史安装验收。本轮产品修复后不能再称其与当前产品源码完全一致；新改动已做上述本地测试，尚未取得新版 Windows 安装 CI。

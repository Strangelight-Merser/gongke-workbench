# 第八轮：余额恢复后的真实建模试验

沿用独立 FreeCAD、Electron、应用服务、dsh ACP、绑定工程 MCP。所有运行均传 `--background`；没有使用系统鼠标/键盘、激活窗口或操作 7658 / workbuddy-2026。关闭由各试验自己的退出标记完成，未按进程名批量杀进程。原图/PDF、摘录和截图仍只在 out/ 下。

每组先跑1次；新第4页首轮独立通过后，才追加一次同配置重复。P7 首轮出现约束重试后修复错误定位再复测；第13页因读图平面解释错误，补强引导后复测。off 仅做一次探索，发生参数 JSON 协议错误后不推广。

## 确定的改动

1. 第4页侧挡板新增 PDF case 和独立验收：外轮廓20边、左右箭头各7边、上下三角各3边，净截面828.5 mm²、厚4、体积3314 mm³、包围盒45×27×4。检查40条截面边和5个闭合环，不能用相同面积掩盖错位。坐标数值来自人工复核图纸标注/投影，审计数据不发送给 Agent。
2. 第13页 low 将左下圆头轮廓当作俯视，将孔轴放到Z，且省略底部凹口。模型自身10项检查全部通过，独立检查否决。PDF 引导补充识别每个视图页面位置、对应模型平面，不默认左上为主视图，不省略小尺寸后宣称完成。不向 Agent 注入13页尺寸答案或建模步骤。
3. 图片与检查的直接工具说明加入避免重复整图/同一像素裁图、同修订多条件合并检查。原来只有资源指南含这些说明，读图阶段未必会读取资源。P7读图提示也明确无法确认时填null，不用像素比例凑数字；不硬拦正常只读工具。
4. P7 多次失败后发现 FreeCAD 冲突/冗余编号为1基，而公开 constraints/geometry 使用0基；fixed点可展开两项、rectangle另有自动约束，仅用报错编号删请求项会删错。统一为0基，在成功/失败回执中添加 `constraint_sources`（input_index→native_indices）和 `constraint_index_base=0`，失败另列automatic_constraints。原生读检查也同步改为0基。此项为公开回执语义修正，不保留旧编号兼容路径。

第4项依据 [FreeCAD 官方 Draft 实现](https://github.com/FreeCAD/FreeCAD/blob/main/src/Mod/Draft/draftmake/make_sketch.py)，本机官方资源同样明确1基编号。真实预检新增 fixed 中心展开后重复半径的用例，验证报错索引能映射到正确输入、事务回滚后桥接仍可读写。

## 当前已完成样本

| out/目录后缀（agent-modeling-r8-） | 输入/模式 | 结果 | 秒 | Agent工程调用 |
|---|---|---|---:|---:|
| robot4-low | 第4页 / low | passed | 326.291 | 16 |
| robot4-low-repeat | 第4页 / low | passed | 185.962 | 12 |
| robot13-low | 第13页 / low | drawing_mismatch | 554.676 | 15 |
| robot13-off | 第13页 / off | run_failed，dsh工具参数JSON错误 | 31.429 | 8 |

第4页2/2通过，均值256.127秒；第二次比第一次短43.0%，但样本很小、工具说明也有改动，不能将差异单独归因于缓存或模型稳定提速。两次保存后的独立边界检查、重开验证均通过；截图实际查看后与源图外形一致。

第13页 low 的外包络恰好仍为18×20×20，但孔轴变成Z、孔中心高度0，底部截面错误。没有为了让结果通过而自动旋转配准；遗漏底部凹口也不能由配准修复。模型自己明确承认省略了细部，故不算正确完成。

off 的 ACP 原始错误 `-32603: Internal error: turn failed: DeepSeek Messages stream: tool input is invalid JSON`，发生于 Agent 工具调度层；日志和参数记录保留，不通过字符串修补JSON继续写工程。该组仅913个输出token，虽然快，但没有完整模型，不能计入建模加速成功。

low 已经真正传入 dsh 的 request/header.config.reasoningEffort，而非只改变界面显示；对应 header 默认maxTokens为256000。low 不保证短推理，第13页首轮88507输出token，P7读图也出现大量输出。

## 费用口径

dsh 持久化 assistant/message 用量分别累加未命中输入、输出、缓存读取；不把ACP上下文占用当作账单。按 [DeepSeek 官方价格](https://api-docs.deepseek.com/quick_start/pricing/) 2026-11-03页面，Flash非高峰每百万未命中输入/输出/缓存命中分别$0.15/$0.60/$0.003；本轮UTC14时处于非高峰。可据此估算模型token费用，不能称为账户实际扣款，也不把其他会话消费算在本轮；未记录的中止流或失败请求用量可能缺失。

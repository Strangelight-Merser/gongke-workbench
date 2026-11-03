# 第七轮真实链路验收

本轮使用 7115 worktree 的独立 FreeCAD、Electron、应用服务、dsh ACP 与绑定工程 MCP。`--background` 通过 macOS `open -g -j -n` 启动独立 CAD，Electron 隐藏且不激活、禁用后台节流；不使用系统鼠标、键盘或前台焦点，结束只关闭本试验实例。依据 [Electron BrowserWindow](https://www.electronjs.org/docs/latest/api/browser-window) 与本机 `open -h`。独立用户目录、宿主端点与工程继续隔离。

## 第六轮诊断

| 输入 | 结果 | 秒 | 工程工具调用 | 服务回执累计秒 |
|---|---|---:|---:|---:|
| P7 vision，第一个完整样本 | passed | 575.445 | 43 | 3.466 |
| P7 vision，另一次完整样本 | passed | 854.603 | 64 | 7.912 |
| P7 vision，用户中断 | modeling_failed | 550.841 | 26 | 0.139 |
| P6 dimensions 1 | review_required | 444.298 | 29 | 2.472 |
| P6 dimensions 2 | review_required | 302.676 | 23 | 2.027 |
| P6 vision 1 | run_failed（超时） | 1210.139 | 78 | 5.010 |
| P6 vision 2 | run_failed（发送前 UI 定位失败） | 7.708 | 0 | 0 |

统计来自原始 `result.json`、`tool-calls.jsonl`，派生表 `out/agent-modeling-dev/round7/historical-metrics.json`；原证据不改。服务累计秒不含模型推理、生成、网络和各轮间隙，不将余下时间全称为纯推理。

P7 两次未受外部中断的第六轮试验 2/2 通过，均值 715.024 秒；单独列出被杀宿主的失败，不纳入模型质量分母。第五轮 P7 dimensions 经离线 BREP 复核为正确，296.022 秒；第五轮 vision 不符，608.941 秒。因此第五至六轮 P7 图片质量样本为 2/3，工程运行中断另列。小样本不能证明稳定成功率。

P6 dimensions 两次构建、保存、重开均成功，但均不算图纸符合性通过。第一份体积 145060 mm³，采用全宽高平台和变高后壁；第二份体积 123793.333 mm³，采用斜坡与后壁，包围盒同为 80×52×52。相同尺寸台账仍产生不同空间解释。需确认：80/52/40/35/21 小字候选、裁掉的总高与落差（暂设52/40/12）、前平台宽/高、斜坡与后壁交界、左端是否开放。仅 15 mm 已人工复核；无单位、公差、材料的明确依据。检查通过仅说明符合各自假设，不能推出原图正确。

P6 vision 第一次读图 400.14 秒，36 次 `project.read_image`；将低清标注读成 80×45×45、内落差30等，并用像素比例增强判断。建模阶段一度将 80 mm 直接传为 80 m，后续约束修正；又发现后壁前后颠倒，删除 8 项后重建。总预算耗尽时最新修订未保存、未完成最终检查。桥接仍响应，属于读图不确定性、单位/空间解释错误与重做叠加，非宿主挂死。

第二次在 `drawing` 阶段选择“打开图纸”时，工具栏和开始页各匹配一个按钮，Playwright 严格定位报错；尚无模型请求。日志不能证明用户切前台是原因。现定位到“工程命令”工具栏的唯一按钮；后台真实 PDF 运行已经通过此入口。

## 减少耗时的实质改动

854 秒 P7 的分布：读图12、草图17、特征13、删特征5、measure6、check3、inspect2，其余6。真实宿主服务仅约8秒。优先减少模型往返和重试，不能靠加速 FreeCAD 算法解决14分钟。

- 修复顺时针圆弧端点映射；原失败调用纳入真实回归，避免把宿主契约错误归咎于模型。
- 一次提交完整草图/必要约束；rectangle 自带水平竖直重合，不重复添加；追加无几何时显式空数组。修订与未知写入读回仍保留。
- 回传求解后几何以提前发现漂移。单位、基准面法向和贯通切除说明更明确。尺寸修改优先 feature_edit，避免整树重建。
- 一个 inspect 获取面引用，多条件合并一次 check；解释 near 语义，减少逐个 measure 探针。保存只在最终修订自查后进行。
- 图片局部复读用于真正模糊处；重复放大不产生新证据，缺失标注留待复核。
- 新增 `--reasoning high|low|off`，通过 ACP session/set_config_option 选定并记录。low 为本轮速度实验，不改学生的全局默认配置。不得只凭速度判定质量。

## 新材料及独立验收范围

原文件位于 `samples/student-materials/quadruped-robot-drawings.pdf`，选原第14、13页。单页摘录只存 out；Agent 收到 `project.read_drawing` 的文字/矢量结果和明确坐标约定（第14页凸柱沿+Z，第13页主视轮廓置于XZ），无图片、无尺寸答案、无建模步骤。教程 PDF 实际为一页通用建模流程图，可作选平面/特征顺序参考，不是这些零件的逐步答案。

第14页：23×18×3 平板，四角3×45°，Ø6凸柱高4、距右边6、竖向居中。独立验收外包络、圆柱朝向/位置/直径、两个截面面积及解析体积1301.0973355 mm³，另验证原生树、最终自查、保存、独立重开和截图。

第13页：18×20底座、双耳R5、两孔Ø5，孔中心高15。独立验收外包络、圆柱数量/方向/直径/高度及底部截面；底部1/1.5/14凹口的端距与耳部切线连接保留具体复核项，不能只凭外包络宣称全图通过。

## 本轮实际运行结果

| 试验目录（out/ 下） | 输入/推理 | 结果 | 秒 | 工程调用 |
|---|---|---|---:|---:|
| agent-modeling-r7-robot14-a | PDF 第14页 / high | passed，独立重开及截图复核通过 | 566.927 | 39 |
| agent-modeling-r7-robot13-low-c | PDF 第13页 / low | API 余额耗尽，中断于首个草图后 | 296.561 | 6 |
| agent-modeling-r7-p7-low-b | P7 图片 / low | API 余额耗尽，中断于读图阶段 | 219.084 | 12 |

第14页 Agent 最终合并11项自查均通过，保存后体积1301.0973355292326 mm³、包围盒23×18×7、有效单实体；两个草图、两个 Pad。独立重开截图 `robot14-1/model-reopened.png` 已实际查看，外形和凸柱/四角符合图纸。最初欠约束漂移、倒角翻向、near 选择器不匹配均由 Agent 自查后修正；这次结果触发了前述回执和说明改进，不能把这些改进倒算为首轮已有能力。

第13页进入了原生草图工具；新回执已明确显示其欠约束轮廓发生平移。尚未等到模型修正或建立实体就收到余额错误。P7 在11次图片局部读取后被同类错误中断，未发出建模任务。二者的 ACP 错误均为 `-32603`，原始消息 `Internal error: turn failed: Insufficient Balance`；provider request_id 分别为 `a090af24-1461-4caf-89b2-72592cdaf3a3` 和 `53bfc019-ba79-459c-ae3b-2131f8aa434b`。完整错误、stderr、持久化会话和工具回执均在各目录。未充值、未切换账户或读取密钥。后续批次遇到此明确错误会停止尚未运行的 case，未运行不计入建模失败分母。

因此新 PDF 计划2件，已通过1件、外部阻塞1件；完整质量样本1/1，按计划完成率1/2，不能声称2件均跑通。P7本轮没有新的质量样本，**尚无证据证明单次14分钟已显著缩短**；low 模式在中断前仍产生大量输出，不能把切换配置当作提速结论。恢复余额后需重跑第13页和P7，并用相同图纸/模型比较耗时、调用数、独立符合性，而不是拿更简单零件的567秒作P7速度对照。

真实 dsh assistant/message 用量累计（含缓存，不等于单次上下文占用）：

| 试验 | 非缓存输入 | 输出 | 缓存读取 | 总 token |
|---|---:|---:|---:|---:|
| robot14 high | 102807 | 84908 | 4137472 | 4325187 |
| robot13 low（中断） | 55870 | 45327 | 206464 | 307661 |
| P7 low（中断） | 8398 | 30603 | 156416 | 195417 |

金额未由持久化用量报告，不推算费用。派生汇总 `out/agent-modeling-dev/round7/live-metrics.json`。

无模型消费的预检尝试 `robot13-low`、`p7-low`、`robot13-low-b` 均因回归用例还含冗余约束被拦住。原请求保留，修正预期并增加删掉冗余关系的工作副本后，`robot13-low-c` 与 `p7-low-b` 的10项真实宿主回归全部通过；不把这些预检失败混进模型成功率。

## 继续运行

处理已有 DeepSeek API 账户余额后，在本 worktree 执行（脚本自行后台启动，无需屏幕操作）：

```sh
/private/tmp/gongke-modeling-venv/bin/python scripts/agent_modeling_trial.py --cases robot13 --delivery pdf --background --reasoning low
/private/tmp/gongke-modeling-venv/bin/python scripts/agent_modeling_trial.py --cases p7 --delivery vision --background --reasoning low
```

默认输出按时间命名，不覆盖既有证据。若要估计稳定性，给同一命令追加 `--repeats 2`；每轮独立宿主/工程。不要并发执行同一 worktree 的构建步骤。

## 验证与交付

最终相关 Python 测试74项通过；桌面测试53项通过、1项跳过；桌面生产构建通过。日志分别为 `out/agent-modeling-dev/round7/{python-final,desktop-final,final-build}.log`。两次实际10项 FreeCAD 预检通过，涵盖原固定约束故障、错误后的桥接可用性、顺时针圆弧原始请求及去冗余后的拉伸。协议替身和宿主脚本回归不计入模型自主建模样本。

原图、PDF、摘录、渲染、FCStd、会话及日志均未加入仓库。分支 `codex/agent-modeling-live-validation` 收拢本 worktree 前几轮未提交的相关实现与本轮修改，不 push、不合并。

**建议作为下一个扩展，先做“学生建模后的讲解与自查”。** 已完成读图、两件建模、错误变体检查和联网调研。

[完整报告与复现入口](/Users/huaiyi/.codex/worktrees/f2ba/gongke-workbench/out/drawing-to-model-study/README.md) · [模型视图](/Users/huaiyi/.codex/worktrees/f2ba/gongke-workbench/out/drawing-to-model-study/results/reference_views.png)

**做了什么：**8件试读，2件参考体，6种错误变体、1种缺尺寸敏感性试验。脚本、STEP、结构化尺寸和日志全部留在已忽略的 `out/drawing-to-model-study/`。无提交、无正式代码变更；原图未复制进仓库，hash未变。

**实际证据：**

| 参考体 | 包围盒 | 体积 |
|---|---|---|
| P7 长圆底座与立筒 | 52×20×20 mm | 7745.026283 mm³ |
| P8 带筋角支架 | 56×40×39 mm | 22296.424958 mm³ |

两件均为有效单实体，STEP回读的体积、包围盒、圆柱面和选定截面一致；P7另通过解析体积校核。

- **读图可用，但必须复核。** 能分出8件、对应典型视图，读出清晰的 `2-φ42`、`3-φ8`。实际发生了P7底厚“6？”→放大后8的纠正；P6疑读仍未解决。公差未获得有效样本，不能声称已验证。R标注数量也不等于三维圆角数量。
- **体积和包围盒不够。** P7槽错移1 mm，两者完全不变，读取槽端轴线才能定位；P8漏筋只少约3.52%体积，5%阈值会漏报。
- **参考体也有假设。** P7未单独标注的端部半径、P8相切关系已明确记录，不能据此自动扣分。

**重要取舍：**

现有接口可复用文档上下文、预览、选择和SOLIDWORKS部分参数读取；需新增通用只读的**特征/草图摘要、精确尺寸与孔轴、截面、逐项条件检查**。FreeCAD现有语义检查仍主要针对轴类。

最小版本就是：**选题块 → 确认关键条件 → 学生自行建模 → 定位不符并解释 → 修改后复查**。例如先让学生判断“20从哪个面量起”，再解释底厚8意味着筒上段增加12；不直接交付完整模型。

[Onshape CAD Challenges](https://www.onshape.com/de/blog/onshape-certified-associate-cad-exam)已有“自行建模后自动比较”的产品先例；[eDOCr](https://www.frontiersin.org/journals/manufacturing-technology/articles/10.3389/fmtec.2023.1154132/full)支持分区识读思路；[MechVQA](https://xiaofengshi.github.io/MechVQA/)则说明尺寸识别、跨视图推理和一致性判断需要分别评估，不能用OCR成绩代表整件恢复能力。

**仍缺的具体步骤：**

- 教师确认单位与未注尺寸，补充真实学生FCStd／SLDPRT验收。
- 完成原生读取：本次FreeCAD探针因Qt要求 `neon` 退出；SOLIDWORKS尚未在Windows运行。
- 暂不采用全形布尔差评分：P7同形STEP回读出现异常布尔差，失败日志已保留。
- 产品上只需决定两点：**先学生自查还是教师评分；提示允许展开到哪一级。**建议先学生自查，按需展开当前步骤，完整参考体留给教师或明确允许的练习模式。


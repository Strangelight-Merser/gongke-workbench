# 建模检查样本

逐字节复制原看图建模试验 `out/drawing-to-model-study/results/*.step`，SHA-256 见 manifest.json。未改写试验原件、脚本或输入图。

P7：参考体、φ12 错孔、槽错移 1 mm、漏槽、总高 28、端部 R9 假设。
P8：参考体、漏筋、漏一个底孔。

单位 mm 为原试验假定，不是已确认的图纸事实。P7 端部 R9 只是缺尺寸敏感性样本，不作为错误扣分。完整来源与假设见 `docs/research-drawing-to-model.md`。

原生运行入口：`tests/e2e/model_inspection_freecad.py`。截面筋检查使用解析面积：z=10 mm，竖板 40×8 + 筋 12×8 = 416 mm²；漏筋为 320 mm²。P7 槽右端轴线 x=14 mm，错移后15 mm。它们独立于总体积与包围盒。

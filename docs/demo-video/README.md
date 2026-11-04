
## 第二轮画面打磨（final-v2）

保留 final，不覆盖。沿用 voice-final 的全部旁白和句子入点，第 6 镜凸台检查不变。
新录制用正常工作台布局；用户请求在产品中默认单行折叠，可展开全文。
开场是实际 robot4.pdf 与 CAD 截图组成的示意动画，明确标注；第 9 镜仅显示验收要点。
同一原片的时间区间不得跨镜头复用，validate_film.py 会检查。

```sh
npm --prefix desktop run build
GONGKE_PYTHON=/private/tmp/gongke-modeling-venv/bin/python npm --prefix desktop test
node desktop/tests/agent-request-review.cjs out/demo-video/v2-request-review
# 录制目标应为尚不存在的目录；固定目录与 timeline-v2.json 一致。
node tools/demo-video/record-final.cjs out/demo-video/v2-main-02
mkdir -p out/demo-video/v2-assets
pdftoppm -scale-to 2400 -png -singlefile out/demo-video/paid-robot4/inputs/robot4.pdf out/demo-video/v2-assets/robot4
/private/tmp/gongke-demo-video-venv/bin/python tools/demo-video/encode_recording.py out/demo-video/v2-main-02
python3 tools/demo-video/plan_v2.py
GONGKE_DEMO_OUTPUT=out/demo-video/final-v2 GONGKE_DEMO_VOICE=out/demo-video/voice-final GONGKE_DEMO_PLAN=tools/demo-video/timeline-v2.json /private/tmp/gongke-demo-video-venv/bin/python tools/demo-video/render_film.py
GONGKE_DEMO_OUTPUT=out/demo-video/final-v2 GONGKE_DEMO_REPLAY=out/demo-video/v2-main-02 /private/tmp/gongke-demo-video-venv/bin/python tools/demo-video/validate_film.py
```

graphics.py 只生成影片外部的示意动画和证据页，不注入产品界面。
未新增模型生成、未调用 dsh。重新录制时不会执行原会话的工具调用。
模型是首次成功会话的结果，并非按回放时序重新建模。

## 第三轮：避开图纸水印

使用 timeline-v3.json，输出环境变量改为 out/demo-video/final-v3；其余生成、验证命令与 v2 相同。
开场图纸仅裁到原始栅格图比例 [0.10, 0.025, 0.45, 0.25] 的主视图上部与尺寸区域，避开斜向水印，不做遮盖或重绘。原始 PDF / PNG 保持不变。其余九镜、字幕和声音沿用 v2。

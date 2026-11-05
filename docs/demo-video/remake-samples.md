# 大纲 v2：开场与建模样片

本轮只制作第 1、5 段各一支样片和风格板，停在视觉审阅点。采用 1920×1080、60 fps、H.264；暂不配音、不放配乐。旧 final-v3 不覆盖。全片、真实 GUI 修正与复查通过段均未制作。

输出：`out/demo-video/rebuild/samples/`。

- `opening.mp4`：12 秒。完整 robot4 正视图轮廓逐笔绘制、原图尺寸亮起、转成立体模型、品牌落版。矢量坐标及尺寸来自产品读图结果；立体网格来自本轮真实 FreeCAD 的 `freecad.scene`。动画只作片头视觉表达，不作建模过程证据。不含原图水印，也未涂改原始图纸。
- `growth.mp4`：13 秒。从真实新建零件后的空视图开始，保留一次草图调用和一次拉伸调用的前后变化、原生特征树和完成卡片。中间硬切省去一段静置；其余原速。单一角标“按真实会话重放”。没有伪造逐边绘制或约束生成。
- `styleboard.png`：思源黑体 88 / 48 / 30 px，强调色 `#24b69c`，墨黑 `#101918`、雾白 `#f3f5f4`。统一字幕、角标、0.7 秒缓动推近。

## 大纲第一部分逐项落实

| 项 | 样片落实与全片后续 |
|---|---|
| 1 无开头、主线、结尾 | 本轮完成品牌开场；全片固定“图纸→模型→检查→学生修正”，结尾按已定作品名与学院落版，审阅后制作。 |
| 2 两零件跳换 | 两支样片只用 robot4；全片第 6、7 段使用第二次错误模型与同一图纸，不再用凸台示例。 |
| 3 建模只有成品 | 新 FreeCAD 经 MCP 真实重执行原始 10 次工程调用；样片可见空视图→Profile→Plate。 |
| 4 验收页像工程报告 | 后续第 8 段只面向评委讲接入、原生模型、安装包；CI 详情放来源文档。此轮不制作验收页。 |
| 5 角标过多 | 建模样片只有一个真实重放角标，无重复免责声明。 |
| 6 小窗口、空白边框 | 连续录屏全幅裁切，界面填满画布；后半段推近特征树及完成卡片。 |
| 7 灰模型灰背景 | 产品控件统一青绿色阶，模型背景改浅渐变、实体提高明暗对比；普通选中边尊重遮挡，核验边保留前景高亮。 |
| 8 缺品牌、字体混乱 | 原创图纸+立体块 Logo、三档字体；已单独提交安装图标配置。 |
| 9 运镜生硬 | 同镜统一视窗，缓动只为看清特征树与工具完成状态；段内硬切。 |
| 10 字幕与大字重复 | 片头仅落版文字；建模段仅底部一句字幕，不叠重复大字。 |
| 11 图纸只露半张 | 开场完整正视图矢量轮廓及真实尺寸，不以水印为由截掉半个零件。 |
| 12 平台限制提示 | 产品“原生窗口嵌入需要 Windows”改成实际当前视图名称“原生模型视图”。 |
| 13 声音未定 | 按本轮要求无配音、无配乐；画面先审，声音最后定。 |

## 真实性与复现

第一次成功会话：`out/demo-video/paid-robot4/robot4-1/tool-calls.jsonl`。

`record-growth.cjs` 新启独立 FreeCAD 和 Electron，`reexecute_session.py` 经工程 MCP 按记录逐条调用。新宿主实例、文档身份和修订号必须重绑定；只替换这两项运行时身份字段。几何、单位、参数、操作 ID、条件和相对输出路径均逐项断言与原记录一致。未调用 dsh。没有注入预存工具结果，也没有修改原始成功/失败记录。新录片中工具卡来自当前产品真实任务回执。

正式素材采用 `growth-03`；`growth-01`、`growth-02` 是同样真实调用的取景与界面调色试录。三次都没有费用。采集为 Retina 3840×2160；CDP 按实际时间戳连续采集，静止时保持上一帧，未生成中间界面。最终 60 fps 是输出帧率，不声称源屏幕每秒都有 60 个不同画面。

```sh
# 从仓库根目录；使用本机已有完整 Python 环境。
node tools/demo-video/record-growth.cjs out/demo-video/rebuild/growth-new
/Users/huaiyi/Documents/gongke-workbench/.venv/bin/python tools/demo-video/remotion/prepare.py growth-new
ffmpeg -hide_banner -loglevel error -y -f concat -safe 0 \
  -i out/demo-video/rebuild/growth-new/frames.ffconcat -vf fps=60 \
  -c:v libx264 -preset ultrafast -crf 18 -pix_fmt yuv420p -movflags +faststart \
  out/demo-video/rebuild/assets/growth.mp4
npm --prefix tools/demo-video/remotion ci
node tools/demo-video/remotion/render.cjs
```

脚本只结束自己创建的 PID；不操作用户其他窗口、文档。原片、PDF、模型、字体、渲染 bundle 在 gitignored 的 out 中；不提交 samples/ 学生资料。

## Remotion 许可

2026-11-04 核对固定安装版本 **4.0.540** 的 `node_modules/remotion/LICENSE.md`，并核对官方 [许可价格说明](https://www.remotion.dev/docs/license/pricing) 和 [4.0 条款](https://www.remotion.pro/terms-4-0)。该版本免费许可覆盖个人、至多 3 名员工的营利组织、非营利组织；允许制作商业或非商业视频与图片。本次学生个人、非营利竞赛制作可免费使用，不购买公司许可。不能将其笼统描述为没有商业条件的 OSI 开源许可；也没有使用文档中预告的 5.0 条款替代本版许可。

字体用已安装的思源黑体 Regular/Bold；Three.js 0.180.0 为 MIT。原创 Logo 无外部图案素材。当前没有第三方音乐、语音素材。

## 后续固定边界

第 6 段用第二次模型真实核验出的两条斜边；第 7 段必须在真实 FreeCAD GUI 中修改草图，再核验、保存、重开，不能用直接脚本改几何冒充手改。第 8 段 SOLIDWORKS 只写“可接入 SOLIDWORKS（2023 实机已完成基础建模）”。结尾为 Logo、作品名“构想引擎——面向工科学生的 AI 工程工作台”、“星光杯 · 计算机学院”，不放成员姓名。

## 本轮验证

- 合并提交 `05485f6`（fe402fa）；工具卡冲突保留两边的真实失败/独立证据测试。
- Python：`pytest tests --ignore=tests/geometry --ignore=tests/fem -q`，**862 passed**。本次没有跑不相关的几何生成和 FEM 测试目录。
- 桌面：`npm run build` 通过；`npm test` **70 passed / 1 skipped**，无失败。控件青绿配色后再次构建和测试通过。
- 真实双侧定位验收：`highlight-07/acceptance.json`，两边选择、缩放对齐、图纸内容改变拒绝旧结果均通过。
- 品牌独立提交 `48e0c5f`。macOS 实际打包成功，包中 `Contents/Resources/icon.icns` 与生成图标逐字节一致；ad hoc 签名。证据 `out/demo-video/rebuild/package/icon-verification.json`。此包只核对图标嵌入，不替代完整发行验收；Windows ICO 已配置，本轮未生成 Windows 安装包。
- 余下限制：此轮不含声音，第 6、7 段实际剪辑及 GUI 修正未制作；样片审阅通过后才继续。

```sh
python3 tools/demo-video/remotion/verify.py growth-new
# 产品图纸定位验收：传入现有本地真实清单，只改新建的工作副本。
node tools/demo-video/check-highlights.cjs out/demo-video/rebuild/highlight-new \
  /Users/huaiyi/.codex/worktrees/d0e8/gongke-workbench/out/independent-drawing-check/local-manifest.json
```

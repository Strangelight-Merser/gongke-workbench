# 实时建模视图真实联调（2026-11-03）

基于 `codex/windows-delivery-20261102` 的 `f362ff5`，工作分支 `codex/live-modeling-visual-validation`。

## 修复

- Electron 白名单遗漏 `host.context`、`host.inspect`，真实窗口因此报“不支持的工程命令”。加入两个只读入口，仍走公共服务与原有校验。
- 删除按模型对角线生成 PlaneGeometry/CylinderGeometry 的量测标记。FreeCAD 显示场景现在提供各个实际裁剪面的网格及 `native_ref`，前端按检查回执匹配，保留孔洞与有限边界；深度测试保留，背面不透染到正面。
- 截面面积检查的位置增加原生截交 `edges`（m），前端沿这些曲线标红；不再绘制辅助无限平面。宿主未提供截交边时不绘制虚构范围。
- 显示网格使用与检查相同的文档坐标变换。Three.js 的 `toCreasedNormals` 保留超过 30° 的折边，修复平面上的放射状高光。

显示协议变化：`freecad.scene.objects[].faces[]` 提供 `native_ref/vertices/triangles`，沿用场景 mm；`host.measure/check` 的截面 location 提供 `edges`，沿用检查 m。工程尺寸、选择身份和写入语义未改变。网格与检查必须仍匹配同一文档修订。

## 真实运行

- macOS；FreeCAD 1.1.4（`4fd3bf320`）；本工作树 Electron 40.10.6；Python `/private/tmp/gongke-modeling-venv/bin/python`。
- 独立 FreeCAD PID 50551，端点 `out/visual-live/host/session.json`；bootstrap 记录源码路径及 SHA256。
- 独立 Electron 用户目录 `out/visual-live/user`。仅本地验收 Electron 副本使用独立 bundle ID `org.gongke.visualvalidation`，确保屏幕工具不会选中后台试验。此改动在忽略的 node_modules 内，不进入交付。
- 屏幕控制实际创建/打开 `out/visual-live/project`，选中“原生 CAD”；脚本通过 MCP 绑定桌面同一工程/服务，没有调用付费 Agent。
- 原始第一次尝试中文内部 name 被宿主 ASCII 名称契约拒绝；日志保留。脚本已使用 ASCII 原生标识，中文操作标题、毫米参数及“不符”状态正常显示。

| 阶段 | 原生修订 | 屏幕结果 |
| --- | --- | --- |
| 两个同心圆草图（外径50、孔径16） | 81 | 草图轮廓、中文步骤 |
| 底板拉伸8 mm | 109 | 实体自动出现；树新增 BasePad |
| 凸台环形草图（外径24、孔径16） | 148 | 新草图叠加到已有底板，树同步 |
| 凸台拉伸12 mm | 178 | 凸台真实生成；树新增 TubePad |
| 高度应为10 mm，实测12 mm | 178 | 两个实际环形平面标红，孔洞不被填充 |
| 外径故意要求22 mm，实测24 mm | 178 | 仅实际凸台圆柱侧面标红 |
| 截面积故意要求1 mm² | 178 | 仅真实内外截交轮廓标红 |
| 修改凸台长度为10 mm并检查 | 189 | 模型自动变矮、检查通过、旧红色消失 |

通过屏幕实点“在模型中定位”，相机重新聚焦；另实点 TubeSketch 特征树按钮，显示并聚焦对应草图。上述建模阶段均由回执自动刷新，没有用手动“读取”按钮代替实时刷新。

`out/visual-live/calls.jsonl` 是完整 MCP 调用回执。`save-scene.json` 和 `geometry-audit.json` 核对了6个真实面的 native_ref、网格均在零件范围内、三张环形面三角形没有跨越通孔；最终边界约50×50×18 mm。`project/visual_part.FCStd` 已由宿主保存。

## 屏幕证据

全部是专用构想引擎真实窗口的屏幕截图，无合成画面；本次采用分阶段截图，没有连续录屏。

- `out/visual-live/screenshots/01-sketch.png`
- `out/visual-live/screenshots/02-base.png`、`03-tube-sketch.png`：修复法线前的真实阶段，保留问题证据。
- `out/visual-live/screenshots/04-bounded-faces.png`：最终有限面高亮及修复后法线。
- `out/visual-live/screenshots/05-step-locate.png`：实点步骤定位。
- `out/visual-live/screenshots/06-cylinder.png`：有限圆柱侧面。
- `out/visual-live/screenshots/07-section.png`：实际截交轮廓。
- `out/visual-live/screenshots/08-repaired.png`：修改后检查通过，红色消失。
- `out/visual-live/screenshots/09-tree-locate.png`：特征树定位草图。

## 回归与重跑

- `npm run build --prefix desktop` 通过。
- `GONGKE_PYTHON=/private/tmp/gongke-modeling-venv/bin/python npm test --prefix desktop`：61通过、1项Windows专用测试跳过。初次用系统 python3 运行时3项服务集成测试因环境缺依赖退出，指定实际联调解释器后全部通过。
- `python -m pytest tests/test_model_inspection.py tests/test_modeling_receipt_events.py tests/test_native_modeling.py tests/test_native_client.py -q`：66通过。
- `python -m pytest tests/test_section_display_locations.py -q`：1通过。
- `git diff --check` 通过。

复跑需先用本工作树的 `tests/e2e/native_modeling_host.FCMacro` 启动独立 FreeCAD；`GONGKE_MODELING_ROOT` 指本工作树、`GONGKE_FREECAD_SESSION` 指独立端点。Electron 使用同一端点、独立 `GONGKE_DESKTOP_USER_DATA=<output>/user`，从窗口创建 `<output>/project`。

随后逐阶段运行并观察窗口（不要对已执行的写阶段重复运行）：

```sh
python tests/e2e/live_modeling_visual.py <output> sketch
python tests/e2e/live_modeling_visual.py <output> base
python tests/e2e/live_modeling_visual.py <output> tube-sketch
python tests/e2e/live_modeling_visual.py <output> tube
python tests/e2e/live_modeling_visual.py <output> fail
python tests/e2e/live_modeling_visual.py <output> cylinder
python tests/e2e/live_modeling_visual.py <output> section
python tests/e2e/live_modeling_visual.py <output> repaired
python tests/e2e/live_modeling_visual.py <output> save
```

原有验收脚本、样例及夹具均未修改。没有触碰其他 worktree 的 Electron/FreeCAD 进程，也没有连接 dsh。

## 已记录的范围外问题

`host.model_save` 返回 committed 且文件存在，但后续 `freecad.scene.modified` 仍为 true，窗口仍显示“有未保存修改”。本次没有重写保存/宿主修改标志语义；需要另行核对 FreeCAD GUI 修改标志在保存后的变化来源。此状态不影响本轮尺寸回执、实时刷新和高亮验收。

## 依据与取舍

- [FreeCAD TopoShape API](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/TopoShape_API.md)：面也是 TopoShape，可直接 tessellate，使用宿主裁剪后拓扑。
- [Three.js BufferGeometry](https://threejs.org/manual/pages/custom-buffergeometry.html)：用顶点及索引构成真实面；不引入另一套 CAD 几何计算。
- [Three.js BufferGeometryUtils](https://threejs.org/docs/pages/module-BufferGeometryUtils.html)：复用 `toCreasedNormals`，避免新增法线算法和依赖。
- [Babylon.js HighlightLayer 实现](https://github.com/BabylonJS/Babylon.js/blob/master/packages/dev/core/src/Layers/thinHighlightLayer.ts)：同类引擎也按指定 mesh 管理高亮。本项目不需要新增发光后处理，直接用目标面的透明着色即可。

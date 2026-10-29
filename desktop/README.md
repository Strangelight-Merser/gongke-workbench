# 构想引擎桌面应用

一个工程窗口管理原生模型、图纸、计算和工程助手。

## 使用

1. 新建工程时选择一个专用文件夹，或打开已有 `gongke-project.json` 所在目录。
2. 在“模型与图纸”选择 FreeCAD、SOLIDWORKS 或 AutoCAD，读取已打开的工程。FreeCAD 需启用 GongKe 工作台；两款 Windows CAD 的插件安装说明分别位于 `adapters/solidworks` 和 `adapters/autocad`。
3. 先“另存工作修订”，再修改受支持的原生参数。已有文件不会被覆盖。修改后读回原生尺寸；FreeCAD 候选会在外部编辑后失效。
4. 在“模型服务”输入服务地址、模型名和自己的密钥。密钥使用系统加密保存；系统加密不可用时仅保留本次会话。服务地址改变时须重新提供对应密钥。支持 Chat Completions 流式工具调用，实际服务连接由首次任务验证。
5. 在右侧描述任务。取消会停止后续动作，不会伪装撤销已经完成的修改。任务记录显示真实结果；中断后不自动重放原生写操作。

“设计计算”可载入明确标记的教学条件，输入工程单位，计算并生成新的 STEP、DXF/SVG、PDF 修订。它复用确定性计算模块；这些批处理图纸与原生 TechDraw/SOLIDWORKS 关联详图具有不同来源。

## 开发与打包

```sh
python -m pip install '.[desktop]' pytest
cd desktop
npm ci
npm run build
# 若 python3 并非安装上述依赖的解释器，设置 GONGKE_PYTHON 的绝对路径。
npm start
```

安装包内置独立 Python 服务，用户无需安装 Python。须在目标系统上构建：

```sh
python tools/build_app_service.py
cd desktop
npm ci
npm run package
```

产物位于 `desktop/release`。当前是未签名的开发构建；没有 Apple 公证或 Windows 安装实测声明。CI 构建 Windows/macOS 目录包，AutoCAD 另有 .NET 8 与 .NET 10 两种原生插件包。商业 CAD 安装与授权不包含在本应用中。

## 验证

```sh
python -m pytest tests/test_app_service.py tests/test_host_paths.py
cd desktop
npm run build
npm test
node tests/desktop-flow.cjs
```

桌面验收使用真实 Electron、真实 Python 服务和真实文件：新建工程、计算、生成 STEP/图纸、SVG 预览、未配置模型时明确拒绝助手任务。结果与截图写入 `out/desktop-validation`。`tests/e2e/desktop_native_flow.py` 在单个真实 FreeCAD GUI 中核对网格、图纸、编辑、原生导出与重开。

模型协议测试使用本地 SSE 测试服务，不是实际模型账号验收。SW/AutoCAD 的 SDK 编译、管道协议检查与真实宿主运行分开记录。当前 AutoCAD 视图按 WCS 平面显示支持的实体，不模拟未解析的块、字体排版和完整原生标注。

## 代码边界

- `electron/main.cts`：受限 IPC、原生文件选择、凭据加密、应用服务生命周期。
- `src`：工程树、原生模型/图纸、计算、任务与助手界面；不直接调用网络或任意进程。
- `gongke_app`：统一命令、工程清单、工作副本登记、SQLite 任务回执、模型工具循环。
- `freecad/gongke`、`adapters`：各宿主自己的对象、线程与事务语义。

预览三角形只用于显示，不能作为持久化特征身份。工程计算通过不等于疲劳、装配、制造或专业审核通过。

独立 Linux FreeCAD 1.1.4 GUI 的合成轴验收已通过 8 项：真实网格与 SVG、原生对象选择、显示时保留源文档状态及子元素选择、40→38 mm 修改与读回重算、关联原生标注更新、原生 DXF 导出、人工修改后结果过期与 Undo、保存重开且原件不变；DXF 独立读回为 2 个 CIRCLE 和 1 个 DIMENSION，测量值约 38 mm，Unicode 转义解码后文字为“⌀38”，文件审计无错误。证据位于 `out/desktop-native-validation`，它证明该 Linux 原生流程，不代表 macOS FreeCAD 故障已修复，也不代表 Windows SOLIDWORKS/AutoCAD 宿主验收通过。

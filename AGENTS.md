# 构想引擎项目规则

Claude、Codex 等开发 Agent 共用本文件。PLAN.md 记录阶段目标，模块文档记录实现契约；与本文件冲突时以本文件为准。

## 产品方向

- 面向工科学生，把计算、建模、出图软件集成到一个工作台：管理工程、提出任务、操作工具、查看结果、继续编辑。
- 提供原生 AI 工具接口，接入用户已有的 Agent（WorkBuddy、DeepSeek Harness、Claude Code、Codex 等），交互和工程操作都在工作台内完成。
- 按目标 Agent 实际支持的协议（MCP、ACP）接入；先打通一个 Agent 的完整工程流程，再扩展。
- 不自建通用模型助手、API Key 管理或工具推理循环。`gongke_app/agent` 是过渡入口，只修故障，不再扩展；替代流程完成后删除。
- 复用工程软件已有能力，不造通用 CAD 内核。

## 宿主接入与实现

- FreeCAD、SOLIDWORKS、AutoCAD 等通过官方 API、SDK 或扩展机制接入，遵守各自的线程、文档锁和事务规则（见各 adapter README、`freecad/gongke/bridge.py`）。
- 目标是统一宿主接口，FreeCAD 也纳入：统一工程上下文、对象身份、能力发现和结果语义，宿主特有能力照常声明。
- 人工操作与 Agent 工具共用一份命令实现和权限检查；CLI、MCP 等入口不得绕过。
- `gongke_core` 不依赖 CAD 宿主运行时。FreeCAD 与 build123d/OCP 分进程运行（OCCT 冲突）。
- 同一工程量只算一次，三维、二维、说明书共用结果。
- 用满足需求的最简实现；替换旧路径时删掉旧的，不留兼容层，不写用不到的校验和兜底分支。
- 技术分歧以代码、官方资料和可复现结果为准。
- 程序生成的固定文件名用 ASCII（`report.docx`、`reducer_assembly.step`），C/ASCII 区域设置下中文名会出错；用户目录和显示名称可以是中文。
- 界面、文档、注释用中文，标识符用英文，术语以国标和主流教材为准。

## 工程数据与操作

- 编辑已有模型以原生文档为准，写入前核对对象身份和修订，保留用户手工修改。
- 自动修改原件前先另存工作副本；工作副本可正常保存，原件和未授权文件不覆盖。
- 工程工具只暴露明确的工程操作，不提供任意 shell、Python、VBA、AutoLISP 执行；权限在执行端校验。
- 原生写入结果未知时查询原操作或读回，不换 ID 重发。
- 计算核心用 SI（转速 r/min），接口注明单位。材料、载荷、系数注明来源，缺失条件不编造。
- 输入变化后，依赖它的旧结果标为过期。

## 数据来源与许可

- 国标只录入数值，不复制原文、原表排版和图片；放在 `data/standards/`，一标准一文件，文件头写标准号和年份。
- 私有格式只基于公开文档和合法样例研究，不使用、阅读或复述反编译代码，过程记录在 `docs/clean-room/`。官方 SDK 可以正常使用。
- CalculiX、Gmsh、LibreDWG 等 GPL 组件以独立进程调用，不链接、不用语言绑定。

## 验证

- 新增或修改计算方法，测试数据来自教材例题或解析解，测试里注明出处（书名、版次、页码或公式）。
- 修改出图代码或影响图纸的结构参数：`pytest tests/drawing`（五个方案 lint 必须为 0），渲染 `drawings.pdf` 目视检查，按 `docs/drawing-checklist.md` 复查。
- 其他改动按影响范围跑相关测试。缺少目标宿主时照常完成实现，并说明哪一步需要在真实环境运行。
- 汇报写做了什么、结果如何，简短直接，不堆免责声明。

## 常用命令

- 计算与标准：`python -m pytest tests/calc tests/standards`
- 全部 Python：`python -m pytest tests`（需 pyproject.toml 的 dev 依赖；`--ignore=tests/geometry --ignore=tests/fem` 可加速）
- 桌面：`cd desktop && npm run build && npm test`
- Windows 插件协议：`dotnet run --project adapters/solidworks/tests/ProtocolChecks.csproj -c Release`、`dotnet run --project adapters/autocad/Gongke.AutoCAD.ContractTests -c Release`
- 应用命令与服务协议：`gongke_app/README.md`；桌面开发与打包：`desktop/README.md`

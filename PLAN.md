# 构想引擎：工程软件集成工作台

依据 2026-11-03 用户决定与两位机械学生反馈更新。规则见 [AGENTS.md](AGENTS.md)。

## 产品目标

面向工科学生，Windows 优先，以构想引擎为主窗口，支持照图纸建模或自由建模。嵌入 CAD 原生编辑界面：默认 FreeCAD，可切换到本机已安装的 SOLIDWORKS，保留原生特征树。

面向未安装 Agent 的学生，经同意下载安装 DeepSeek Harness Desktop，引导平台注册、充值和在 dsh 中填写 API Key。已有 dsh 通过 ACP 连接窗口内会话；WorkBuddy 可选安装，已有用户引导写入工程 MCP 配置。构想引擎负责工程上下文、工具与结果，不经手 Key。

## 学生主场景

学生打开图纸与已有模型，或直接新建模型。窗口内 Agent 按图纸或学生的要求，直接在嵌入的 CAD 中建出带草图和特征树的原生模型，学生可以接着手工修改；也能讲解某个特征怎么做，并结合当前模型与错误信息排查建模报错。

Agent 读取当前模型，对照图纸检查尺寸、孔和遗漏特征，定位问题并直接修正或说明修改方法，结果关联对象与修订。另设可选的**练习模式**：Agent 只讲解和检查，学生自己建模，提示逐级展开，参考模型不直接给出。

材料包与任务书提取后移；减速器计算、出图与说明书保留为专项模块，运动分析、实验数据处理在建模主流程完成后推进。[学生工作流调研](docs/research-student-workflows.md)作为背景，主场景以本次反馈为准。

## 近期阶段

先完成“打开图纸或新建模型 → Agent 在原生 CAD 中建模 → 对照图纸检查并修正 → 学生继续编辑”，练习模式复用同一套读取与检查能力。

1. **前端重构与工程入口。** 按[前端调研](docs/research-frontend-design.md)采用 Fluent UI React v9：左侧工程树、中间 CAD／文档、右侧 Agent、底部状态栏。工程对象作为一级导航，减速器步骤归入专项模块；切换文档保留视角、选择和编辑状态。调研中的材料包流程按本次决定后移。
2. **Agent 引导与连接。** 检测已有 dsh／WorkBuddy；未安装时，经用户同意下载、校验并安装官方 dsh Desktop，WorkBuddy 可选。引导注册 DeepSeek 平台、充值、创建 Key，并在 dsh 内自行填写。已有 dsh 启动 ACP、注入绑定工程的 MCP；WorkBuddy 引导写入同一工程 MCP 配置。以真实回复并读到当前工程为连接验收，见 [dsh 引导调研](docs/research-dsh-onboarding.md)。
3. **Windows 嵌入编辑区。** 先接入 FreeCAD 原生编辑界面，再支持本机 SOLIDWORKS；在真实 Windows 宿主中验证焦点、快捷键、弹窗、缩放与生命周期，让学生完成草图、特征和保存。容器保留完整编辑能力，技术依据见 [CAD 嵌入调研](docs/research-cad-embedding.md)；主窗口仍为构想引擎。
4. **Agent 原生建模与对照图纸检查。** 经统一宿主接口在 FreeCAD／SOLIDWORKS 中创建草图、约束和特征（拉伸、旋转、切除、孔、圆角、阵列等），并读取当前文档的特征、尺寸、孔与截面，按图纸条件逐项检查、定位并修正。练习模式只开放读取、检查与讲解。
5. **完善宿主插件。** 围绕主流程补齐 FreeCAD、SOLIDWORKS／AutoCAD 的文档读取、工作副本、受限修改、图纸更新、保存导出与操作查询。遵守宿主线程、文档锁和事务规则；窗口嵌入由容器承担，工程操作由插件承担。
6. **后续专项与材料包。** 接入材料导入、来源定位、任务书提取及缺项确认，区分老师给定、学生选择和程序建议。减速器专项复用已有计算、出图与说明书能力；课程允许辅助生成时，从同一份确认结果生成可检查、可继续编辑的原生工作副本。

## 关键技术决策

- 沿用 Electron＋React＋TypeScript 与随包 Python 服务；桌面、CLI、MCP 共用工程执行入口、工具定义、权限与操作记录，统一宿主文档、对象、修订、能力及结果语义。`gongke_core` 保持宿主无关，FreeCAD 与 build123d/OCP 分进程。
- ACP 负责窗口内 Agent 会话，MCP 绑定指定工程，切换工程不让旧会话操作新工程；权限在执行入口与宿主端落实。接入依据：[dsh Desktop](https://github.com/deepseek-ai/deepseek-harness/blob/master/apps/desktop/README.md)、[ACP 会话规范](https://agentclientprotocol.com/protocol/v1/session-setup)、[WorkBuddy MCP](https://www.codebuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/MCP-Guide)。布局参考 [Zoo 工作区](https://zoo.dev/docs/zoo-design-studio/features/workspace)，控件采用 [Fluent v9](https://fluent2.microsoft.design/components/web/react)。
- CAD 嵌入复用宿主编辑器。Windows 窗口重挂需落实 [SetParent](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setparent) 的窗口样式与 DPI 要求；工程操作经宿主 API 执行。
- 已有模型以原生文档为准，自动修改前另存工作副本，写入前核对对象身份与修订，保留手工修改。写入结果未知时查询原操作或读回，不换 ID 重发。
- 同一工程量只算一次，模型、图纸、说明共用结果；输入变化后旧结果标为过期。计算核心用 SI（转速 r/min），接口注明单位，材料、载荷和系数保留来源。

## 不做的事

- 不自建通用 Key 助手、模型推理循环或模型账号管理，不读取、保存或转发用户 Key；内置助手已删除，历史会话资料保留。
- 不自研 CAD 内核，不以模板参数编辑限制学生自由建模，不把轴修订案例固定为产品主场景。
- 不编造图纸条件与实验记录；不要求先有任务书，不用减速器流程统领应用。
- 近期不建设插件市场、多 Agent 平台、远程 CAD 节点或跨平台完整嵌入；优先完成 Windows 学生工作流。

实现入口：[桌面应用](desktop/README.md)、[应用命令](gongke_app/README.md)、[SOLIDWORKS 插件](adapters/solidworks/README.md)、[AutoCAD 插件](adapters/autocad/README.md)。

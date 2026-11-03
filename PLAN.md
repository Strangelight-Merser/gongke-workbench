# 构想引擎：工程软件集成工作台

按用户 2026-11-03 确认的决定更新。项目规则见 [AGENTS.md](AGENTS.md)；本文记录产品目标与阶段方向。

## 产品目标

面向工科学生，Windows 优先，以构想引擎为主窗口，集中管理材料、工程、计算、建模、图纸和结果。支持自由建模，CAD 原生编辑界面嵌入窗口：默认 FreeCAD，可切换到本机已安装的 SOLIDWORKS。交付文件尽量保留原生特征树，让学生继续编辑。

窗口内通过 ACP 托管用户已有的 Agent，首个接入 DeepSeek Harness；WorkBuddy 通过 MCP 接入工程工具。构想引擎负责工程上下文、工具执行与结果呈现，复用 Agent 自身的登录和模型能力。

## 学生主场景

学生收到老师的任务书、分组表和补充要求后，把材料连同已有草图或模型拖进构想引擎，确认自己的题号和少量缺项；随后在工作台中逐步完成方案选择、计算、建模与出图，Agent 解释依据、检查错误，并在老师要求修改时指出受影响的结果。最终学生按课程模板整理自己的说明与实验分析，导出可继续编辑的工程文件、图纸和报告，能够在答辩中解释关键选择。

材料包可以包含 PDF、Word、照片、测量记录、已有 CAD 文件及补充消息。Agent 提取题号、条件、待设计项、交付要求和截止时间，保留原文位置，区分“老师给定／学生选择／程序建议”；学生确认缺项、歧义和冲突，结构化任务书留在内部。

Agent 以讲解与检查为主，不代做：制图训练由学生操作，Agent 提示错误与修改方法；课程允许辅助生成时，提供可检查、可继续编辑的草稿。计算与说明使用有来源的条件和学生论证，实验分析使用真实记录，不编造数据、观察或个人体会。

在已有减速器能力基础上，依次扩展：**零部件测绘与 CAD 大作业 → 四杆机构／凸轮运动分析 → 实验数据处理**。场景依据见 [学生工作流调研](docs/research-student-workflows.md)。

## 近期阶段

先连通工程入口、Agent 与原生编辑，再把材料与生成结果接入同一工程；窗口与插件工作随主流程一起推进。

1. **统一工程入口与工程 MCP。** 将现有 Python 服务作为唯一工程执行入口，桌面、CLI 和 MCP 共用工具定义、权限与操作记录。MCP 绑定指定工程，切换工程不让旧会话悄悄操作新工程；FreeCAD 与商业 CAD 纳入统一宿主接口，统一文档、对象、修订、能力与结果语义。
2. **窗口内 Agent。** Electron 主进程管理 ACP 会话，React 呈现对话、权限请求、工具状态与结果。先打通 DeepSeek Harness 的完整工程流程，会话注入绑定工程的 MCP；WorkBuddy 使用同一工程 MCP。替代路径完成后删除 `gongke_app/agent`、Key 配置与旧模型循环，保留历史会话资料。
3. **Windows 嵌入编辑区。** 保留构想引擎主窗口，先接入 FreeCAD 原生编辑界面，再支持本机 SOLIDWORKS。围绕原生窗口容器处理焦点、快捷键、弹窗、缩放与宿主生命周期，保留草图、特征和手工编辑能力。嵌入方式在真实 Windows 宿主上确定，不把预览器当成编辑区。技术依据见 [CAD 嵌入调研](docs/research-cad-embedding.md)；其中改以 FreeCAD 为主窗口的建议不采用。
4. **SOLIDWORKS／AutoCAD 插件。** 继续完善现有 C# COM add-in 与托管 bundle，连接原生文档、工作副本、参数修改、图纸更新及保存导出。遵守宿主线程、文档锁与事务规则，补齐操作结果查询；窗口嵌入与工程操作分别由容器和插件承担。
5. **材料包入口。** 从材料导入、来源定位和缺项确认进入工程，串起学生的方案选择、计算、建模与出图。复用现有计算和检查能力，把来源分类、手工修改与受影响结果呈现在对应步骤中。
6. **生成到原生工作副本。** 从同一份已确认设计结果生成宿主原生草图、特征和关联图纸，接续学生手工编辑；先连通已有轴与课程设计能力，再按上述场景扩展。STEP 导入保留为实体交换路径，不声称恢复原始特征树；DXF 转 DWG 不等于恢复参数约束与图纸关联。

## 关键技术决策

- 沿用 Electron＋React＋TypeScript 与随包提供的 Python 服务。`gongke_core` 保持宿主无关；FreeCAD 与 build123d/OCP 分进程，复用宿主官方 API、SDK 和扩展机制。
- ACP 负责 Agent 会话，MCP 提供明确的工程操作；权限在共同执行入口与宿主执行端落实。协议采用官方 SDK，先覆盖实际客户端需要的本地接入。ACP 会话可注入 MCP，见 [会话规范](https://agentclientprotocol.com/protocol/v1/session-setup)；WorkBuddy 接入方式见 [官方 MCP 指南](https://www.codebuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/MCP-Guide)。窗口内会话组织可参考 [Obsidian Agent Client](https://github.com/RAIT-09/obsidian-agent-client)。
- CAD 嵌入复用宿主编辑器，不自研通用建模界面。Windows 窗口重挂是待落实的技术路径，需处理 [SetParent 文档](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setparent) 明示的窗口样式与 DPI 行为；实际编辑仍经宿主 API 执行。
- 已有模型以原生文档为准，自动修改前另存工作副本，写入前核对对象身份与修订，保留手工修改。写入结果未知时查询原操作或读回，不换 ID 重发。
- 同一工程量只算一次，模型、图纸、说明共用结果；输入变化后旧结果标为过期。计算核心用 SI（转速 r/min），接口注明单位，材料、载荷和系数保留来源。

## 不做的事

- 不自建通用 Key 助手、模型推理循环或模型账号管理；过渡期的 `gongke_app/agent` 只修故障，不再扩展，也不长期保留第二条助手路径。
- 不自研 CAD 内核，不以模板参数编辑限制学生自由建模，不把轴修订案例固定为产品主场景。
- 不做一键代交作业或代写实验报告，不用程序默认值冒充老师给定条件，不补造实验记录。
- 近期不建设插件市场、多 Agent 平台、远程 CAD 节点或跨平台完整嵌入；优先完成 Windows 学生工作流。

实现入口：[桌面应用](desktop/README.md)、[应用命令](gongke_app/README.md)、[SOLIDWORKS 插件](adapters/solidworks/README.md)、[AutoCAD 插件](adapters/autocad/README.md)。

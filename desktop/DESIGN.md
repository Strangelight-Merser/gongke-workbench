# 构想引擎桌面设计

Windows 工程工作区。学生先打开图纸或模型，在同一窗口与自己的 Agent 协作，再接着手工编辑。减速器课程设计是工程中的专项计算，不是应用的导航骨架。

## 工作区

标题栏 → 活动栏 | 主侧栏 | 编辑器组 + 底部 Panel | 辅助侧栏 → 状态栏。

| VS Code / Cursor 元素 | 构想引擎位置与行为 |
| --- | --- |
| Title Bar / Command Center | 顶部 40 px，工程名是命令面板入口；右端切换主侧栏、Panel、Agent 和主题。macOS 左侧给系统窗口按钮留位。 |
| Activity Bar | 最左 48 px：资源管理器、快速打开、问题；底端操作记录。无业务数据的插件/源码管理入口不占位。 |
| Primary Side Bar / Explorer | 默认 232 px，180–360 px；视图标题右侧是新建模型、导入图纸、刷新、更多。更多菜单放新建/打开工程，无工程时同时提供直接按钮。 |
| Explorer 分组 | 图纸、模型、计算、出图、报告、其他文件。模型用立方体图标，文件用文档图标；生成文件展示修订目录名与“过期”标记，完整相对路径悬停可见。计算专项属于工程对象，不作全局导航。 |
| Explorer 右键 | 文件“打开并保留”“在右侧打开”“复制相对路径”；原生 CAD 的几何编辑和删除仍在宿主，不从文件树绕过工作副本和修订检查。 |
| Editor Groups / Tabs | 单击文件复用一个斜体预览标签；双击文件/标签或右键“保留标签”变为常驻标签。关闭仅移除标签，不关闭原生 CAD。主编辑组保留访问过的文档实例和视角直到切换工程。 |
| Split Editor | 编辑器标题右端或文件右键向右拆分，两个组独立选标签、关闭和预览。Quick Open/资源管理器打开到最后聚焦的组。只拆分文件预览，原生 CAD 和可写计算表始终在第一个组，避免重复绑定宿主和重复提交输入。 |
| Breadcrumbs | 标签下方 27 px。文件为“工程 › 目录 › 文件”；FreeCAD 为“工程 › 模型 › 文档 › Body › 特征”，Body/特征链取当前快照的 `features.parent`，不硬编码对象层级。其他宿主仅展示已返回的文档/选择引用。 |
| Panel | 编辑器下方“问题”“操作记录”“输出 / 日志”。问题只列不符或待确认项，保留按文档身份和修订定位；日志显示本窗口服务事件及当前错误，最多 200 条，不提供任意终端。可显隐、拖动或键盘调整高度，切换面板保留已展开回执。 |
| Secondary Side Bar / Agent | 右侧默认 352 px，300–520 px；不因编辑器切页或折叠而卸载。新会话、历史、设置位于标题右侧；上下文继续使用当前聚焦编辑组的文件/原生选择，输入、权限与步骤显示由 Agent 面板负责。 |
| Status Bar | 底部 28 px。左侧为服务、工程、宿主、问题数量与执行状态；右侧为当前内容单位、修订、Agent 实际连接状态。文件单位不明时显示“文档标注”，未知修订为“—”，不把上一个原生模型的修订套给文件。 |
| Command Palette / Quick Open | 标题命令入口或快捷键打开。命令按工程、文件、模型、视图、首选项分组命名；文件按名称/相对路径过滤。方向键选择、Enter 执行、Escape 关闭并返回焦点。 |
| Welcome / 空状态 | 无工程时直接新建/打开；工程欢迎页提供导入图纸与新建模型。新建模型打开既有 CAD 工作区，再由宿主/Agent 建立模型，不绕开宿主写入契约。 |

两侧栏宽度、折叠状态、主题存本机。窗口缩窄时先折叠工程树，宽度计算包含活动栏和分隔条。分屏内文件操作改为带 tooltip 的图标，图纸缩放由用户控制，不因切面板自动重置相机。

### 快捷键

| 操作 | macOS | Windows / Linux |
| --- | --- | --- |
| 命令面板 | Cmd+Shift+P | Ctrl+Shift+P |
| 快速打开 | Cmd+P | Ctrl+P |
| 主侧栏 | Cmd+B | Ctrl+B |
| 聚焦资源管理器 | Cmd+Shift+E | Ctrl+Shift+E |
| 底部 Panel | Cmd+J | Ctrl+J |
| 问题 | Cmd+Shift+M | Ctrl+Shift+M |
| 辅助侧栏 | Cmd+Alt+B | Ctrl+Alt+B |
| 聚焦 Agent 输入 | Cmd+I | Ctrl+I |
| 向右拆分文件 | Cmd+\ | Ctrl+\ |
| 聚焦编辑组 | Cmd+1 / 2 | Ctrl+1 / 2 |
| 关闭当前标签 | Cmd+W | Ctrl+W |
| 下/上一个标签 | Ctrl+Tab / Ctrl+Shift+Tab | Ctrl+Tab / Ctrl+Shift+Tab |

快捷键只监听 renderer，不注册系统全局快捷键，CAD 获得原生焦点时由宿主处理。命令面板采用 Fluent Dialog 的焦点管理；`applyStylesToPortals=false` 使浮层继承主题但不复制全屏工作台布局，避免遮没底层编辑区。原生嵌入容器沿用对模态/菜单的隐藏处理。

### Agent 接口与所有权

本轮不修改 `src/agent/`。原有 `project / context / referencePath / removeContext / mode / onMode / onTurnEnd / openModel` props 继续使用；状态栏订阅已有 `agent.onState`。布局样式把既有“新会话”按钮及其处理器放到标题栏，外层提供历史按钮，不模拟点击内部 DOM、不另造新会话 API。

布局依赖现有 `.agent-panel > .panel-heading` 与 `.agent-controls button[aria-label="新会话"]` 两个样式锚点；另一会话若替换标题结构，请保留这两个锚点，或在合并时将标题动作统一为 `headerActions?: ReactNode` 插槽，并删除对应定位样式，不能同时留下两套标题入口。

目前 `AgentAPI` 只有 `newSession`，没有历史枚举/恢复方法。历史入口明确说明这一点并可转向操作回执，不把回执冒充对话历史。真正的历史恢复需 Agent 内部会话后续提供能力，本轮没有扩展公共协议。

### 设计依据

- [VS Code User Interface](https://code.visualstudio.com/docs/editing/getting-started/userinterface)：Workbench 区域、Explorer、Editor Groups、预览标签、命令面板和 Quick Open。
- [VS Code Custom Layout](https://code.visualstudio.com/docs/configure/custom-layout)：双侧栏、Panel、显隐与布局快捷键。
- [VS Code Code Navigation](https://code.visualstudio.com/docs/editing/editingevolved)：面包屑的文件/符号层级。
- [Cursor Agent Overview](https://cursor.com/docs/agent/overview)：侧面板入口 Cmd/Ctrl+I、标题区对话操作、会话搜索。
- [Cursor Prompting](https://cursor.com/docs/agent/prompting)：具体文件和上下文引用。

2026-11-03 查阅时，Cursor 旧 `/en/agent/chat/history` 已跳转文档首页，现行文档同时介绍 Agents Window。这里按工程编辑为中心的产品目标保留右侧 Agent；历史图标的位置是适配决定，不声称所有 Cursor 版本均使用同一布局。

## 控件与视觉

基础控件采用 Fluent UI React v9，项目颜色统一到 `src/styles/tokens.css`。外框、内容、纸面、文字、辅助文字、边线、强调、选择、成功、警告、错误均有语义 token。表单和对话框沿用 Fluent 的焦点与键盘行为。

| 项目 | 规则                                                              |
| ---- | ----------------------------------------------------------------- |
| 字体 | Segoe UI Variable / Segoe UI / Microsoft YaHei UI；数值用等宽数字 |
| 字号 | 辅助 12，树与命令 13，正文与输入 14，局部标题 16，开始页 24 px    |
| 间距 | 4 / 8 / 12 / 16 / 24 px；组间留空，不给每一段套卡片               |
| 密度 | 控件默认 32 px，树行 28 px；缩空间不缩小文字                      |
| 浅色 | 外框 #F3F3F3，内容白色，正文 #242424，辅助 #616161                |
| 深色 | 外框 #202020，内容 #252526，正文 #F2F2F2，辅助 #B8B8B8            |
| 纸面 | PDF、图纸与 DXF 保持白纸；宿主主题由 CAD 管理                     |
| 形状 | 面板贴边无圆角；控件采用 Fluent 圆角；阴影仅用于浮层              |
| 图标 | Fluent SVG；颜色用于选择、焦点与状态，不作为装饰                  |

只保留一个当前主动作。空工程突出“打开图纸”，无工程突出“新建工程”。对话输入在 Agent 底部，会话上方仅列当前附加对象，参考可移除，不重复工程标题。空状态建议使用有边框的按钮。未完成引导直接占据 Agent 面板主体，当前步骤不可折叠，不显示对话空状态或输入框；首次对话验证仍保留真实回复和授权按钮。已完成引导收进设置菜单；断开连接放在 Agent 选择器旁的操作菜单。工具详情按需展开。

DeepSeek 引导分为“检测 / 安装 → 注册与充值 → 在 dsh 填 Key → 连接并首次对话”四步。仅当前步骤有一个主按钮，其余操作为小号链接；安装路径与版本收进“安装信息”。更新 Key、充值恢复入口只在相应错误出现时显示。连接与当前工程模式绑定完成后才能发送首次对话。

已配置的 ACP Agent 可通过设置菜单“使用已配置的 Agent”直接进入连接与对话；此操作只切换面板，不写入引导完成状态。返回“安装与连接引导”继续原步骤。WorkBuddy 保留安装、连接工程、首次对话及真实回执确认流程。

## 主流程与数据边界

1. 新建 / 打开工程使用已有服务接口，不强制填写任务书。
2. “打开图纸”接受 PDF、PNG、JPEG、WebP、SVG、DXF。外部文件复制到 `inputs/<随机目录>/<原文件名>`，同名导入互不覆盖；已有工程内文件直接打开。原文件保留。
3. PDF 由 PDF.js 本地渲染，支持翻页、缩放、适应窗口，翻页与缩放使用紧凑图标按钮。锁定 `pdfjs-dist@5.4.296`，其标准主库与 worker 不使用当前 Electron 40 不支持的 `getOrInsertComputed`，不注入 polyfill；升级时须复跑当前 Electron 的预览截图。渲染完成状态绑定当前 PDF、页码和缩放比例；适应窗口的异步尺寸计算也属于忙碌状态。加载或渲染失败必须结束 spinner 并显示错误。图像支持平移、光标中心缩放。DXF 使用 dxf-viewer，中文字体随应用提供，预览不依赖联网。DXF 的库支持范围不等于完整 CAD 保真；原生文件仍由宿主编辑。
4. Agent 发送时携带当前参考；直接建模打开 CAD 文档。宿主实时界面由已有嵌入容器负责，本轮不新增草图或特征建模命令。
5. 底部问题面板以“检查项｜图纸要求｜模型实测｜偏差｜结论”展示建模核对回执中的不符和待确认项，不再注入减速器 `design.calculate` 的强度校核表。强度校核保留在减速器专项。偏差为实测减要求，展示单位；未知值不判失败或通过。旧生成成果按当前输入版本标记过期。
6. 定位前读取当前宿主上下文，核对记录的文档路径、会话和修订。FreeCAD 使用原生对象名，SOLIDWORKS 使用实际快照的持久引用，AutoCAD 使用文档 ID 与实体句柄；成功后打开对应 CAD 并归还焦点。原生选择沿用已有命令，不修改几何。
7. 工程原生写入保留对象、修订、工作副本检查。结果未知时保存原 operation_id，查询原操作；不得新建 ID 重试。商业 CAD 的状态与命令放在独立 hook，显示组件不重写宿主契约。

## 本轮数据与主题决定

- 建模检查展示读取任务回执的 `checks[]`。展示字段为 `item / expected / actual / unit / ok / detail`，其中 `target` 保存宿主、文档路径、会话、检查时修订及原生定位引用。缺失数值显示“未提供”，不从自然语言描述提取或编造；没有完整定位身份的行禁用定位并说明原因。此处是 renderer 的展示模型，不新增 Python 服务或宿主协议。现有 `revision.inspect` 的采集、映射和问题列表仍展示源记录，不把图纸缓存尺寸冒充设计要求；完整定位需检查方提供现有宿主快照身份。
- 主题使用 Fluent v9 的明暗 token。深色透明按钮文字为 `#D6D6D6`，在 `#252526` 上为 10.54:1。默认品牌悬停色 `#479EF5` 在 `#383838` 上仅 4.18:1，改为项目强调色 `#75B6ED`；移除按钮跨明暗主题的颜色渐变，避免浅色前景残留在深色底上。禁用态保留独立的 Fluent disabled token。项目按用户要求，将可用文字与图标都按至少 4.5:1 检查（WCAG 非文字图标最低要求原为 3:1）。

## Agent 模式决定

工程 MCP 已提供 `--allow-writes`，不需要改变 Python 协议。窗口内“直接建模”使用允许写入的绑定工程连接；“练习”移除此参数，由现有执行端只开放只读工具。默认配置文件本身仍保持只读，只有用户在窗口内选择的模式用于本次连接。

练习先支持受现有工程工具策略约束的 DeepSeek Harness。其他 ACP 配置和 WorkBuddy 外部会话不伪装成受此模式控制。登录、充值和 Key 保留在 Agent 自己的应用内。

切换模式需要重连，不能原地提升旧 MCP 绑定的权限。当前对话记录保留在窗口中并标记模式切换，Agent 端建立新会话；草稿保持。执行中不可切模式。工程切换清理当前选择与文档，Agent 的执行绑定由 Electron 的现有工程检查隔离。

## Agent 错误详情

友好提示下提供“错误详情”，展示操作阶段、ACP 错误码及消息、上游错误数据、失败工具回执和 dsh stderr 尾部摘要。默认收起，不把连接成功当作模型调用成功。诊断经本地 IPC 的 `errorDetails` 传递；错误向上传播时保留同一份详情，不再次重写底层原因。

桌面将脱敏诊断写入 userData 下的 `agent-errors.jsonl`，详情内显示实际日志路径；Key、Bearer 凭据及敏感环境变量值不写入日志。日志写入失败就地显示，不能覆盖原始故障。stderr 只保留有界尾部，完整对话与启动环境不纳入诊断。

`onboarding-smoke.cjs` 每次在输出根目录创建独立的 `run-*` 目录，失败保留 `failure.json` 和诊断日志，无需删除上次结果。脚本仍要求真实首次回复和当前工程的有效 MCP 回执。

## 必须保持的 15 条约束

1. 工程对象是一级导航，课程步骤只属于专项任务。
2. 中心内容优先，外围面板可调整、折叠并记住布局。
3. 不重复原生 CAD 的特征树、属性栏和工具栏。
4. 切换文档不丢草稿、视角、缩放、选择与对话。
5. 条件展示值、单位与来源；可编辑字段使用表单，禁止 JSON 编辑器。
6. 工程名在标题命令中心可见，Agent 只显示当前附加对象并允许移除参考。
7. 修改展示真实差异与影响；取消、撤销、另存使用准确名称。
8. 结果状态绑定输入与修订，过期文件不能充当有效成果。
9. 同类对象使用树、列表、表格；没有真实缩略图就用文件列表。
10. 控件用 Fluent，业务视觉用语义 token，不每页另选风格。
11. 不使用装饰网格、渐变、emoji、发光、重复副标题、研发状态文字。
12. 键盘可导航树、标签、命令、表单与对话框；焦点必须可见。
13. CAD 内快捷键交给宿主；不注册抢占原生编辑的全局快捷键。
14. 加载、空白、错误、断连、执行中、过期与恢复均有真实状态。
15. 不新增 Key 管理或模型循环，使用用户自己的 ACP / MCP Agent。

## 代码职责

- `app/`：应用壳、工程事件、布局状态。
- `project/`：工程树、对象分类、减速器条件及专项阶段。
- `workspace/`：文档、预览、原生编辑容器与宿主检查。
- `agent/`：连接引导、设置表单、会话、权限与输入。
- `operations/`：操作记录、检查结果、未知原生操作与 DXF 导入。
- `ui/`：控件入口及少量工程展示组件。
- `styles/`：语义 token 与工作区、文档、Agent 样式。

`main.tsx` 只挂载应用。嵌入 CAD 的 React 控件从 `electron/embed/` 移入 `src/workspace/EmbeddedCad.tsx`，删除旧 UI 文件与旧 CSS；Electron 的嵌入协议和原生控制实现不变。旧 `CommercialView.tsx` 与旧全局样式已移除。必要的 Electron 接线仅承担图纸选择 / 安全读取、MCP 模式参数，不改 Python 或宿主插件。

## 验证与截图评审

在 `desktop/` 执行：

```sh
npm run build
npm test
node tests/visual-review.cjs /absolute/path/to/frontend-review
```

开发服务测试需要包含项目 `app` 依赖的 Python。可设 `GONGKE_PYTHON` 为已有虚拟环境的 Python 路径；不改变服务代码以绕过缺失依赖。Electron 运行时需已安装；缺少时按当前包管理器策略执行 `npm rebuild electron`。

截图脚本启动独立 Electron userData，加载生产 renderer，并注入测试目录内的模拟服务边界。每个尺寸（1366×768、1920×1080）覆盖空工程、PDF、图片、DXF、Agent 建模中、检查结果、引导未完成、深色主题，共 16 项。每项失败后保存 `尺寸-场景-failure.png` 与同名 JSON 并继续下一项；最终 `review.json` 汇总全部状态，`failure.json` 汇总失败项，有失败则退出码为 1。窗口无法启动时也记录该尺寸的未完成项。脚本还独立检查页面无横向溢出、PDF 当前缩放渲染完成且 spinner 消失、引导主体、单排 CAD 工具栏、检查数值与原生定位请求、输入折叠恢复、键盘调整和布局保存。深色控件逐项读取实际计算样式，验证常态及悬停文字/图标至少 4.5:1，颜色和比值写入 `review.json.contrastRecords`。评审标记占用状态栏正常布局，不浮在控件上。

**截图水印与 CAD 区域均明确标记样例。** Playwright 的 Chromium 截图不包含外部原生 HWND，此脚本不能证明真实 FreeCAD / SOLIDWORKS 嵌入成功；Windows 真实宿主的焦点、弹窗、DPI、手工编辑与保存另走原生验收。可用 `freecad-flow.cjs` / `commercial-flow.cjs` 检查既有原生语义，模拟宿主结果不得当作真机验收。

人工评审应检查：中心占比与树行密度、16 张图的裁切与可读性、主题对比、对话与权限位置、弹层遮挡、文档切换和输入保持。在 Windows 125% / 150% 缩放下再检查原生 CAD 矩形与焦点。首轮已查看外部回传的空工程截图与 PDF 失败截图，按七项反馈修正 PDF 版本、标记遮挡、树与 Agent 密度、PDF 工具栏、工程标题和截图续跑。第二轮外部 16 张截图均生成成功，已查看 PDF、深色、建模、检查、引导五张问题图并按六项反馈修订。截图脚本此前仅证明流程未报错；第三轮加入渲染状态、对比度与定位断言。第三轮外部评审确认上述六项修正；本轮已查看第三轮的引导与建模截图，继续收敛引导层级、模型保存状态和真实窗口流程入口。**本轮第四次截图及真实窗口流程仍待外部运行。**

`acp-flow.cjs` 从“使用已配置的 Agent”进入连接，继续验证 ACP 会话、窗口内权限批准、工具完成及真实 Agent 回复；`onboarding-live.cjs` 从菜单进入引导并沿实际步骤连接，继续验证权限、工程回执及重启后的完成状态。两者用可访问名称定位控件，不通过伪造引导状态绕开界面。`onboarding-smoke.cjs` 直接验证控制器与 ACP，不含窗口选择器，保持原样。

## 依据

- [Fluent React v9 组件](https://fluent2.microsoft.design/components/web/react)：统一控件、树、标签、对话框与状态展示。
- [Fluent 布局](https://fluent2.microsoft.design/layout)：4 px 间距基线和组间留白。
- [VS Code 自定义布局](https://code.visualstudio.com/docs/configure/custom-layout)：可折叠侧栏与文档工作区。
- [PDF.js 示例](https://mozilla.github.io/pdf.js/examples/)：分页渲染、独立 viewport 和 HiDPI canvas。
- [PDF.js v5.4.296 官方发布](https://github.com/mozilla/pdf.js/releases/tag/v5.4.296)、[官方构建说明](https://mozilla.github.io/pdf.js/getting_started/)：使用该版标准构建，主库与 worker 成对锁定。
- [dxf-viewer](https://github.com/vagran/dxf-viewer)：DXF 渲染与字体加载，不自行实现几何解析。
- [Noto CJK](https://github.com/notofonts/noto-cjk)：`src/assets/preview-font.ttf` 为 Noto Sans SC 字体，SIL OFL 许可证同目录附带；仅用于离线 DXF 文字预览。

- [WCAG 文字对比度](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html)与[非文字对比度](https://www.w3.org/WAI/WCAG22/Understanding/non-text-contrast.html)：用最终计算颜色核对阈值，不从抗锯齿截图取样估算。
- [Fluent 颜色与交互状态](https://fluent2.microsoft.design/color)：使用语义 token 区分可用、悬停与禁用状态。

- [Playwright locators](https://playwright.dev/docs/locators)：窗口流程按可访问角色和标签定位真实控件。

- [ACP 会话建立](https://agentclientprotocol.com/protocol/v1/session-setup)与[对话流程](https://agentclientprotocol.com/protocol/v1/prompt-turn)：会话建立、模型回复与工具执行是不同阶段，各自保留错误来源。

## 原生建模过程（2026-11-03）

中间视图默认显示原生几何，Windows 仍可切回嵌入编辑。首次打开自动读取；建模完成回执到达后读取一次 `freecad.scene`，不再用定时器把修订变化后的模型清空。读取期间到达的回执合并为一次后续读取，不并发请求宿主。手工操作仍可用“读取 FreeCAD 工程”刷新。WebGL renderer、相机与 OrbitControls 保留，仅替换网格；新文档的第一个非空几何自动取景，后续修改不改变视角。

`host.context/inspect` 提供文档身份、Body 下的特征树和世界坐标边轮廓，`freecad.scene` 提供实体网格与图纸；前后修订不一致则不拼接快照，保留上一画面并显示刷新原因。草图尚未生成实体时按成功回执的草图引用读取轮廓。蓝色轮廓标出本次特征的原生边，不将完整特征形体称作布尔差分。

右侧步骤来自公共执行服务的 `task.receipt`，因此外部 WorkBuddy MCP 与窗口内 Agent 共用记录。新事件增加 `project` 用于工程过滤；准备/完成回执按既有 task_id、at、command 关联；磁盘收据格式保持原语义。`host.check` 的桌面调用也记录回执。重新打开工程从现有 `task.list/task.get` 恢复最近记录；步骤可展开原参数和原结果。草图名称、长度、角度与阵列数量按真实输入显示，不从线弧组合臆测胶囊、贯穿孔或设计用途。查询原 operation_id 得到确定成功后才刷新，不重发写入。

点击历史特征步骤，只在同一宿主实例、文档和配置的当前特征树中重新解析仍存在的对象；删除项不提供定位。面/边检查必须匹配完整修订。红色半透明平面/圆柱表示**量测支撑面或轴面**，不冒充有限拓扑面的精确着色；边用实际采样轮廓。没有实体的 missing/unknown 保留文字，不虚构位置。新修订自动移除旧检查标记。Windows FreeCAD 嵌入视图同时使用带修订校验的原生 selection 高亮；步骤定位会切到工作台视图以查看轮廓与检查标记。SOLIDWORKS 的步骤文案可展示，当前没有通用显示网格协议，本轮不声称实现其 Three.js 实体镜像。

验证入口：`npm run build`、`GONGKE_PYTHON=<含 app 依赖的 Python> npm test`；`node tests/modeling-headless.cjs` 使用 headless Chrome 检查实际 React/Three.js 渲染、首次读取、回执后网格只读一次、canvas 保留、删除树节点与检查过期。`tests/fixtures/modeling-live.*` 是明确标记的合成几何样例，不能作为 FreeCAD 真机证据。Python 回执与公共入口回归见 `tests/test_modeling_receipt_events.py` 及原有 app/modeling/inspection 测试。

本轮日志与截图：`out/live-model-validation/`。真实 FreeCAD→MCP→Electron 验收须在屏幕释放后，使用独立 `GONGKE_FREECAD_SESSION`、独立桌面状态目录和工程，按 `docs/native-modeling.md` 的脚本驱动草图、拉伸、修改、检查失败/修复和删除；不得连接其他会话的活动模型。当前只读屏幕核对仍存在 `WorkBuddy P7 验收`，底栏路径为 `.../out/workbuddy-20261103-065546/project`，未启动或操控另一个 GUI。

依据：[Three.js OrbitControls](https://threejs.org/docs/pages/OrbitControls.html) 的 camera/target 与 damping 生命周期；[ACP tool calls](https://agentclientprotocol.com/protocol/v1/tool-calls) 的展示更新与实际执行分工；同类 [freecad-mcp](https://github.com/neka-nat/freecad-mcp) 的宿主插件读取方式。采用项目已有原生读取和受限工具，没有引入其任意代码执行入口或依赖。

补充无窗口原生验证：`/Applications/FreeCAD.app/Contents/Resources/bin/python tests/e2e/modeling_display_freecad.py` 在全新 Python 进程中创建并关闭自己的内存文档，验证真实 Sketch 轮廓、Body/Sketch/Pad 树和世界坐标边，产出 `native-read.json`。本机已通过；这是 FreeCAD 原生读取证据，仍不等同于 GUI/MCP/Electron 端到端验收。系统缺少可选 3Dconnexion 驱动库的提示保留在 `native-read.log`。

## Agent 步骤密度与详情（2026-11-03）

依据 DSH 官方仓库版本 `8bd073392eef6f54e921a093b95076248eb08cbb` 的 ToolRow、GenericToolCard、ToolCallTree 与 ReasoningRow，来源及许可见根目录 THIRD_PARTY_NOTICES.md。

上游工具行默认 24px，次级字号 13px（正文减一级），摘要单行省略；运行状态独立呈现，错误摘要使用错误色。通用工具按输入/输出组织展开内容，每区限高 150px 独立滚动；专用工具另有读文件、diff、终端等卡片和原始调用检查入口。思考独立折叠，运行时可预览已完成段落首行。调用树按 PTC 的真实父子关系缩进，不能把它误称为按连续次数自动分组。

本项目采用相同的信息层级，独立实现，使用 Fluent token：正文 14px，工具 12px，单行 26px；不移植 DSH 的插件、终端及代码渲染体系。连续超过三次成功调用合为“已完成 N 步”，按原顺序展开；正文、思考、失败、待核实和待授权切断分组，不将检查不符藏入成功组。ACP 流与工程回执各自分组，缺少共同调用 ID 时不猜测合并，保留宿主回执定位能力。

展开第一层显示中文操作摘要对应的结果、错误、特征引用与检查要求/实测值；长度摘要继续按现有 SI → mm 转换。检查详情保留源单位，不猜换算。长消息先显示 240 字，“显示全部”后仍限高 160px；原始参数、ACP 内容及完整回执在下一层 JSON 区域，限高 180px 可滚动和选择复制。思考限高 180px，默认折叠。权限卡片按钮保持可见，参数也收到原始详情层。未读取的错误、未知状态不判为成功；界面只改变展示，不改变权限、写入或重试语义。读者向上阅读时新事件不强制拉回底部。

验证入口：`node tests/agent-visual-review.cjs <目录> before|after`（先构建对应版本）。测试替身含 36 次调用、长参数/回执、失败重试、尺寸不符和授权；不调用模型、不执行 CAD 写入。before/after 使用同一数据与窗口尺寸，另存折叠总览。visual-review 的建模场景等待自动打开的模型页，再通过“返回 CAD 编辑”进入嵌入布局，不再点击已卸载的开始页按钮。

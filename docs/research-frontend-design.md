**构想引擎需要先重做工作区结构与操作连续性，再统一视觉。** 当前“AI 味”主要来自：用课程步骤代替工程导航、面板按页面拼接、重要操作藏在说明文字和 JSON 后面，以及视觉规范没有落实为交互能力。换主题或套 UI kit，解决不了这些问题。

建议采用：**Zoo 的 CAD＋Agent 工作区思路、VS Code 的面板组织、Fluent 的 Windows 控件规范**。组件基础优先选 Fluent UI React v9；UINice 用作资料入口，暂不购买整站改造方案。

本次已读当前源码、PLAN 和学生场景；`npm run build` 通过，Git 工作区无变更。Electron 启动失败，Playwright Chromium 报系统权限拒绝，以下界面问题依据代码判断，未冒充截图实测。

**1．当前具体哪里有问题**

P1 表示优先影响任务完成，P2 表示影响理解与视觉品质。

| 优先级 | 问题与用户后果 | 代码证据 |
|---|---|---|
| P1 | **一级导航绑定减速器课程。** “电动机→传动零件→轴系”占据工程入口；材料、模型、图纸没有形成稳定的对象结构。测绘、自由建模和实验场景无处安放。 | [Workflow.tsx:7](/Users/huaiyi/Documents/gongke-workbench/desktop/src/Workflow.tsx:7)、[main.tsx:471](/Users/huaiyi/Documents/gongke-workbench/desktop/src/main.tsx:471) |
| P1 | **真实入口缺失。** 新工程直接进入参数表；工程文件默认折叠、平铺显示，没有材料导入、题号选择、来源核对流程。与最新学生场景脱节。 | [main.tsx:57](/Users/huaiyi/Documents/gongke-workbench/desktop/src/main.tsx:57)、[main.tsx:534](/Users/huaiyi/Documents/gongke-workbench/desktop/src/main.tsx:534)、[main.tsx:979](/Users/huaiyi/Documents/gongke-workbench/desktop/src/main.tsx:979) |
| P1 | **编辑不能连续进行。** 任务书草稿只存在组件局部状态，切换页面会卸载；未点击计算或保存的修改没有持久化，也没有离开提示。 | [main.tsx:648](/Users/huaiyi/Documents/gongke-workbench/desktop/src/main.tsx:648)、[main.tsx:998](/Users/huaiyi/Documents/gongke-workbench/desktop/src/main.tsx:998) |
| P1 | **选模型对象会重建场景。** effect 依赖 `selected`，内部重新创建 renderer、camera、controls，并重设相机位置。选择动作可能直接破坏刚调整好的观察角度。 | [ModelView.tsx:16](/Users/huaiyi/Documents/gongke-workbench/desktop/src/ModelView.tsx:16)、[ModelView.tsx:60](/Users/huaiyi/Documents/gongke-workbench/desktop/src/ModelView.tsx:60)、[ModelView.tsx:114](/Users/huaiyi/Documents/gongke-workbench/desktop/src/ModelView.tsx:114) |
| P1 | **空间分配僵硬，而且宿主之间不一致。** 左栏固定236px，右栏约300–340px；Agent 固定占右栏50%。FreeCAD 属性进入外侧检查器，商业 CAD 又在中间塞入约220px属性栏，外侧检查器仍保留。1080px窗口下模型区域可能只剩约300px。 | [style.css:208](/Users/huaiyi/Documents/gongke-workbench/desktop/src/style.css:208)、[style.css:940](/Users/huaiyi/Documents/gongke-workbench/desktop/src/style.css:940)、[CommercialView.tsx:536](/Users/huaiyi/Documents/gongke-workbench/desktop/src/CommercialView.tsx:536)、[main.tsx:1478](/Users/huaiyi/Documents/gongke-workbench/desktop/src/main.tsx:1478) |
| P1 | **阶段导航伪装成阶段完成。** “继续”只是切换 tab，没有完成当前任务；“生成模型与图纸”实际还生成说明书，动作名称与范围不一致。计算、建模、出图之间缺少可检查的交接。 | [main.tsx:695](/Users/huaiyi/Documents/gongke-workbench/desktop/src/main.tsx:695)、[main.tsx:1125](/Users/huaiyi/Documents/gongke-workbench/desktop/src/main.tsx:1125) |
| P1 | **Agent 的当前对象不透明。** 发送时携带 `check/file/native`，可见上下文却主要展示校核名称；商业 CAD 组件没有向 App 回传选择上下文的接口。用户难判断“修改这个”究竟指谁。 | [main.tsx:391](/Users/huaiyi/Documents/gongke-workbench/desktop/src/main.tsx:391)、[main.tsx:636](/Users/huaiyi/Documents/gongke-workbench/desktop/src/main.tsx:636)、[main.tsx:851](/Users/huaiyi/Documents/gongke-workbench/desktop/src/main.tsx:851) |
| P2 | **把内部结构当产品界面。** “完整条件”是 JSON 编辑器；部分原生内容和回执直接显示 JSON；断连页面出现“插件已通过引用编译”等研发状态。 | [main.tsx:1166](/Users/huaiyi/Documents/gongke-workbench/desktop/src/main.tsx:1166)、[CommercialView.tsx:458](/Users/huaiyi/Documents/gongke-workbench/desktop/src/CommercialView.tsx:458)、[CommercialView.tsx:690](/Users/huaiyi/Documents/gongke-workbench/desktop/src/CommercialView.tsx:690) |
| P2 | **排版把空间花在框架上，把必要信息缩小。** 工作纸左内边距52px、阶段标题22px，但来源标记仅9.5px、面板标题11px。淡格背景遍布表单，层级主要依赖小字与浅色。 | [style.css:472](/Users/huaiyi/Documents/gongke-workbench/desktop/src/style.css:472)、[style.css:533](/Users/huaiyi/Documents/gongke-workbench/desktop/src/style.css:533)、[style.css:608](/Users/huaiyi/Documents/gongke-workbench/desktop/src/style.css:608) |
| P2 | **图纸列表和修订轴外观完整，操作价值不足。** 图纸“缩略图”只是 SVG/PDF 等格式文字；修订轴是不可点击的 span，不能打开、比较或追踪影响。 | [main.tsx:1264](/Users/huaiyi/Documents/gongke-workbench/desktop/src/main.tsx:1264)、[main.tsx:916](/Users/huaiyi/Documents/gongke-workbench/desktop/src/main.tsx:916) |

另外，源码颜色计算显示，`--ink-3` 在工作纸和外框上的对比度约为 **3.42:1、3.05:1**，却用于小字号正文、标签和单位，低于普通文本的4.5:1要求。[颜色定义](/Users/huaiyi/Documents/gongke-workbench/desktop/src/style.css:3)、[W3C 对比度规范](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html)

已有设计文档其实要求了可拖分隔、折叠检查器、命令面板，但实现没有兑现；同时它仍把“课程指导书章节顺序”作为学生的统一心智模型。下一次必须同时修正**规范与实现**。[旧规范](/Users/huaiyi/Documents/gongke-workbench/docs/design-language.md:13)

**2．UINice 能解决什么，以及其他设计资源怎样用**

UINice 目前有三层产品：

| 内容 | 实际能力 | 对我们的价值 |
|---|---|---|
| 免费目录 | 人工筛选 UI kits，提供分类、检索、安装资料和推荐 | 找组件及比较实现，省检索时间 |
| 免费 MCP | `search_kits`、`get_kit`、`save_kit`、`weekly_picks` | 让 Agent 查目录、取安装命令和提示词、收藏；**不负责诊断我们的工程流程** |
| Pro | 三套自有设计系统、组件与模板，通过提示词下载应用 | 可以统一外观，但不能证明能处理嵌入 CAD、对象选择、修订和修改影响 |

MCP 的使用流程是：在官网选择编辑器→获取 key→按生成配置连接→请求搜索 kit→读取具体 kit 文档后采用。这里的 MCP 是把目录能力开放给 AI 编辑器的工具接口。[UINice MCP](https://uinice.com/mcp)

Pro 当前标价为30天9.99美元、365天79美元、终身129美元。公开的 Graphite Atelier 提示词会要求改造整个网站，同时保留 routes、字段和 API；示例围绕订单后台、设置页和落地页。**这些边界恰好无法解决构想引擎需要调整的信息架构。** 若以后试用，先限定一个条件表或结果列表；不要将整站提示词直接交给实现会话。[价格与范围](https://uinice.com/pricing)、[Graphite Atelier 公开提示词](https://uinice.com/pro/graphite-atelier)

关于“AI 味”，用户讨论反复提到紫蓝渐变、玻璃卡片、居中宣传标题、模板字体组合；也有人指出，装了反套路 skill 后只是统一变成绿色。这些是经验帖，能说明反感点，不能证明某个颜色天然不好。[模板化 UI 讨论](https://www.reddit.com/r/vibecoding/comments/1ua16u7/what_do_yall_use_to_make_your_saas_not_look_like/)、[“绿色成为新紫色”](https://www.reddit.com/r/ClaudeAI/comments/1rtuqb1/emerald_green_is_the_new_purple_ai_skills_made/)

对本项目，避免方法应落到具体行为：

- 渐变、emoji、大圆角、阴影不作为默认装饰；颜色承担选择、焦点和工程状态。
- 同类数据采用行、列、树；卡片仅用于确实独立的对象，图纸卡片必须提供真实缩略图。
- 删除重复标题、解释型副标题和“看起来像功能”的装饰标签。
- 密度以“能比较多少条件、能看清多少模型”为准，不能靠缩小字实现。
- 空白、加载、错误、修改后过期与恢复路径一起设计，不能只做初始成功页。

可用的指导与 skills：

| 资源 | 建议用途 | 本项目应怎样约束 |
|---|---|---|
| [Anthropic frontend-design](https://github.com/anthropics/skills/blob/main/skills/frontend-design/SKILL.md) | 明确设计方向、字体层级、token、真实内容与截图自评 | 借用其有意图的设计方法；不要把突出品牌、hero、独特字体等网页表达搬进工程工作区 |
| [Impeccable](https://github.com/pbakaus/impeccable) | 对已有界面做 critique、audit、polish | 每次审一个具体流程或组件；结果必须对应代码与可复现问题 |
| [UI UX Pro Max](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) | 搜索风格、配色、字体及 UX 指导 | 用作备选资料库；锁定设计体系后不再让它每页重新选风格 |
| [Vercel Web Interface Guidelines](https://vercel.com/design/guidelines) | 键盘、焦点、命中范围、表单与反馈检查 | 适合变成实现验收清单，特别是对话框焦点恢复与键盘操作 |
| [shadcn 官方 skill](https://ui.shadcn.com/docs/skills) | 按项目配置正确查找、组合组件 | 解决组件 API 使用问题；不替代工程信息架构 |
| [Refactoring UI](https://refactoringui.com/) | 层级、间距、对齐、弱化次要内容 | 优先应用“从功能开始”“标签克制”“减少无意义边界”；不能机械理解为减少所有信息 |

**3．最值得借鉴的成品**

| 参考 | 应学习的部分 | 不宜照搬的部分 |
|---|---|---|
| [Zoo Design Studio](https://zoo.dev/docs/zoo-design-studio/features/workspace) | CAD中心、可调面板、命令入口、工程内AI对话与状态栏；与我们的组合最接近 | 自有建模语言、云几何引擎及整个产品实现 |
| [SOLIDWORKS](https://www.solidworks.com/sites/default/files/2020-05/Fundamentals3DDesign-SIM-ENG-SV.pdf)、[Fusion](https://help.autodesk.com/view/fusion360/ENU/?contextId=LP-STEPS-P13N-SNP-GS-OTH-CRD-1)、[Onshape](https://cad.onshape.com/help/Content/Home/user_interface_basics.htm?Highlight=use) | 对象树、上下文工具、参数编辑、文档标签、特征历史 | 在外围再次复制原生宿主已有的树和整套工具栏 |
| [Blender](https://docs.blender.org/manual/en/5.2/interface/window_system/index.html)、[Figma](https://help.figma.com/hc/en-us/articles/360039831974-Explore-the-navigation-bar-and-left-sidebar) | 工作内容占主区、选择驱动属性、面板服务对象 | 初版就做任意窗口拼接，或为视觉悬浮牺牲可用面积 |
| [VS Code](https://code.visualstudio.com/docs/configure/custom-layout) | 左工程树、中心文档、右辅助面板、底部问题列表；显隐与尺寸可控制 | 把所有工程功能变成插件式图标入口 |
| [Zed Agent Panel](https://zed.dev/docs/ai/agent-panel)、[Cursor](https://cursor.com/help/ai-features/agent) | 上下文附加、对话与工作内容并存、变更审阅入口 | 让对话替代结构化结果，或让用户在长消息里寻找修改对象 |
| [Linear](https://linear.app/now/behind-the-latest-design-refresh) | 稳定的操作位置、紧凑列表、让导航弱于内容、减少重复边框和图标 | 过淡的辅助文字，以及把任务管理布局直接套到CAD |

Fluent 2 适合提供控件、间距和状态规范；Windows 规范负责标题栏、缩放、键盘与系统行为。微软明确为鼠标键盘主导的生产力应用推荐紧凑控件密度，**Fluent 不等于把桌面做成宽松的 Windows 设置页**。[Fluent 布局](https://fluent2.microsoft.design/layout)、[紧凑密度](https://learn.microsoft.com/en-us/windows/apps/develop/ui/controls/compact-sizing)、[Windows 标题栏](https://learn.microsoft.com/en-us/windows/apps/design/basics/titlebar-design)

参考网站的使用优先级：

- **[Mobbin](https://mobbin.com/)、[Refero](https://refero.design/)**：适合寻找真实产品屏幕和连续流程。重点检索文件导入、分栏编辑、AI上下文、变更审阅、错误恢复；Mobbin公开页可见 Linear、Claude、Manus 等产品样例。
- **Godly／[Recent](https://recent.design/info)**：`godly.website` 当前转向 Recent。适合研究视觉细节，不能作为工程软件信息架构依据。
- 本项目应固定少量参考：**一套工作区、一套条件确认、一套修改比较**，并写清楚各自借鉴什么。不要拼贴十种“漂亮页面”。

**4．建议的构想引擎界面**

整体采用贴边、可调整的工作区：

```text
系统标题栏：工程名、保存状态、窗口控制
菜单／命令：文件  编辑  视图  工程         搜索命令
┌──────────────┬────────────────────────────┬──────────────────┐
│ 工程树        │ 文档标签                    │ Agent            │
│              │ 任务书.pdf  条件  模型  图纸  │ 当前工程／对象     │
│ 材料          ├────────────────────────────┤                  │
│ 条件          │                            │ 对话、问题、操作   │
│ 模型          │ 当前文档 / 原生 CAD 编辑区   │                  │
│ 计算          │                            │                  │
│ 图纸          │                            ├──────────────────┤
│ 报告          │                            │ 输入与附件         │
├──────────────┴────────────────────────────┴──────────────────┤
│ 当前修订  保存状态  CAD连接  单位       问题  后台任务          │
└─────────────────────────────────────────────────────────────┘
```

- **左侧管理工程对象。** 材料、条件、模型、计算、图纸、报告是稳定分组；减速器七阶段放进该工程的任务清单，不再决定整个应用导航。
- **中间管理打开的文档。** 允许任务书与条件并排核对；CAD、图纸切换保留视角、缩放与选中对象。
- **右侧默认完整 Agent 面板。** 检查器按需展开，可调高度、可折叠；没有选中内容时不占半屏。原生CAD已经展示的尺寸属性不再重复摆一套。
- **底部状态栏保持薄。** 点击问题、后台任务或修订，展开相应列表；运行记录不再替换整个模型工作区。
- 左树初始约240px，Agent约360px。中心不足约720px时优先折叠外层工程树；布局按窗口可用宽度适配，并记住用户调整。
- 原生CAD区域保持完整矩形。菜单、对话框、焦点与快捷键要经过真实宿主验证；不能假设 React 的 `z-index` 能盖住原生窗口。

信息层级固定为：**当前对象与操作 → 当前问题及修改影响 → 来源与详细记录**。同一局部任务只突出一个主动作。

主场景应这样贯通：

| 环节 | 用户看到、操作和得到的结果 |
|---|---|
| 拖入材料 | 文件进入材料树；逐文件显示导入状态。已有CAD直接进入模型分组，不强制先填减速器参数 |
| 确认条件 | 左边原文，右边“条件／值／单位／来源／归属”；只突出缺项、冲突和题号歧义；老师给定、学生选择、程序建议可区分 |
| 计算 | 显示采用的条件版本；结果用可比较表格呈现，失败项置前；点数值可以定位公式与来源 |
| 建模 | 打开原生工作副本；Agent建议与对应对象相连。制图训练保留学生操作入口，允许生成时明确呈现草稿 |
| 出图 | 选择图纸范围和必要设置；看到真实预览、图检问题及可继续编辑的文件；报告单独生成 |
| 修改影响 | 例如拉力改变后，先列出受影响的计算、模型、图纸与报告；保留旧成果并标过期，提供“更新受影响结果”，结果可比较 |

视觉基线建议如下，作为首版原型参数：

| 项目 | 约束 |
|---|---|
| 字体 | Windows优先 `Segoe UI Variable / Segoe UI / Microsoft YaHei UI`；数值采用等宽数字，代码才用等宽字体 |
| 字号 | 12px辅助、13px树与工具栏、14px表单与对话、16px局部标题、20px起始页标题；必要信息不低于12px |
| 间距 | 4／8／12／16／24px；组件内部紧，组间明显；取消52px纸面左边距 |
| 密度 | 默认控件高32px、树行28px；紧凑模式缩减间距，不缩字号 |
| 色彩 | 浅色：外框 `#F3F3F3`、内容 `#FFFFFF`、正文 `#242424`、辅助 `#616161`；蓝色强调可保留现有品牌方向 |
| 深色 | 外框 `#202020`、内容 `#252526`、正文 `#F2F2F2`、辅助 `#B8B8B8`；图纸纸面保持白色，CAD主题单独尊重宿主 |
| 形状 | 贴边面板不加圆角；控件4px、弹层8px；阴影仅表达浮层 |
| 图标与动态 | 统一Fluent SVG图标，16/20px；禁用Unicode拼凑图标；动画只回应展开、切换、执行状态，尊重减少动态效果 |

**组件选型：优先 Fluent UI React v9。** 官方现有 Tree、Toolbar、Menu、Dialog、Field、Tablist 等基础组件，与Windows工程表单和面板更匹配。[官方组件目录](https://fluent2.microsoft.design/components/web/react)

shadcn/ui 的优势是源码可控、组合灵活、扩展生态丰富；但它是一种组件代码分发方式，仍需要团队承担统一密度、状态和样式维护。[shadcn 定位](https://ui.shadcn.com/docs)

当前项目尚无成熟组件体系，建议选择一种作为基础：**Fluent v9＋项目语义token＋必要的分隔面板组件**。不要同时引入 Fluent、shadcn 和多个动画库来拼接页面。CAD容器与工程状态仍由项目实现。

**5．下一步重构与可交给实现会话的约束**

先完成“导入材料→确认条件→查看计算→打开模型→修改后查看影响”这一条完整流程，再推广到其他页面。

建议按责任拆分：

```text
app/              AppShell、布局状态、当前文档与选择
project/          工程树、材料导入、来源查看
conditions/       条件表、草稿、冲突确认
workspace/        文档标签、CAD容器、图纸与结果查看
agent/            会话、上下文、权限请求、操作结果
operations/       后台任务、问题、修订与变更比较
ui/               统一控件与工程专用展示组件
styles/           tokens、theme、各模块样式
```

`main.tsx` 只组装应用；`CommercialView` 拆开宿主状态与显示组件，共用工作区布局。工程身份、选中对象和修订建立明确类型，避免继续依赖全局 `Record<string, any>`。表单草稿与文档视图状态独立于页面挂载；Three.js 场景生命周期与选中高亮分开。

旧设计规范应改为指向唯一规范，避免维护两套冲突要求。以下内容可直接放入未来的 `desktop/DESIGN.md`：

```text
1. 工程对象是一级导航；课程步骤只属于具体工程任务。
2. 中央工作内容优先；外围面板贴边、可调整、可折叠并记住布局。
3. 不重复原生CAD已有的特征树、属性栏和工具栏。
4. 切换文档不得丢失草稿、视角、缩放、选择与对话。
5. 条件必须展示值、单位、来源和确认状态；JSON仅进入诊断入口。
6. Agent明确显示绑定工程、对象与修订；用户能添加或移除上下文。
7. 修改显示实际差异与影响；取消、撤销、恢复旧修订使用准确名称。
8. 结果状态绑定条件和修订；过期成果不可显示为当前有效成果。
9. 同类信息优先使用树、列表和表格；图纸缩略图必须来自实际产物。
10. 使用统一组件和语义token；业务组件不随意定义颜色、字号和圆角。
11. 不加装饰性网格、渐变、emoji、常驻发光、重复副标题与研发说明。
12. 键盘可完成主流程；焦点清晰；关闭弹层后焦点返回触发位置。
13. CAD焦点内的快捷键由宿主处理，外围命令不得误截获原生编辑操作。
14. 同时交付加载、空白、错误、断连、执行中、过期和恢复状态。
15. 不扩展旧Key配置与模型循环；ACP替代流程完成后移除旧入口。
```

验收不要只看一张首页截图：至少覆盖**材料核对、模型编辑、图纸检查、修改影响**四个状态，在1366×768和1920×1080、Windows 100%／125%／150%缩放下检查；实际完成面板调整、键盘导航、CAD焦点往返、选中对象不跳视角、切页不丢草稿。再由未参与开发的学生试走主流程，记录卡点、误操作和需要提示的位置。


# 图纸如何交给 Agent

学生打开工程内图纸后，在 Agent 面板发送任务即可。当前参考文件会经主进程和绑定工程服务读取；路径不会被当作图纸内容。移除参考后不再自动附加。原文件不修改，外部文件导入时复制到工程独立目录。

## 输入契约与产品取舍

| 输入 | 实际交付 | 边界 |
| --- | --- | --- |
| DXF | `project.read_drawing` 提取模型空间/指定布局中的线、圆、弧、多段线（含 bulge）、样条、文字和 DIMENSION；块参照按变换展开 | 保留 INSUNITS、坐标系、测量值、dimlfac、公差/覆盖文字和已存显示文字；不把文字覆盖值默认为真实几何。未支持实体显式列出 |
| 矢量 PDF | 提取每页线条、矩形、曲线路径、文字和字符位置，给出含数字的尺寸候选 | PDF 通常没有 CAD 尺寸对象；候选与被标注几何的关联仍由 Agent 判断，页面 pt 不是零件 mm。图号、比例不能误作尺寸 |
| 扫描/混合 PDF | 上述提取结果加图片区域及缺字提示 | 不做 OCR；图片部分需视觉 Agent 查看学生提供的页面截图，或导入人工核对的尺寸资料 |
| PNG/JPEG/WebP | ACP `image` 内容块；也可由视觉 Agent 调用 `project.read_image` | 初始化 image 声明只记录，不再阻止用户发送。可在窗口的“会话模型”通过 session/set_config_option 切换模型，再实际发送标准图片块；Agent 拒收时保留响应。模型确实无视觉时，改选视觉模型或提供核对后的尺寸说明。MCP 图片也不能让文本模型获得视觉 |
| JSON/TXT（也可选工程中的 MD/YAML/SVG） | `project.read_file` 返回实际文本和文件 SHA-256 | 人工尺寸资料不计为自动识图；SVG 传源文本，不宣称完成 CAD 尺寸解析 |

**产品决定：本轮不增加工作台侧视觉模型调用。** 学生在既有 dsh/WorkBuddy 内配置或选择模型，凭据和账单继续由该 Agent 管理。工作台仅做确定性文件解析与协议传输（含标准 ACP 会话模型选择），不增加 Key 管理或第二个模型推理循环。即使另建视觉服务能复用外部凭据，仍会引入另一路计费和工具权限，本轮没有必要。

**工程语义决定：PDF 提取与尺寸解释分开。** 提取器不会自动把 pt 换算成 mm，不猜测图纸比例，也不承诺从任意 PDF 得到已确认的尺寸关系。未关联、栅格内容、轮廓字体、未支持 DXF 实体和单位缺失均在结果中保留。Agent 必须先列出已标注、推导、假设和缺失项，再按 m/rad 建模。

公共工具新增只读 `project.read_drawing(path, page=1, layout="Model", offset=0, limit=200)`，`limit` 最大 500。返回来源哈希、页数/布局、原始坐标说明、warnings、items、total_items、next_offset。首次发送附当前文件第一页/布局的首批结果；Agent 继续分页读取，不能把首批当整份图纸。工具使用原工程路径约束和收据链，切换工程即使绑定失效。MCP 新增 `gongke://drawing-input` 说明资源，说明同时进入 server instructions，避免依赖 Agent 主动发现资源。

窗口内部 `agent.prompt(text, referencePaths?)` 第二参数扩展为当前工程参考文件。图片仍发标准 image；矢量解析结果和文本资料作为普通 ACP text 传入，不要求 Agent 支持 embeddedContext。没有修改 ACP 公共协议、CAD 修订、工作副本或写入结果未知时查询原操作的契约。发送准备失败时保留图纸页和任务文字；进入 prompting 后再切到模型区。

依赖：复用 `ezdxf`；新增 `pdfplumber>=0.11,<0.12` 到 app/dev/desktop extras，读取 PDF 图形和文字；打包收集 pdfminer 字符映射数据。解析库不会执行文件中的指令。大文件可按页/条目读取，结果不静默截断。

## 模型调研（2026-11-03）

不能只按显示名称判定模型能力，还需区分官方服务、Agent 模型目录和 ACP 声明。

| 本机 dsh 列表项 | 官方服务当前能力 | 本轮实际证据 |
| --- | --- | --- |
| `deepseek-v4-flash` | 旧名称仍被接受，但旧模型已退役，官方 API 路由到支持视觉的 DeepSeek-V4.1-Flash-1017 | 第二轮选中此项，ACP image=false。因此失败点是当前 Agent 路由的能力声明，不能认定服务端模型本身不会读图 |
| DeepSeek-V4.1-Flash，ID `deepseek-flash` | 支持图文输入 | 第五轮隔离启动配置 + session/set_config_option + 实际 ACP 图片已成功；9 个数值读对 8 个，仍发生尺寸及贯通关系误判 |
| DeepSeek-V4-Pro，ID `deepseek-v4-pro` | 官方 API 明确不支持视觉 | 不应通过手工伪造 image 声明尝试绕过 |

来源：[DeepSeek 模型表及旧名称映射](https://api-docs.deepseek.com/quick_start/pricing/)、[Vision](https://api-docs.deepseek.com/guides/vision/)、[官方 dsh 默认模型目录](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/llm/llm-deepseek/src/models.ts)。调研读取了当日官方网页和本机公开源码；源码不等于已安装版本的运行验证。

dsh 官方配置支持第三方视觉模型：在 dsh **Settings → Models → Add model provider** 选择内置供应商（如 Anthropic/OpenAI/Moonshot），或添加自定义模型 API，填写服务端点/协议/模型；Key 仅在 dsh 内配置。自定义模型需在 Input types 勾选 Image（前提是供应商实际支持），pi-ai 配置对应 `input: [text, image]`，DeepSeek 适配器对应 `inputModalities`。直接使用官方 DeepSeek 时优先选择已声明视觉的 `deepseek-flash`，不覆盖整个模型目录，不更改现有凭据。选择模型会保存为新会话默认；工作台可通过 `session/set_config_option` 选中该项，实际发送图片检验；若 Agent 的 ACP 层仍依据初始化能力拒收，则保留错误，另行重连验证。配置声明不是网络能力测试。依据：[dsh 官方模型配置指南](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/user/guide/providers.md)。

WorkBuddy 支持图片，但取决于选中模型。[桌面官方模型配置](https://www.codebuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Model) 列出 Hy3、GLM-5v-Turbo、Kimi-K2.6 等支持图片，桌面的 DeepSeek-V4-Flash/Pro 只标思考；[移动端模型页](https://www.codebuddy.cn/docs/workbuddyapp/features/Model) 却把这两个 DeepSeek 显示名标为视觉，文档存在平台差异，不能用其推断官方 Pro API 支持图片。[桌面更新日志](https://www.codebuddy.cn/docs/workbuddy/Changelog) 也明确对无图片能力的模型提示切换。工作台接入仍以具体 Agent 的 ACP 声明和实际收图为准，本轮未实测 WorkBuddy ACP 图片链路。

解析依据：[ezdxf Dimension](https://ezdxf.readthedocs.io/en/stable/dxfentities/dimension.html) 明确 measurement 是未应用线性缩放的实测值；[pdfplumber](https://github.com/jsvine/pdfplumber) 提供线/曲线/字符位置，明确不提供 OCR。没有依据这些 API 宣称自动恢复完整工程语义。

## 第四轮前的行为调整

第三轮证实验收脚本因 dsh 工具名的规范化哈希后缀误拦正常读操作。脚本现在仅限定工具来自绑定工程的 `mcp__gongke__` 命名空间，允许全部只读与已有工程写工具；不按固定工具名、顺序或读写粒度做第二次筛选。外部文件、参考体、任意代码和原件写入仍受既有执行端约束。原生结果验收与生成过程分开，不能以还没达到最终验收条件为由中途拒绝工具。

移除工作台两处 image capability 本地拒绝，是为了处理 session 模型切换后初始化声明不再反映当前模型的情况。实际请求记录内容块类型、图片字节数/SHA-256、原始能力声明、当前 configOptions；base64 不重复写入日志，原图片保存在本地工程。失败响应保留 code/message/data，不把发送请求等同于 Agent 已看到图。官方 [Session Config Options](https://agentclientprotocol.com/protocol/v1/session-config-options) 要求发送选项的实际 value，并以返回的 configOptions 更新会话。

本机公开 dsh 源码 `packages/acp/acp/src/content.ts` 在 imageEnabled=false 时明确抛出 `inline image prompts were not advertised by this connection`；`index.ts` 在 initialize 时计算该值，prompt 时仍传入它。这是需要实际验证的已知源码限制，不能提前伪装成真实试验结果，也不据此把图改成文字路径。

第四轮真实验证进一步定位：会话切换成功后，dsh 仍在 ACP 图片准入返回 -32602（`inline image prompts were not advertised by this connection`），模型未收到该图。第五轮 vision 试验改用官方 ACP plugin 启动配置，在 initialize 前指定 deepseek-official/deepseek-flash，再执行会话选模和实际图片验证。工作台不伪造能力声明，不修改全局 dsh 或自建 Key 管理；当前该启动覆盖仅用于隔离试验，尚未将未验收的新默认模型推广给所有学生。详见 [逐轮证据与命令](agent-modeling-trial.md)。

## 第五轮后的局部复读

真实 vision 把底板 8 读成 6，并将贯通槽解释为盲槽；模型自查通过只证明实体符合它自己的读图假设。引导现在分别要求读图核实与实体核实：小字看不清时复读局部，孔槽是否贯通以剖面/视图关系为依据，不从阴影独自下结论；无法确认则保留不确定项。

`project.read_image(path, crop?, scale=1)` 新增局部读取：crop 为源图像素 `[left, top, right, bottom]`（右下不含），scale 为 1–4 整数。最近邻放大只复制像素，不补画或识别内容。原文件不改；`sha256` 仍标识原文件，`content_sha256` 标识实际图片块，并返回 source_pixels/crop/scale/pixels。裁图仍作为标准 MCP image block 返回，所有路径检查沿用绑定工程。工作台不调用另一个视觉服务或管理 Key。复用已有 Pillow，并将它列入 app/dev 依赖。

### 矢量 PDF 实测与取舍（第七轮）

本地 SOLIDWORKS 2018 导出的 A3 PDF 已验证文字与矢量提取。PDF 仍不是带尺寸关联的 CAD 文件：文字、引线、视图位置交给 Agent 解释，页面 pt 不能直接当 mm，矢量绘制的 Ø 等符号不一定在文字层中。没有自建视觉服务或 Key 管理。

按字符变换矩阵分方向组词，修正向上阅读的 `17` 被默认顺序提成 `71` 的问题；默认 `detail=drawing` 返回几何与单词，避免再次重复所有字符。需要核对字体/方向时显式用 `detail=characters`。实现依据 [pdfplumber 的方向与文字提取 API](https://github.com/jsvine/pdfplumber#extracting-text)。只解析任务页，试验的单页摘录、渲染和原文件哈希均放在本地 `out/`，不提交版权资料。

照片尺寸看不清时放大不会增加原始信息；引导明确区分标注、推导、假设，避免反复读同一像素后把比例估计当作确认尺寸。P6 的裁边与空间语义缺口仍须更清晰的原图或人工确认。

**可行。Windows 首版建议采用“下载官方 dsh Desktop → 用户在 dsh 中填写 Key → 构想引擎启动其内置 ACP 命令”的路线。**学生不必安装 Node，也不必操作终端；暂时不需要我们自行打包运行时。

以下截至 **2026-11-03**，依据官方文档、发布元数据及当前工作区源码；未修改仓库。

1. **发行方式、依赖与 ACP**

| 项目 | 核实结果 |
|---|---|
| npm | 官方包 `@deepseek-ai/dsh`；当前 `latest` 为 **0.2.1-rc.5**，仍是预发布版 |
| npm 安装／升级 | `npm install -g @deepseek-ai/dsh@0.2.1-rc.5`；升级时换成经过验证的版本 |
| Node | rc.5 源码声明 `^22.19.0 \|\| >=24.0.0`；当前 master 已提高到 `>=24.9.0`，不能混用版本要求 |
| pnpm | 源码开发固定 `11.28.5`；npm 基本启动不要求学生另装 pnpm，插件管理会用到 |
| Windows | 官方提供 **Windows x64 Desktop EXE 安装包**，自带运行时及 pnpm；本次未确认 Windows ARM64 原生桌面包 |
| ACP | `dsh --profile acp`，通过 stdin/stdout 通信；无需启动 Web 服务 |
| 独立 CLI 二进制 | 未找到官方单文件 `dsh.exe` 发行；Desktop 的 `dsh.cmd` 调用随应用携带的 Electron 运行时 |

来源：[npm 元数据](https://registry.npmjs.org/@deepseek-ai/dsh/latest)、[rc.5 依赖要求](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.2.1-rc.5/package.json)、[CLI 文档](https://github.com/deepseek-ai/deepseek-harness/blob/master/apps/cli/README.md)、[Desktop 文档](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.2.1-rc.5/apps/desktop/README.md)。

**体积暂不能给可靠总数。**npm 元数据中的 `75,972 bytes` 只是启动包解压体积，不含依赖；Windows 安装包下载量、安装后占用及首次运行增量，本次未取得可验证数字，不能据此宣称 dsh 很轻。Desktop 支持应用内更新，其 CLI 随 Desktop 一起升级。

2. **自动下载、随包分发与校验**

- **dsh 本体采用 MIT**，允许复制、分发、修改及商业使用，须保留版权和许可声明。
- **完整安装包不能只按 MIT 判断。**官方第三方清单明确保留各依赖许可，其中含 MPL-2.0 组件及采用单独条款的可选组件。自行随包分发，需要核对实际携带的依赖、声明及相应源码提供义务。[MIT](https://github.com/deepseek-ai/deepseek-harness/blob/master/LICENSE)、[第三方许可清单](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.2.1-rc.5/THIRD_PARTY_NOTICES.md)
- 官方 Windows 下载入口是 **[dsh-latest-windows-x64.exe](https://download.deepseek.com/desktop/dsh-latest-windows-x64.exe)**，发布文档明确指定该地址；不必假设安装包一定挂在 GitHub Releases。[官方发布说明](https://github.com/deepseek-ai/deepseek-harness/blob/master/apps/desktop/publishing/README.md)

建议构想引擎维护一份**已验证版本清单**，记录版本、平台、官方版本化下载 URL、大小和摘要。下载后校验哈希、Windows Authenticode 签名及版本，再安装；不要把可变的 `latest` 地址当作固定版本保证。官方更新 feed 带二进制地址及 SHA-512；npm 路线则校验 `dist.integrity`，并锁定依赖，不能只锁最外层包。

3. **Key 与模型如何配置**

用户操作入口是 **dsh → Settings → Models → DeepSeek → 输入 API Key → 保存**；也可启动 `dsh web`，在系统浏览器中的 dsh 页面完成。没有查到需要采用的 `dsh login` 式 API Key 交互命令。[模型配置指南](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/user/guide/providers.md)

- Key 文件：`$DSH_HOME/.credentials.yaml`，默认 Windows 为 `%USERPROFILE%\.dsh\.credentials.yaml`。
- 普通配置：`$DSH_HOME/profiles/<profile>/cordis.patch.yml`。
- 默认凭据优先级：**已保存 Key → 启动环境 `DEEPSEEK_API_KEY` → 工程 `.env` → dsh home `.env`**。
- Desktop 和 ACP 使用同一个 `DSH_HOME` 时，可由 dsh 自己读取共享凭据，构想引擎无需读取或复制文件。[凭据规则](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/credentials/credentials-local/README.md)、[rc.5 基础配置](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.2.1-rc.5/packages/bundle/base/cordis.patch.yml)

**ACP `authenticate` 不能代替上述配置。**官方返回 `authMethods: []`，`authenticate` 直接成功，不校验平台 Key。模型可通过 ACP 的 `session/set_config_option` 选择，建议从返回的可用列表选择 `deepseek-flash`；不要假定 Desktop 中的模型选择会自动成为 ACP 的选择。[ACP 契约](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/acp/acp/README.md)

构想引擎只需打开 dsh、展示操作说明、接收连接结果；**不提供 Key 输入框，不读取剪贴板，不把 Key 写入启动参数、环境配置或日志**。也不要承诺凭据经过系统钥匙串加密：官方默认是文件存储。

4. **平台注册、实名、充值与费用**

建议引导顺序：

**[开放平台](https://platform.deepseek.com/)注册／登录 → 按平台提示完成认证 → [余额与充值](https://platform.deepseek.com/balance) → [API Keys](https://platform.deepseek.com/api_keys)创建 Key → 用户自行粘贴到 dsh。**

官方说明支持手机号或邮箱注册并验证；用户协议要求按页面提示实名注册。但**当前实名认证所需材料、是否强制绑定中国大陆手机号、最低充值额、付款方式，本次未能进入登录后的实际表单核实**。不要在引导中写死“必须身份证认证”或“最低充值 10 元”。[官方隐私政策](https://platform.deepseek.com/downloads/DeepSeek%20隐私政策.pdf)、[用户协议](https://platform.deepseek.com/downloads/DeepSeek%20用户协议.pdf)

学生可能卡在验证码、邮箱域名限制、认证失败、充值未到账，以及误以为网页登录成功就已经配置了 API。相应问题应跳转至[官方帮助](https://static.deepseek.com/faq/index.html?lang=zh)，保留“稍后继续”。

目前 Flash 每百万 token：未命中缓存输入 **1／2 元**、输出 **4／8 元**，分别对应空闲／高峰时段。因此，假设一次任务累计 **10 万输入＋1 万输出**，约 **0.14／0.28 元**；这是用量示例，Agent 多轮调用会继续累加。Search、Fetch 各 **0.005 元／成功请求**。首次充值建议选择平台允许的小额，不承诺固定任务次数。[官方价格](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)

5. **无 Node 电脑的安装选择**

**首版选官方 Desktop。**它已经解决运行时、原生依赖、Key 配置界面及更新问题；安装后可直接定位：

`<安装目录>\resources\runtime\cli\bin\dsh.cmd`

调用它不要求 Desktop 窗口保持打开，也不必先让学生注册 PATH。[官方启动脚本](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.2.1-rc.5/apps/desktop/cli/dsh.cmd)

“构想引擎携带私有 Node＋固定版本 npm 依赖＋打开 dsh Web 配置”技术上可行，但需要我们承担 Windows 原生依赖、打包和升级验证；**这是后续减少额外桌面应用的选项，当前没有必要先做。**

当前仓库还有一个明确缺口：[settings.cts:18](/Users/huaiyi/Documents/gongke-workbench/desktop/electron/acp/settings.cts:18) 只搜索裸命令和 `.exe`，[client.cts:70](/Users/huaiyi/Documents/gongke-workbench/desktop/electron/acp/client.cts:70) 直接 `spawn`。Windows `.cmd` 需要通过 `cmd.exe` 等正确启动，并处理带空格路径。因此现有面板**还不能据此宣称 Windows 即装即用**。[Node 官方说明](https://nodejs.org/api/child_process.html#spawning-bat-and-cmd-files-on-windows)

6. **建议的首次引导**

| 步骤 | 用户看到的操作／成功条件 | 失败提示与动作 |
|---|---|---|
| 检测 | 检查现有 dsh 安装及版本；没有则显示“安装 DeepSeek Harness”，WorkBuddy 放在其他选项 | 已安装但找不到：重新检测／选择安装位置 |
| 同意安装 | 显示来源、版本、实际下载大小和安装位置；用户确认后下载、校验、安装 | 下载失败可重试；校验失败停止安装；空间不足显示所需空间 |
| 开通 API | 提供“注册或登录”“充值”“创建 API Key”三个官方入口 | 验证码、实名、支付问题留在平台解决，可稍后继续 |
| 配置 dsh | 打开 dsh，提示进入 Models 填写 Key；返回点击“已完成，连接” | 缺少 Key：重新打开 dsh 配置，不在工作台索取 Key |
| 建立连接 | 启动 ACP，完成 `initialize`、`session/new`，绑定当前工程 MCP，选择可用模型 | 启动失败显示安装／版本问题；MCP 失败显示工程连接问题 |
| 首次对话 | 用户发送“读取当前工程，告诉我名称和当前状态”；在窗口批准一次只读工程操作 | 401：去 dsh 更新 Key；402：打开充值；429／503：稍后重试 |
| 完成 | 窗口收到真实模型回复，且工程名称、状态与当前工程一致 | 仅握手成功不能标记“配置完成” |

错误映射依据[官方错误码](https://api-docs.deepseek.com/zh-cn/quick_start/error_codes/)。最终还需在**未安装 Node 的干净 Windows x64 环境**走完这条流程，尤其验证安装定位、`.cmd` 启动、共享凭据及首次 MCP 授权。


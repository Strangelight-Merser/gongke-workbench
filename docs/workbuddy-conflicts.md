# WorkBuddy 5.9.3 配置加载与工程专属连接器

## 官方说明与本机实测

2026-11-03 查阅 [WorkBuddy MCP 指南](https://www.codebuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/MCP-Guide)：明确用户级 `~/.workbuddy/mcp.json` 和项目级 `<工程>/.workbuddy/mcp.json`，没有说明同名优先级和外部编辑后的重载保证。[CodeBuddy Code MCP 文档](https://cloud.tencent.com/document/product/1831/137039) 则规定项目根 `.mcp.json` / `mcp.json`；这是另一个客户端的契约，不能直接视为 WorkBuddy 的规则。[连接器规范](https://open.workbuddy.cn/docs/connector) 支持 `command/args/env`，4.22.15 起支持 `cwd`。

本机 V5.9.3 的实际证据保存在 `out/workbuddy-20261103-065546/`：

- 原用户级 `gongke` 是旧 `-P -m gongke_core mcp`，显示 22 个旧工具；当前工程服务 SDK 探针为 29 个只读工具，宿主连通。
- 项目中改为不冲突的 `gongke-1dd0f773059c` 后，退出重开、新建办公及开发任务，均未加载。因此不能把问题仅归因于用户级同名覆盖，也不能宣称已验证合并优先级。
- “专家·技能·连接器 → 连接器 → 自定义连接器 → 添加 MCP”只显示 `/Users/huaiyi/.workbuddy/mcp.json`，未见配置范围或导入项目 MCP 选项（截图 27）。
- 对五种替代路径各放一个独立名称的只读服务：`.mcp.json`、`mcp.json`、`.codebuddy/mcp.json`、`.codebuddy/.mcp.json`、`.workbuddy/.mcp.json`，保留原 `.workbuddy/mcp.json`。退出重开，新建开发任务，选择准确工程目录；信任弹窗明确说受限模式不加载项目配置，已选“正常打开”，界面确认已信任（截图 28）。
- 六个名称仍全部不可见，无工程调用（截图 29）；日志 `projectMcpCount=0`；自定义 MCP 列表仍只有旧 gongke 与 miora，没有待信任项目服务（截图 30）。实验文件已逐字核对后清除，清单留在 `path-experiment.json`。

这些证据确认本机已测试的项目加载路径不生效，足以停止依赖它作为产品接入入口；并不能证明所有版本只读用户级。没有阅读 WorkBuddy 应用包实现代码。接下来需实测用户级新条目，不能把 SDK 探针成功当作 WorkBuddy 成功。

## 产品行为

引导和 CLI 共用用户级安装器，不再生成项目级配置：

1. 每次生成、重连或权限变更先返回 `status=confirmation_required`，包含将写的路径、工程专属名称、完整新条目、旧入口/同名冲突，不写文件，也不展示其他服务的环境变量。
2. 引导解释“其他工作空间也能看到此连接器，但固定绑定本工程、默认只读”。用户点击“同意备份并写入用户配置”，或 CLI 传 `--confirm-user-config` 后才写入。
3. 名称固定为 `gongke-<规范工程路径的 SHA256 前12位>`。该名属于其他服务时使用空闲后缀；绑定本工程的既有专属条目更新原位。其他服务、旧 gongke、顶层字段均保留。
4. 写入前将原文件逐字保存为同目录 `mcp.json.gongke-backup-<uuid>`，权限 0600；首次安装没有原文件时备份空配置。然后原子替换配置，返回 `backup_path` 和 `config_sha256`。损坏 JSON 直接报错，不覆盖。
5. `workbuddy-restore` 仅在当前文件摘要仍匹配本次安装结果时恢复备份；已有后续修改则拒绝，需在保留后续内容的前提下人工撤销专属条目。首次安装的撤销恢复空配置。

```sh
# 预览，不写入，退出码 1 表示等待同意
python -m gongke_app workbuddy --state-dir "$RUN/desktop/state" --project "$RUN/project"
# 获得用户同意后才运行；写权限还需明确增加 --allow-writes
python -m gongke_app workbuddy --state-dir "$RUN/desktop/state" --project "$RUN/project" --confirm-user-config
# 从配置成功结果取两个值；无需运行桌面服务
python -m gongke_app workbuddy-restore --backup /absolute/backup --expected-sha256 HASH
```

## 本机待批准变更与后续验收

本轮尚未写入真实用户配置。拟追加的完整条目在 `out/workbuddy-20261103-065546/user-config-proposal.json`：`gongke-1dd0f773059c`，指向 `/private/tmp/gongke-modeling-venv/bin/python -m gongke_app mcp`，固定本轮 `desktop/state` 和 `project`，显式 cwd/PYTHONPATH，初始不含 `--allow-writes`。保留旧 gongke，不借它执行任何工程操作。

获得同意后，重启 **7658 验收桌面**载入新代码（不动 7115，不重启 FreeCAD），在引导预览并确认用户级写入。退出重开 WorkBuddy，打开自定义连接器，信任/启用该专属服务并核对 `project.current`；新建任务选同一工程。实际生效方式、信任提示、工具清单和真实调用均截图留档。外部编辑自动热重载未获证明，不依赖它。

后续按 [验收清单](workbuddy-validation.md) 完成只读、原图、尺寸、经同意启用写权限、P7 建模、检查、保存与桌面收据。旧项目配置仅为历史证据，不再由产品写入；新提示词必须使用专属名称。

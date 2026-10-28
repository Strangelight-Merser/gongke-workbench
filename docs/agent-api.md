# 给 AI agent 用的接口（MCP）

学生在 FreeCAD 中编辑工程，agent 通过 MCP 读取同一份原生对象、比较轴径、应用修改和提交受限梁复核。
已有任务书设计工具继续提供独立批处理；它们不会读取或修改当前原生工程。

## 启动与接入

MCP 服务器使用**外部 Python 进程**，通过标准输入输出通信；协议实现不需要安装 `mcp` SDK。
FreeCAD 工作台在本机开启带会话令牌的命令桥，文档操作由 FreeCAD 的 Qt 主线程执行。
不要把 build123d/OCP 导入 FreeCAD 进程。外部几何、CalculiX 求解分别保持进程隔离。

先安装工作台，在 FreeCAD 中启用“工科工作台”，再启动 MCP 客户端。可以打开已有受支持轴，或通过 `create_shaft_project` 新建案例。
外部 Python 至少安装项目的核心依赖 `pyyaml`；批处理出图、Word 和 STEP 分别需要 `ezdxf`、`python-docx` 和 `build123d`。
当前原生轴读取与改径不依赖这些批处理导出包。

下面的 `/path/to/GongKeWorkbench` 换成独立工作台安装目录，`/path/to/python` 换成外部 Python 3.11+ 解释器。
`-P` 防止客户端的工作目录遮蔽安装副本；从源码项目内启动客户端时，也会使用指定的安装版本。

**Claude Code**

```
claude mcp add gongke --env PYTHONPATH=/path/to/GongKeWorkbench -- /path/to/python -P -m gongke_core mcp
```

**WorkBuddy、Claude Desktop、Cursor 等（JSON 配置）**

```json
{
  "mcpServers": {
    "gongke": {
      "command": "/path/to/python",
      "args": ["-P", "-m", "gongke_core", "mcp"],
      "env": {"PYTHONPATH": "/path/to/GongKeWorkbench"}
    }
  }
}
```

默认桥接会话文件为 `~/.local/share/gongke/freecad-session.json`。需要指定实例时，FreeCAD 与 MCP 进程设置同一个
`GONGKE_FREECAD_SESSION` 路径。会话令牌由工作台生成，无需写进客户端配置；客户端只连接本机回环地址。

## 当前原生工程工具

| 工具 | 参数 | 行为 |
|---|---|---|
| `create_shaft_project` | 可选 `case`, `task` | 新建并选中原生轴；`teaching` 是三段教学轴，`course_output` 从 coupling 任务书初始化带两个键槽和六处圆角的七段课程输出轴 |
| `get_project_context` | 无 | 返回当前文档 `session_id`、选择及对象身份 |
| `bind_existing_shaft` | `session_id`, `body_name`, `expected_revision`, `engineering`, `operation_id` | 给受支持的现有三段回转轴添加身份和工况映射，保留原生模型；绑定可撤销 |
| `read_engineering_object` | `session_id`, `entity_id` | 从原生命名约束读取尺寸，并返回工程条件、支持范围和结果适用性 |
| `review_current_object` | `session_id`, `entity_id` | 固定当前 CAD 尺寸、材料和载荷复核，不重新选型；结果与对象内容关联并保存在本机 |
| `preview_shaft_change` | `session_id`, `entity_id`, `segment_id`, `diameter_m` | 固定其他条件比较一个候选，返回差异和 `change_id`；不修改 CAD |
| `preview_fillet_change` | `session_id`, `entity_id`, `left_segment_id`, `right_segment_id`, `radius_m` | 比较课程轴右轴承邻接轴肩的圆角增大；返回编辑条件和完整条件校核，不修改 CAD |
| `apply_change` | `session_id`, `change_id`, `operation_id` | 校验工程仍与预览一致，再以一次原生事务应用候选 |
| `undo_last_agent_change` | `session_id`, `operation_id` | 只撤销仍在栈顶的对应操作，不越过后续人工编辑 |
| `save_project` | `session_id`, 可选 `path` | 保存指定文档；新工程提供绝对 `.FCStd` 路径 |
| `run_analysis` | `session_id`, `entity_id` | 读取当前对象快照并提交梁模型任务，返回 `job_id`；不接收外部快照 |
| `get_job` | `job_id` | 返回任务状态、结果、错误及 `applicability` |
| `cancel_job` | `job_id` | 请求取消求解；随后查询任务终态 |

原生工程工具使用 SI 单位：直径与长度为 m，力为 N，转矩为 N·m，应力为 Pa。例：35 mm 的候选写作 `diameter_m: 0.035`。

已有未绑定的 Body 出现在 `get_project_context.unbound_objects` 中。`can_bind` 表示几何与约束是否符合当前接管范围；`segments` 给出实测尺寸和现有约束名。
仅支持完全约束的三段实心台阶剖面加 360° 回转：每段已有具名线长 `Distance` 和绝对半径 `DistanceY` 约束，无表达式、外部引用或其他 Body 特征。对象名、约束名和线编号不要求采用工作台命名。
调用绑定时，`body_name` 使用该条目的 `name`，`expected_revision` 使用本次读取的 `revision`。中途手改会使绑定请求失效。`undo_available: false` 时保留读取能力，绑定和候选写入均拒绝，避免产生无法回滚的部分修改。

`engineering` 必须明确给出 `material`、`supports_m`、`loads`、`torque_points`、`constraints`、`middle_diameter_bounds_m`、`coordinate_system` 和 `source`，不得自动补教学数据。
坐标声明固定为 `body_local_x`：`z_m` 沿 Body 局部 X，`fx_n` 沿局部 Y，`fy_n` 沿局部 Z；载荷与支承使用绝对局部坐标，手改轴段长度不会自动移动它们。工况来源保存为 `declared`，不升级为已核实来源。
简化模型只接收横向集中力和平衡转矩；轴向力、偏心或力偶字段会明确拒绝。绑定产生新对象身份，来宾不能用旧 UUID 或输入直径覆盖 CAD 实际尺寸。
完整工况格式见 [existing_shaft_conditions.json](../examples/existing_shaft_conditions.json)。该文件是明确声明的示例假定；自己的工程必须提供相应材料、工况和来源，不能直接沿用示例数值。

三段教学轴支持改径候选应用。课程输出轴支持右轴承邻接轴肩的圆角增大，轴径修改仍未开放。
圆角候选的 `status: ready` 与 `can_apply: true` 只表示满足本阶段的编辑条件；`validation_scope` 标明范围，`review.status` 仍可为 `blocked`。
半径必须增大、低于相邻台阶及轴段长度，并不超过三家引用的圆角上限；默认案例可从 1 mm 增到 1.2 或 1.5 mm。
三家引用只限制这次局部编辑，未公布的轴肩直径上限继续为 `unknown`，不会据此选定供应商或判定安装合格。
应用时验证整条原生特征链和完整快照，仅目标圆角可变；实际几何失败则中止事务。成功收据中的 `engineering_conclusion` 保留整轴条件结论。
`create_shaft_project({"case":"course_output"})` 使用内置 coupling 任务书；指定 `task` 时仅用来初始化，后续复核读取当前 CAD。
课程对象可在 FreeCAD 中继续手工编辑；分析是否适用取决于实际特征和来源覆盖，不能将条件数值通过说成完整验收通过。

一个典型调用序列如下。示例中的标识必须替换为前一步返回值，不能根据零件中文名称猜测。

```text
create_shaft_project({"case":"teaching"})
get_project_context({})
read_engineering_object({"session_id":"返回的会话", "entity_id":"选中轴的身份"})
review_current_object({"session_id":"返回的会话", "entity_id":"选中轴的身份"})
preview_shaft_change({"session_id":"返回的会话", "entity_id":"选中轴的身份", "segment_id":"返回的开放轴段", "diameter_m":0.035})
apply_change({"session_id":"返回的会话", "change_id":"预览返回的候选", "operation_id":"本次应用的唯一标识"})
save_project({"session_id":"返回的会话", "path":"/absolute/path/shaft.FCStd"})
```

学生已经要求采用某个候选时即可应用。若预览后发生手改，旧候选会被拒绝，应重新读取并预览。
写操作超时不要生成新 `operation_id` 反复提交；先读取当前工程，再用原标识查询原操作收据。
`receipt_only` 表示历史收据，不能代替当前对象状态。原生 Undo 属于当前打开会话；保存重开保证工程可继续编辑，不承诺撤销栈跨会话保留。
`analysis_persisted: false` 表示计算结果未能写入本机结果目录，具体原因见 `persistence_error`。
此时应保留已返回的结果；若 `applied: true`，CAD 修改已经提交，仍可用原 `operation_id` 查询收据和撤销，不能把缓存失败当作修改失败而重新应用。
缓存无法读取或已损坏时，原生对象仍可读取，`analysis` 返回 `missing` 和 `read_error`；成功的绑定或修改收据不会因此丢失。

## 校核范围与结果适用性

名义弯扭应力和挠度检查只描述工具返回的简化模型范围。新增孔槽、删除绑定约束或改变未支持拓扑后，
系统保留学生模型，停止自动应用相关候选。`pass` 不代表实际轴的轴肩应力、疲劳、配合或装配已全部通过。

当前梁任务接受受支持的三段教学轴与七段课程输出轴，固定提交时的快照，通过独立 CalculiX 进程求解，复核梁挠度和转角。
教学轴施加横向载荷；课程轴保留完整集中力（包括 `fz_n`）和轴向力偏心产生的力偶，并检查当前工程声明的刚度控制位置及限值。
课程轴采用阶梯圆截面梁，忽略键槽和圆角过渡对截面的局部影响，不校核圆角局部应力或疲劳。`torque_points` 不进入梁 FEM，不能据此给出扭转结论。
轴段长度手改后，若固定载荷、支承和接口位置尚未重新绑定，课程轴任务会被拒绝。解析对照采用相同的 Timoshenko 梁假设，数值接近不等于实际零件安全。

`review_current_object` 的轴肩疲劳读取实际 `Fillet.Radius`。`fatigue_sections` 保存可计算截面，`fatigue_unsupported_sections` 保存超出当前公式范围的截面；含受阻截面时聚合值仅是已计算部分的最小值。键槽的 `geometry_basis=assumed_keyway_root` 表示槽根半径仍为计算假设，其疲劳状态保留 `blocked`。`fatigue_method_sources` 列出公式来源及尚未核实的范围，不能只看一个安全系数给出整轴通过结论。

原生特征链中任何一处重算失败都会使对象返回 `unsupported`；最终实体缓存仍可显示也不例外。可通过原生 Undo 恢复最后有效工程，再重新读取。课程工程使用完整原生拓扑名称，保留 FreeCAD 的拓扑追踪；不自动重绑或删除学生特征。

任务 `status` 的终态包括 `succeeded`、`failed`、`cancelled`、`interrupted`。
任务成功、工程结论、结果适用性要分别读取：

- `current`：输入与当前受支持对象匹配，计算方法版本也一致；仍需读取任务终态及工程结论。
- `stale`：当前输入或计算方法版本已改变，保留的结果需要重新计算。
- `missing`：源文档、对象或可读取的上下文不可用，不能宣称当前工程通过。
- `unsupported`：当前对象超出该工具的映射范围。

关闭重开后需重新取得 `session_id`。当前轴复核结果保存在本机 `~/.local/share/gongke/results`，通过对象身份、输入内容和校核方法版本判断 `current/stale`；旧方法结果即使几何未变也需重算。
自定义桥接会话路径时，结果目录位于会话文件旁。梁任务保存在同位置的 `runs` 目录，查询时重新关联当前打开且身份唯一的对象。
macOS 上恢复未完成任务时，会先核对原管理进程已退出，再按保存的进程身份清理遗留求解器。`recovery_cleanup` 记录清理结果；身份缺失、不匹配或系统查询失败时为 `unverified`，不能解释为求解器已结束。旧任务标为 `interrupted`，不会自动重新求解。
只把 `.FCStd` 搬到其他电脑不会自动携带这些结果文件。缺少结果不妨碍原生模型编辑，按当前对象重新校核即可。

## 任务书批处理工具

以下工具按任务书重新设计或处理指定导出文件。不能用 `run_design`、`get_report`、`generate_files` 的结果覆盖或描述学生已经修改的原生工程。
命令行 `python -m gongke_core design` 与这些 MCP 工具共享任务书校验和 `delivery` 导出流程。

| 工具 | 作用 |
|---|---|
| `get_task_schema` | 任务书的 JSON Schema：字段含义、单位、默认值、可选值 |
| `get_example_task` | 某种传动方案（coupling / vbelt / bevel / worm / single）的示例任务书 |
| `validate_task` | 检查任务书，列出全部错误 |
| `run_design` | 完成全部设计计算，返回结果摘要、全部校核项和未通过项 |
| `explore_parameter` | 一个参数取多个值分别设计，返回各方案的主要指标，用于选参数 |
| `get_report` | 计算说明书（Markdown），可只取某一章 |
| `lookup_standard` | 查电动机、轴承、平键、模数、齿轮材料、蜗轮材料、齿形系数 |
| `generate_files` | 生成说明书（md/docx）、工程图（DXF/SVG/整套 PDF）、三维模型（STEP）、有限元复核 |
| `check_drawings` | 检查 DXF 图纸中文字重叠、图线穿过文字的位置（命令行：`python -m gongke_core check-drawings 目录`） |

任务书与 `examples/*.yaml` 结构相同，只有 `conveyor`（拉力 N、带速 m/s、卷筒直径 mm）必填。
错误的任务书会以工具错误（`isError: true`）返回逐条说明，agent 可以据此修改后重试。

## 实测

用 Claude Code 只接入这个服务器，给出一句话任务（拉力 4000 N、带速 1.6 m/s、卷筒 450 mm，比较 4 种传动比分配，
选两级大齿轮直径最接近的方案并出图）。agent 依次调用 `get_example_task`、`explore_parameter`、`run_design`、`generate_files`，
得到全部校核通过的方案、说明书和整套图纸，过程中没有人工干预。
这次实测发现对比结果里缺少分度圆直径，已加入 `explore_parameter` 的输出（`d_mm`）。

## Python 直接调用

```python
from gongke_core import api

task = api.example_task("bevel")
task["gears"]["low"]["material1"] = "42CrMo_QT"
print(api.design(task)["failed"])
print(api.explore(task, "ratio_split", [1.2, 1.3, 1.4])["results"])
api.generate(task, "out", step=True)
```


## 交付状态与运行目录

每次调用 `generate_files` 使用新目录或空目录。CLI 允许输入任务书位于该目录，但不会覆盖已有产物；FreeCAD 重复运行时把有 manifest 标记的旧运行移到相邻归档目录。没有 manifest 的旧目录不会自动移动或覆盖。

- `calculation_ok`：本次设计校核是否全部通过。
- `exports_complete`：本次请求的导出是否全部完成。
- `ok`：上述两项通过，且自动图检未发现问题；不代表专业审阅通过。
- `artifacts`：各请求项的完成状态、文件或错误。失败项的残留文件不作为成功交付物。
- `manifest.json`：运行标识、代码与数据摘要、成功文件清单和问题说明。
- `task.json` 保存输入，`normalized_task.json` 保存默认值展开后的内部任务参数（SI 单位）。

`summary.ratios.target_total` 是任务目标总传动比，`total` 是最终实际总比。`shaft_states` 按最终齿数比计算。初选分配仍在说明书里单独说明。

智能体工作流程见 [设计核对与纠错](assistant-workflow.md)。

# 给 AI agent 用的接口（MCP）

工科工作台的全部设计能力同时提供两种用法：

- **人用**：FreeCAD 工作台（图形界面）和命令行 `python -m gongke_core design`。
- **AI 用**：MCP（Model Context Protocol）服务器 `python -m gongke_core mcp`。Claude、Cursor 等 agent 直接调用设计计算、多方案对比和出图，不需要操作图形界面（不需要 computer use）。

三者调用同一套 `gongke_core.api`，结果完全一致。

## 启动与接入

服务器通过标准输入输出通信，只用 Python 标准库实现（不需要安装 mcp 包），FreeCAD 自带的 Python 也能运行。
出图需要 ezdxf，生成 Word 说明书需要 python-docx，三维模型需要 build123d（与工作台相同）。

下面的 `/path/to/gongke-workbench` 换成本仓库所在目录。

**Claude Code**

```
claude mcp add gongke --env PYTHONPATH=/path/to/gongke-workbench -- python3 -m gongke_core mcp
```

**Claude Desktop、Cursor 等（JSON 配置）**

```json
{
  "mcpServers": {
    "gongke": {
      "command": "python3",
      "args": ["-m", "gongke_core", "mcp"],
      "env": {"PYTHONPATH": "/path/to/gongke-workbench"}
    }
  }
}
```

Windows 上 `command` 可以写 FreeCAD 自带的 Python，如 `C:\\Program Files\\FreeCAD 1.0\\bin\\python.exe`，
并把工作台安装依赖时用的目录（FreeCAD 用户数据目录下的 `GongKe\\pylibs-*`）也加进 `PYTHONPATH`。

## 工具

| 工具 | 作用 |
|---|---|
| `get_task_schema` | 任务书的 JSON Schema：字段含义、单位、默认值、可选值 |
| `get_example_task` | 某种传动方案（coupling / vbelt / bevel / worm）的示例任务书 |
| `validate_task` | 检查任务书，列出全部错误 |
| `run_design` | 完成全部设计计算，返回结果摘要、全部校核项和未通过项 |
| `explore_parameter` | 一个参数取多个值分别设计，返回各方案的主要指标，用于选参数 |
| `get_report` | 计算说明书（Markdown），可只取某一章 |
| `lookup_standard` | 查电动机、轴承、平键、模数、齿轮材料、蜗轮材料、齿形系数 |
| `generate_files` | 生成说明书（md/docx）、工程图（DXF/SVG/整套 PDF）、三维模型（STEP）、有限元复核 |

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

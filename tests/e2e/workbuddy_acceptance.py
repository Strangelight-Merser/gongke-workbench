"""读取真实 WorkBuddy 配置的 MCP 探针及任务收据核对；不启动 GUI，不修改工程。"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import traceback
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def load_config(project):
    path = Path.home() / ".workbuddy/mcp.json"
    raw = path.read_bytes()
    servers = json.loads(raw)["mcpServers"]
    from gongke_app.workbuddy import owns
    matches = [(name, value) for name, value in servers.items() if owns(value, project)]
    if len(matches) != 1:
        raise ValueError("需要且只能有一个绑定当前工程的构想引擎服务")
    name, server = matches[0]
    arguments = server["args"]
    bound_project = Path(arguments[arguments.index("--project") + 1]).resolve()
    if bound_project != project:
        raise ValueError(f"配置绑定其他工程：{bound_project}")
    state = Path(arguments[arguments.index("--state-dir") + 1]).resolve()
    return server, state, {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(),
                           "service_name": name, "command": server["command"], "args": arguments,
                           "cwd": server.get("cwd"),
                           "environment_keys": sorted(server.get("env", {}))}


def read_receipt(state, project, task_id, *, response=None, tool=None):
    """只读应用的持久记录；不创建第二个 Application 或改写任务状态。"""
    uri = (state / "tasks.sqlite3").as_uri() + "?mode=ro"
    with sqlite3.connect(uri, uri=True) as database:
        row = database.execute("SELECT record FROM tasks WHERE id=?", (task_id,)).fetchone()
        if row is None:
            raise ValueError(f"任务不存在：{task_id}")
        record = json.loads(row[0])
        record["receipts"] = [json.loads(row[0]) for row in database.execute(
            "SELECT record FROM receipts WHERE task_id=? ORDER BY rowid", (task_id,))]
    if record["task_id"] != task_id or Path(record["project"]).resolve() != project:
        raise ValueError(f"任务身份或所属工程不符：{task_id}")
    if record["status"] != "complete":
        raise ValueError(f"任务尚未成功完成：{task_id}: {record['status']}")
    if not record["receipts"] or any(row["phase"] != "finished" for row in record["receipts"]):
        raise ValueError(f"任务缺少完整收据：{task_id}")
    last = record["receipts"][-1]
    if last["result"] != record["result"]:
        raise ValueError(f"任务结果与末条收据不符：{task_id}")
    if tool is not None and last["command"] != tool:
        raise ValueError(f"收据工具名称不符：{task_id}")
    if response is not None and (response["result"] != record["result"]
                                 or response["status"] != record["status"]
                                 or Path(response["project"]).resolve() != project):
        raise ValueError(f"MCP 回传与服务记录不符：{task_id}")
    return record


async def probe(args, server, state, evidence, stderr):
    from mcp import Client, StdioServerParameters, stdio_client

    # 不补 PYTHONPATH、不更换解释器；实际配置必须能离开源码 cwd 启动。
    with tempfile.TemporaryDirectory(prefix="gongke-workbuddy-probe-") as temporary_cwd:
        cwd = server.get("cwd", temporary_cwd)
        evidence["child_cwd"] = cwd
        evidence["environment_policy"] = "SDK 默认继承环境加配置 env；未注入探针 shell 的其他变量"
        params = StdioServerParameters(command=server["command"], args=server["args"],
                                       env=server.get("env"), cwd=cwd)
        async with Client(stdio_client(params, errlog=stderr)) as client:
            tools = (await client.list_tools()).tools
            evidence["tools"] = [tool.model_dump(mode="json") for tool in tools]
            available = {tool.name: tool for tool in tools}

            async def call(name, arguments):
                if name not in available or not available[name].annotations.read_only_hint:
                    raise ValueError(f"缺少声明为只读的工具：{name}")
                response = await client.call_tool(name, arguments)
                row = {"tool": name, "arguments": arguments,
                       "response": response.model_dump(mode="json")}
                evidence["calls"].append(row)
                payload = response.structured_content
                if response.is_error or not payload or payload.get("status") != "complete":
                    raise ValueError(f"工具调用失败：{name}: {payload}")
                row["service_record"] = read_receipt(state, args.project, payload["task_id"],
                                                     response=payload, tool=name)
                row["receipt_matches"] = True
                return payload["result"]

            await call("project.current", {})
            await call("project.files", {})
            hosts = await call("hosts.list", {})
            freecad = next((host for host in hosts["hosts"] if host["host"] == "freecad"), None)
            evidence["freecad_connected"] = bool(freecad and freecad["connected"])
            if evidence["freecad_connected"]:
                await call("host.context", {"host_id": freecad["host_id"]})
            elif args.require_freecad:
                raise ValueError("FreeCAD 未连接；请先在沙箱外启动宿主并载入构想引擎桥接")
            else:
                evidence["skipped"] = ["FreeCAD 未连接，未调用 host.context；本次仅证明配置与应用 MCP 可用"]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="mode", required=True)
    for name in ("probe", "receipts"):
        sub = commands.add_parser(name)
        sub.add_argument("--project", type=Path, required=True)
        sub.add_argument("--output", type=Path, required=True, help="新 JSON 证据文件，不覆盖已有文件")
        if name == "probe":
            sub.add_argument("--require-freecad", action="store_true")
        else:
            sub.add_argument("--task-id", action="append", required=True,
                             help="人工从 WorkBuddy 工具结果复制；每个 ID 重复一次参数")
    args = parser.parse_args(argv)
    args.project = args.project.expanduser().resolve()
    args.output = args.output.expanduser().resolve()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    evidence = {"mode": args.mode, "project": str(args.project),
                "started_at": datetime.now(timezone.utc).isoformat(), "calls": [],
                "status": "failed", "workbuddy_ui_verified": False,
                "origin": "official_mcp_sdk_probe" if args.mode == "probe" else "operator_supplied_task_ids",
                "scope": "脚本不能证明真实 WorkBuddy 加载或调用；须另附 WorkBuddy 工具结果和桌面任务截图"}
    # 独占创建，避免覆盖上一轮结果；失败也保存已获得的证据。
    with args.output.open("x", encoding="utf-8") as output:
        try:
            server, state, evidence["config"] = load_config(args.project)
            evidence["state_dir"] = str(state)
            if args.mode == "probe":
                log_path = args.output.with_suffix(args.output.suffix + ".stderr.log")
                evidence["stderr_log"] = str(log_path)
                with log_path.open("x", encoding="utf-8") as stderr:
                    asyncio.run(probe(args, server, state, evidence, stderr))
            else:
                evidence["service_records"] = [read_receipt(state, args.project, task_id)
                                                 for task_id in args.task_id]
            evidence["status"] = "passed"
        except Exception as exc:
            evidence["error"] = str(exc)
            evidence["traceback"] = traceback.format_exc()
        evidence["finished_at"] = datetime.now(timezone.utc).isoformat()
        json.dump(evidence, output, ensure_ascii=False, indent=2, allow_nan=False)
        output.write("\n")
    print(json.dumps({"status": evidence["status"], "evidence": str(args.output),
                      "error": evidence.get("error")}, ensure_ascii=False))
    return 0 if evidence["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

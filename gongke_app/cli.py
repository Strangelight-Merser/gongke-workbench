"""打包程序与开发环境共用的绑定工程 CLI。"""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys

from gongke_app.connection import Connection


def main(argv=None):
    parser = argparse.ArgumentParser(prog="gongke-service")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("mcp", "call", "workbuddy", "inspect-revision"):
        command = sub.add_parser(name)
        command.add_argument("--state-dir", type=Path, default=Path.home() / ".local/share/gongke/app")
        command.add_argument("--project", required=True, help="必须与桌面当前工程一致")
        command.add_argument("--allow-writes", action="store_true", help="授权本次连接修改工程，仍受工作副本和路径限制")
        if name == "call":
            command.add_argument("method", help="tools.list 或应用工具名，例如 revision.inspect")
            command.add_argument("--params", default="{}", help="JSON 对象；@file 从文件读取")
        elif name == "workbuddy":
            command.add_argument("--confirm-user-config", action="store_true", help="同意备份并更新用户级 WorkBuddy 配置中的当前工程专属条目")
            command.add_argument("--executable", type=Path, help="显式指定打包后的 gongke-service；默认使用运行中桌面服务的入口和环境")
        elif name == "inspect-revision":
            command.add_argument("--host", choices=["freecad"], default="freecad")
            command.add_argument("--case", type=Path, required=True)
            command.add_argument("--capture", type=Path)
            command.add_argument("--previous", type=Path)
            command.add_argument("--out", required=True, help="工程内尚不存在的相对目录")
    restore = sub.add_parser("workbuddy-restore")
    restore.add_argument("--backup", type=Path, required=True)
    restore.add_argument("--expected-sha256", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "workbuddy-restore":
            from gongke_app.connection import restore_workbuddy
            print(json.dumps(restore_workbuddy(args.backup, args.expected_sha256), ensure_ascii=False))
            return 0
        connection = Connection(args.state_dir)
        if args.command == "workbuddy":
            options = {"executable": str(args.executable.absolute())} if args.executable else {}
            result = connection.request("configure", project=args.project, allow_writes=args.allow_writes, confirm_user_config=args.confirm_user_config, **options)
        else:
            binding = connection.request("bind", project=args.project, allow_writes=args.allow_writes)
            if args.command == "mcp":
                from gongke_app.mcp_server import serve
                asyncio.run(serve(connection, binding))
                return 0
            if args.command == "inspect-revision":
                from gongke_app.mcp_server import call_bound
                parameters = {key: json.loads(getattr(args, key).read_text(encoding="utf-8"))
                              for key in ("case", "capture", "previous") if getattr(args, key) is not None}
                result = asyncio.run(call_bound(connection, binding, "revision.export", {**parameters, "path": args.out}))
                if result["status"] != "complete":
                    print(result["result"].get("error", result["status"]), file=sys.stderr)
                    return 2
                review = result["result"]["review"]
                print(result["result"]["summary"])
                print("检查结果：" + result["result"]["path"])
                return 0 if review["drawing_review"]["status"] == "pass" and review["calculation"]["numerical_status"] == "pass" else 1
            if args.method == "tools.list":
                result = connection.request("tools", binding_id=binding["binding_id"])
            else:
                from gongke_app.mcp_server import call_bound
                parameters = Path(args.params[1:]).read_text(encoding="utf-8") if args.params.startswith("@") else args.params
                result = asyncio.run(call_bound(connection, binding, args.method, json.loads(parameters)))
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 1 if isinstance(result, dict) and result.get("status") in {"failed", "canceled", "interrupted", "confirmation_required"} else 0
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 2

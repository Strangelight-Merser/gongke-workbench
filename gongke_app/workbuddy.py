"""WorkBuddy 用户级工程专属连接器命名与冲突检查。"""
import hashlib
import json
from pathlib import Path
import re


def owns(server, project):
    args = server.get("args", []) if isinstance(server, dict) else []
    return (isinstance(args, list) and "mcp" in args and "--project" in args and "--state-dir" in args
            and args[args.index("--project") + 1:args.index("--project") + 2] == [str(project)])


def selection(project, servers):
    path = Path.home() / ".workbuddy/mcp.json"
    conflicts = []
    for name, server in servers.items():
        args = server.get("args", []) if isinstance(server, dict) else []
        text = " ".join(args) if isinstance(args, list) else str(args)
        legacy = bool(re.search(r"(?:^|\s)-m\s+gongke_core\s+mcp(?:\s|$)", text))
        if name == "gongke" or legacy:
            conflicts.append({"name": name, "reason": "旧工程入口" if legacy else "同名服务", "path": str(path)})
    stem = "gongke-" + hashlib.sha256(str(project).encode()).hexdigest()[:12]
    name = stem
    index = 2
    while name in servers and not owns(servers[name], project):
        conflicts.append({"name": name, "reason": "服务名已占用", "path": str(path)})
        name = f"{stem}-{index}"
        index += 1
    return name, conflicts

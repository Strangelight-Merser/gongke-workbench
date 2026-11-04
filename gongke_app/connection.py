"""MCP/CLI 到正在运行的应用服务的本机连接；不执行领域命令。"""
from __future__ import annotations

import ipaddress
import json
import os
from pathlib import Path
import secrets
from socketserver import TCPServer
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
from uuid import uuid4

from gongke_app.tools import validate, schema, TEXT, BOOL, TASK


def private_json(path, value):
    temporary = path.with_name("." + path.name + "-" + uuid4().hex)
    try:
        with os.fdopen(os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def write_workbuddy(project, state_dir, executable, allow_writes, *, prefix=(), env=None, confirm_user_config=False):
    # venv 的 python 常是符号链接，解析到基础解释器会丢失虚拟环境依赖。
    executable = executable.absolute()
    executable.stat()
    path = Path.home() / ".workbuddy/mcp.json"
    before = path.read_bytes() if path.exists() else None
    value = json.loads(before) if before is not None else {}
    from gongke_app.workbuddy import selection
    servers = value.setdefault("mcpServers", {})
    name, conflicts = selection(project.path, servers)
    args = [*prefix, "mcp", "--state-dir", str(state_dir.resolve()), "--project", str(project.path)]
    if allow_writes:
        args.append("--allow-writes")
    servers[name] = {
        "command": str(executable), "args": args, "cwd": str(project.path),
    }
    if env:
        servers[name]["env"] = env
    result = {"status": "confirmation_required", "path": str(path), "server": servers[name],
              "service_name": name, "conflicts": conflicts, "allow_writes": allow_writes}
    if not confirm_user_config:
        return result
    path.parent.mkdir(parents=True, exist_ok=True)
    backup = path.with_name("mcp.json.gongke-backup-" + uuid4().hex)
    with os.fdopen(os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as stream:
        stream.write(before if before is not None else b'{"mcpServers": {}}\n')
    private_json(path, value)
    import hashlib
    return {**result, "status": "configured", "backup_path": str(backup),
            "config_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def restore_workbuddy(backup, expected_sha256):
    """仅当配置仍是刚安装的版本时恢复备份，避免覆盖后续人工修改。"""
    import hashlib
    path = Path.home() / ".workbuddy/mcp.json"
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected_sha256:
        raise ValueError("WorkBuddy 配置已变化，不能整份恢复；请保留新条目并人工撤销工程连接器")
    data = backup.read_bytes()
    json.loads(data)
    temporary = path.with_name(".mcp-restore-" + uuid4().hex)
    with os.fdopen(os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as stream:
        stream.write(data)
    temporary.replace(path)
    return {"status": "restored", "path": str(path)}


class LoopbackHTTPServer(ThreadingHTTPServer):
    def server_bind(self):
        # 本机端点只使用数字地址；HTTPServer 的反向 DNS 查询会阻塞离线启动。
        TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]


class ConnectionServer:
    def __init__(self, app, state_dir):
        self.app = app
        self.token = secrets.token_urlsafe(32)
        self.path = Path(state_dir) / "service.json"
        connection = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                if (self.path != "/command" or self.headers.get("Origin") is not None
                        or not secrets.compare_digest(self.headers.get("Authorization", ""), "Bearer " + connection.token)):
                    self.send_error(403)
                    return
                try:
                    self.connection.settimeout(30)
                    size = int(self.headers.get("Content-Length", "0"))
                    if not 0 < size <= 8 * 1024 * 1024:
                        raise ValueError("请求大小无效")
                    payload = json.loads(self.rfile.read(size), parse_constant=lambda _: (_ for _ in ()).throw(ValueError("数值必须有限")))
                    result = connection.dispatch(payload)
                    response = {"result": result}
                except Exception as exc:
                    response = {"error": str(exc)}
                body = json.dumps(response, ensure_ascii=False, allow_nan=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.server = LoopbackHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True, name="gongke-connection")
        self.thread.start()
        private_json(self.path, {"url": f"http://127.0.0.1:{self.server.server_port}", "token": self.token, "pid": os.getpid()})

    def dispatch(self, payload):
        validate(payload, schema({"action": TEXT, "params": TASK}, ["action", "params"]))
        action, params = payload["action"], payload["params"]
        if action == "bind":
            validate(params, schema({"project": TEXT, "allow_writes": BOOL}, ["project"]))
            return self.app.bind(**params)
        if action == "tools":
            validate(params, schema({"binding_id": TEXT}, ["binding_id"]))
            return self.app.bound_tools(**params)
        if action == "call":
            validate(params, schema({"binding_id": TEXT, "method": TEXT, "params": TASK, "task_id": TEXT}, ["binding_id", "method", "params", "task_id"]))
            return self.app.bound_call(**params)
        if action in {"task", "cancel"}:
            validate(params, schema({"binding_id": TEXT, "task_id": TEXT}, ["binding_id", "task_id"]))
            return self.app.bound_task(**params, cancel=action == "cancel")
        if action == "configure":
            validate(params, schema({"project": TEXT, "allow_writes": BOOL, "executable": TEXT, "confirm_user_config": BOOL}, ["project", "allow_writes"]))
            with self.app.lock:
                binding = self.app.bind(params["project"], params["allow_writes"])
                self.app.bindings.pop(binding["binding_id"])
                if "executable" in params:
                    return write_workbuddy(self.app.current(), self.app.state_dir, Path(params["executable"]), params["allow_writes"], confirm_user_config=params.get("confirm_user_config", False))
                return self.app.dispatch("mcp.configure", {"allow_writes": params["allow_writes"], "confirm_user_config": params.get("confirm_user_config", False)})
        raise ValueError("未知连接命令")

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.path.unlink(missing_ok=True)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Connection:
    def __init__(self, state_dir):
        try:
            endpoint = json.loads((Path(state_dir) / "service.json").read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise ValueError("应用服务尚未运行，请先打开桌面工程") from None
        parsed = urlsplit(endpoint["url"])
        if (parsed.scheme != "http" or not ipaddress.ip_address(parsed.hostname).is_loopback
                or parsed.port is None or parsed.path not in {"", "/"} or parsed.username or parsed.password
                or parsed.query or parsed.fragment):
            raise ValueError("应用连接只允许本机回环 HTTP 地址")
        self.url = endpoint["url"].rstrip("/") + "/command"
        self.token = endpoint["token"]
        self.opener = build_opener(ProxyHandler({}), NoRedirect())

    def request(self, action, **params):
        payload = json.dumps({"action": action, "params": params}, ensure_ascii=False, allow_nan=False).encode("utf-8")
        request = Request(self.url, data=payload, headers={"Authorization": "Bearer " + self.token, "Content-Type": "application/json"})
        with self.opener.open(request, timeout=30) as response:
            result = json.load(response)
        if "error" in result:
            raise ValueError(result["error"])
        return result["result"]

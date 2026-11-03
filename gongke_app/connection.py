"""MCP/CLI 到正在运行的应用服务的本机连接；不执行领域命令。"""
from __future__ import annotations

import ipaddress
import json
import os
from pathlib import Path
import secrets
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


def write_workbuddy(project, state_dir, executable, allow_writes, *, prefix=(), env=None):
    executable = executable.resolve(strict=True)
    path = project.resolve(".workbuddy/mcp.json")
    value = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    args = [*prefix, "mcp", "--state-dir", str(state_dir.resolve()), "--project", str(project.path)]
    if allow_writes:
        args.append("--allow-writes")
    value.setdefault("mcpServers", {})["gongke"] = {"command": str(executable), "args": args}
    if env:
        value["mcpServers"]["gongke"]["env"] = env
    path.parent.mkdir(parents=True, exist_ok=True)
    private_json(path, value)
    return {"path": str(path), "server": value["mcpServers"]["gongke"], "allow_writes": allow_writes}


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

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
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
            validate(params, schema({"project": TEXT, "allow_writes": BOOL, "executable": TEXT}, ["project", "allow_writes", "executable"]))
            with self.app.lock:
                binding = self.app.bind(params["project"], params["allow_writes"])
                self.app.bindings.pop(binding["binding_id"])
                return write_workbuddy(self.app.current(), self.app.state_dir, Path(params["executable"]), params["allow_writes"])
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

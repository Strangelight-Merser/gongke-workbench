"""通过本机命令桥操作已打开的 FreeCAD 工程，不加载 FreeCAD 或几何内核。"""

from __future__ import annotations

import ipaddress
import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


class NativeBridgeError(RuntimeError):
    """桥接未连接或工程操作被拒绝；错误交由 agent 解释给学生。"""


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # 授权令牌只交给已发现的本机实例，不跟随重定向。
        return None


def _endpoint() -> tuple[str, str]:
    path = Path(os.environ.get("GONGKE_FREECAD_SESSION", "~/.local/share/gongke/freecad-session.json")).expanduser()
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise NativeBridgeError("未连接 FreeCAD：请打开 FreeCAD 并启用工科工作台。") from exc
    except (OSError, ValueError) as exc:
        raise NativeBridgeError("无法读取 FreeCAD 会话文件，请在 FreeCAD 中重新启用工科工作台。") from exc
    try:
        url, token = config["url"], config["token"]
        parsed = urlsplit(url)
        address = ipaddress.ip_address(parsed.hostname or "")
        if (parsed.scheme != "http" or not address.is_loopback or parsed.port is None
                or parsed.username is not None or parsed.password is not None
                or parsed.path not in ("", "/") or parsed.query or parsed.fragment
                or not isinstance(token, str) or not token.strip()):
            raise ValueError("invalid endpoint")
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise NativeBridgeError("FreeCAD 会话地址无效，只允许带端口的本机回环 HTTP 地址。") from exc
    return url.rstrip("/") + "/command", token


def call(method: str, **params):
    """发送一次工程命令；写入失败或超时不会自动重试。"""
    url, token = _endpoint()
    try:
        payload = json.dumps({"method": method, "params": params}, ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise NativeBridgeError("工程命令参数必须是有效 JSON，数值必须有限。") from exc
    request = Request(url, data=payload, method="POST", headers={
        "Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8",
    })
    # 不使用系统代理，工程参数和令牌只发到本机桥接。
    opener = build_opener(ProxyHandler({}), _NoRedirect())
    try:
        with opener.open(request, timeout=30) as response:
            result = json.load(response)
    except HTTPError as exc:
        raise NativeBridgeError(f"FreeCAD 桥接拒绝连接（HTTP {exc.code}），请检查当前工科工作台会话。") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise NativeBridgeError("FreeCAD 桥接未响应。请检查 FreeCAD 是否仍打开；写操作未自动重试，应先读取当前工程状态。") from exc
    except (ValueError, UnicodeError) as exc:
        raise NativeBridgeError("FreeCAD 桥接返回了无效响应。") from exc
    if not isinstance(result, dict) or not isinstance(result.get("ok"), bool):
        raise NativeBridgeError("FreeCAD 桥接响应缺少操作状态。")
    if not result["ok"]:
        error = result.get("error", "工程操作未完成")
        message = error if isinstance(error, str) else json.dumps(error, ensure_ascii=False)
        raise NativeBridgeError(message)
    if "result" not in result:
        raise NativeBridgeError("FreeCAD 桥接响应缺少操作结果。")
    return result["result"]

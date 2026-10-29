"""Streaming Chat Completions tool calls; credentials stay in memory."""
from __future__ import annotations

import ipaddress
import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Provider:
    def __init__(self, base_url, model, api_key):
        if not all(isinstance(value, str) and value.strip() for value in (base_url, model, api_key)):
            raise ValueError("请填写模型服务地址、模型名称和 API Key")
        parsed = urlsplit(base_url)
        try:
            local = ipaddress.ip_address(parsed.hostname or "").is_loopback
        except ValueError:
            local = parsed.hostname == "localhost"
        if (parsed.scheme != "https" and not (parsed.scheme == "http" and local)) or not parsed.hostname:
            raise ValueError("模型服务需使用 HTTPS；本机服务可使用 HTTP")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("服务地址不能包含身份信息、查询参数或片段")
        self.base_url = base_url.rstrip("/")
        self.model, self._key = model, api_key
        self.verified = False

    def status(self):
        return {"configured": True, "base_url": self.base_url, "model": self.model,
                "connection": "已完成模型请求" if self.verified else "未验证；首次请求将连接模型服务"}

    def complete(self, messages, tools, ctx, on_text):
        ctx.check()
        payload = {"model": self.model, "messages": messages, "tools": tools,
                   "tool_choice": "auto", "stream": True}
        request = Request(self.base_url + "/chat/completions", method="POST",
                          data=json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8"),
                          headers={"Content-Type": "application/json", "Authorization": "Bearer " + self._key})
        content, calls = [], {}
        finish_reason = None
        try:
            with build_opener(NoRedirect()).open(request, timeout=45) as response:
                for raw in response:
                    ctx.check()
                    line = raw.decode("utf-8").strip()
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    chunk = json.loads(data)
                    if "error" in chunk:
                        raise ValueError("模型流返回错误；请检查服务状态与模型配置")
                    choices = chunk.get("choices", [])
                    if not choices:
                        continue
                    choice = choices[0]
                    finish_reason = choice.get("finish_reason") or finish_reason
                    delta = choice.get("delta", {})
                    text = delta.get("content")
                    if text:
                        content.append(text)
                        on_text(text)
                    for partial in delta.get("tool_calls", []):
                        index = partial["index"]
                        call = calls.setdefault(index, {"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
                        if partial.get("id"):
                            call["id"] += partial["id"]
                        fn = partial.get("function", {})
                        for key in ("name", "arguments"):
                            call["function"][key] += fn.get(key) or ""
        except HTTPError as exc:
            raise ValueError(f"模型服务请求失败（HTTP {exc.code}）；请检查服务地址、模型与凭据") from None
        except (URLError, TimeoutError, OSError) as exc:
            raise ValueError("模型服务连接失败或超时；本次请求未自动重试") from None
        except (UnicodeError, json.JSONDecodeError, KeyError, TypeError):
            raise ValueError("模型服务返回了无效的工具调用流") from None
        ctx.check()
        if finish_reason not in {"stop", "tool_calls"}:
            raise ValueError("模型响应未完整结束，未执行其中的工具调用")
        message = {"role": "assistant", "content": "".join(content) or None}
        if calls:
            message["tool_calls"] = [calls[index] for index in sorted(calls)]
            if any(not call["id"] or not call["function"]["name"] for call in calls.values()):
                raise ValueError("模型工具调用缺少标识或名称")
        self.verified = True
        return message

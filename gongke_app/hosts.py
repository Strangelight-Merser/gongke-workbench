"""Discover and probe installed Windows CAD named-pipe bridges."""
from __future__ import annotations

from concurrent.futures import Future, TimeoutError
import hashlib
import json
import os
from pathlib import Path
import re
import threading
from uuid import UUID, uuid4

from gongke_core import native_client

READ_METHODS = {"host.info", "host.describe", "document.context", "documents.list", "document.snapshot",
                "parameters.list", "drawing.inspect", "operation.get", "operation.status", "preview.mesh", "selection.get"}
WRITE_METHODS = {"parameter.change", "drawing.update", "document.save_copy", "drawing.export",
                 "document.select", "selection.set", "drawing.edit_text", "drawing.move_dimension_text", "drawing.import_dxf", "document.open", "document.activate", "operation.cancel"}
COPY_METHODS = {"document.save_copy", "drawing.import_dxf"}


def _fingerprint(method, params):
    # Native copy parameters are strings and integer revisions. Newtonsoft also
    # escapes these three line separators in its default compact JSON output.
    canonical = json.dumps(params, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    for character in ("\u0085", "\u2028", "\u2029"):
        canonical = canonical.replace(character, "\\u" + format(ord(character), "04x"))
    return hashlib.sha256((method + "\n" + canonical).encode("utf-8")).hexdigest()


def _operation_id(host, value):
    if not isinstance(value, str) or not value:
        raise ValueError("操作 ID 必须是非空字符串")
    return str(UUID(value)) if host == "solidworks" else value


def _host_session(config):
    value = config.get("session_id" if config["host"] == "solidworks" else "instance_id")
    if not isinstance(value, str) or not value:
        raise ValueError("宿主发现信息缺少会话身份，无法确认副本操作归属")
    return value

# These parameter contracts match the shipped native adapters. They travel with
# discovery so the model can construct commands without guessing custom fields.
CONTRACTS = {
    "solidworks": {
        "document.context": {},
        "document.open": {"document_path": "工程内相对 .sldprt/.slddrw 路径", "configuration": "零件配置名；图纸可省略", "operation_id": "UUID"},
        "document.activate": {"document_path": "已打开文件绝对路径", "configuration": "零件配置名；图纸可省略", "operation_id": "UUID"},
        "parameters.list": {"document_path": "当前文档绝对路径", "configuration": "当前零件配置"},
        "parameter.change": {"document_path": "已登记工作副本的绝对路径", "configuration": "当前配置", "session_id": "document.context 的会话", "expected_revision": "当前文档 revision 整数", "operation_id": "UUID", "parameter_name": "parameters.list 中writable=true的线性或直径name", "expected_value": "当前实际值（m）", "value": "目标值（m）"},
        "preview.mesh": {"document_path": "当前零件绝对路径", "configuration": "当前配置"},
        "selection.get": {"document_path": "当前文档绝对路径", "configuration": "零件配置"},
        "selection.set": {"document_path": "当前文档绝对路径", "configuration": "零件配置", "persistent_reference": "实际快照返回的引用", "expected_revision": "当前revision整数", "operation_id": "UUID"},
        "drawing.inspect": {"document_path": "当前图纸绝对路径"},
        "drawing.update": {"document_path": "已登记图纸副本绝对路径", "session_id": "会话", "expected_revision": "当前图纸revision整数", "operation_id": "UUID"},
        "document.save_copy": {"document_path": "原文档绝对路径", "configuration": "零件配置；图纸可省略", "session_id": "会话", "expected_revision": "原文档当前revision整数", "operation_id": "UUID", "output_path": "新工作副本工程相对路径，零件.sldprt或图纸.slddrw", "output_part_path": "复制图纸时必填，关联零件的新相对.sldprt路径", "expected_part_revision": "复制图纸时必填，关联零件当前revision整数"},
        "drawing.export": {"document_path": "当前图纸绝对路径", "session_id": "会话", "expected_revision": "当前图纸revision整数", "operation_id": "UUID", "sheet": "当前原生图纸页名", "output_path": "新的工程相对.dxf路径"},
        "operation.get": {"operation_id": "原操作UUID"},
    },
    "autocad": {
        "documents.list": {},
        "document.snapshot": {"document_id": "documents.list中的ID", "offset": "可选整数，默认0", "limit": "可选1到5000整数", "expected_revision": "分页offset>0时必填"},
        "document.open": {"path": "工程内相对.dwg路径", "operation_id": "UUID"},
        "document.select": {"document_id": "当前文档ID", "expected_revision": "当前revision整数", "handle": "快照实体handle", "operation_id": "UUID"},
        "drawing.edit_text": {"document_id": "已登记工作副本ID", "expected_revision": "当前revision整数", "handle": "TEXT或MTEXT的handle", "text": "新纯文本；不支持尺寸显示覆盖", "operation_id": "UUID"},
        "drawing.move_dimension_text": {"document_id": "已登记工作副本ID", "expected_revision": "当前revision整数", "handle": "原生DIMENSION的handle", "position": "WCS工程单位的[x,y,z]数值数组", "operation_id": "UUID"},
        "drawing.import_dxf": {"source_path": "工程内已存在的相对.dxf路径", "target_path": "新的工程相对.dwg路径", "operation_id": "UUID"},
        "document.save_copy": {"document_id": "原文档ID", "expected_revision": "当前revision整数", "target_path": "新的工程相对.dwg路径", "operation_id": "UUID"},
        "operation.status": {"operation_id": "原操作UUID"},
        "operation.cancel": {"operation_id": "要取消的原操作UUID；只能停止未开始操作"},
    },
}


class Hosts:
    def __init__(self, directory=None):
        self.directory = Path(directory) if directory else Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local/share")) / "Gongke/hosts"
        self.locks = {}
        self.lock = threading.Lock()

    def discover(self):
        found = []
        for path in sorted(self.directory.glob("*.json")):
            try:
                item = json.loads(path.read_text(encoding="utf-8"))
                if item["host"] not in {"solidworks", "autocad"} or not re.fullmatch(r"[A-Za-z0-9_-]+", item["pipe_name"]):
                    continue
                if not isinstance(item.get("token"), str) or not item["token"]:
                    continue
                found.append({**item, "host_id": path.stem})
            except (OSError, ValueError, KeyError, TypeError):
                continue
        return found

    def list(self):
        freecad = {"host_id": "freecad", "host": "freecad", "transport": "loopback_http"}
        try:
            freecad.update(connected=True, info=native_client.call("get_project_context"))
        except native_client.NativeBridgeError as exc:
            freecad.update(connected=False, error=str(exc))
        result = [freecad]
        for config in self.discover():
            public = {key: value for key, value in config.items() if key != "token"}
            public["parameter_contracts"] = CONTRACTS[config["host"]]
            try:
                method = "host.info" if config["host"] == "solidworks" else "host.describe"
                public["info"] = self._request(config, method, {}, timeout=2)
                if isinstance(public["info"], dict) and "error" in public["info"]:
                    raise ValueError("宿主探测失败：" + str(public["info"]["error"]))
                public["connected"] = True
                public["capabilities"] = public["info"].get("capabilities", [])
            except Exception as exc:
                public.update(connected=False, error=str(exc))
            result.append(public)
        return {"platform_supported": os.name == "nt", "hosts": result}

    def _prepare_command(self, host_id, method, params, project):
        if method not in READ_METHODS | WRITE_METHODS:
            raise ValueError("该宿主命令未获应用层支持")
        config = next((item for item in self.discover() if item["host_id"] == host_id), None)
        if config is None:
            raise ValueError("未发现该 CAD 宿主，请在原生软件中加载桥接插件")
        caps = config.get("capabilities", [])
        if isinstance(caps, list) and caps and method not in caps:
            raise ValueError("该宿主未声明此命令能力")
        params = dict(params)
        if method in WRITE_METHODS:
            if not params.get("operation_id"):
                raise ValueError("原生操作必须包含唯一 operation_id")
            keys = ["path", "output_path", "output_part_path", "source_path", "target_path", "file_path"]
            if method == "document.open":
                keys.append("document_path")
            for key in keys:
                if key not in params:
                    continue
                is_input = method == "document.open" or (method == "drawing.import_dxf" and key == "source_path")
                target = project.resolve(params[key], exists=is_input)
                if not is_input:
                    if target.exists():
                        raise ValueError("输出文件已存在，请选择新的工作副本")
                    target.parent.mkdir(parents=True, exist_ok=True)
                params[key] = str(target)
            if config["host"] == "solidworks" and method in {"parameter.change", "drawing.update"}:
                if not project.is_working_copy(params.get("document_path"), "solidworks"):
                    raise ValueError("请先通过工作台保存并打开新的原生工作副本，再执行修改")
        operation = None
        if method in COPY_METHODS:
            operation = {"operation_id": _operation_id(config["host"], params["operation_id"]),
                         "host": config["host"], "host_id": host_id, "host_session": _host_session(config),
                         "method": method, "params": params, "fingerprint": _fingerprint(method, params),
                         "request_id": uuid4().hex, "state": "unregistered"}
            project.remember_copy_operation(operation)
        return config, params, operation

    def command(self, host_id, method, params, project):
        try:
            config, params, operation = self._prepare_command(host_id, method, params, project)
        except (ValueError, TypeError, OSError) as exc:
            return {"error": {"code": "command_not_submitted", "outcome": "not_applied", "message": str(exc)}}
        if config["host"] == "autocad" and method in {"drawing.edit_text", "drawing.move_dimension_text"}:
            # A transport failure stays unknown. A successful read proving this
            # is an original document is a known refusal before any edit is sent.
            context = self._request(config, "documents.list", {})
            if "error" in context:
                return context
            document = next((item for item in context.get("documents", []) if item["document_id"] == params.get("document_id")), None)
            if not document or not project.is_working_copy(document.get("path"), "autocad"):
                return {"error": {"code": "command_not_submitted", "outcome": "not_applied",
                                  "message": "请先通过工作台保存并打开新的 DWG 工作副本，再执行修改"}}
        if operation is not None:
            result = self._request(config, method, params, request_id=operation["request_id"])
            self._register_copy_result(operation, result, project)
        else:
            result = self._request(config, method, params)
            if method == ("operation.get" if config["host"] == "solidworks" else "operation.status"):
                self._recover_copy(config, params, result, project)
        return result

    @staticmethod
    def _register_copy_result(operation, result, project):
        if not isinstance(result, dict) or "error" in result:
            return
        host, params, operation_id = operation["host"], operation["params"], operation["operation_id"]
        if host == "solidworks":
            if result.get("status") != "saved":
                return
            if params.get("output_part_path"):
                copies = result.get("working_copies", [])
                expected = {Path(params["output_path"]).resolve(), Path(params["output_part_path"]).resolve()}
                if (any(result.get(flag) is not True for flag in ("references_verified", "parameter_values_verified", "source_state_preserved", "reopen_verified"))
                        or not isinstance(copies, list) or len(copies) != 2
                        or any(not isinstance(item, dict) or not isinstance(item.get("path"), str) for item in copies)
                        or {Path(item["path"]).resolve() for item in copies} != expected
                        or any(item.get("verified") is not True for item in copies)
                        or not isinstance(result.get("path"), str)
                        or Path(result["path"]).resolve() != Path(params["output_path"]).resolve()):
                    raise ValueError("关联工作副本回执未完整验证两个文件与引用关系；未授予修改资格")
                project.register_copies([(item["path"], item) for item in copies], host, operation_id=operation_id)
                return
            if result.get("file_exists") is not True or type(result.get("errors")) is not int or result["errors"] != 0:
                raise ValueError("原生副本保存回执缺少可靠成功状态；未授予修改资格")
        else:
            if result.get("outcome") != "committed":
                return
            if (result.get("operation_id") != operation_id or result.get("disk_reopen_verified") is not True
                    or result.get("original_preserved") is not True):
                raise ValueError("原生副本保存回执与操作不匹配或未验证文件；未授予修改资格")
            if operation["method"] == "drawing.import_dxf" and result.get("source_path") != params["source_path"]:
                raise ValueError("导入副本回执的源文件不匹配；未授予修改资格")
        target = params.get("output_path") or params.get("target_path")
        project.register_copy(target, host, result, operation_id=operation_id)

    def _recover_copy(self, config, params, result, project):
        operation_id = _operation_id(config["host"], params.get("operation_id"))
        operation = project.copy_operation(operation_id)
        # A successful unrelated operation cannot grant permission to a file.
        if operation is None:
            return
        if (operation["host"] != config["host"] or operation["host_id"] != config["host_id"]
                or operation["host_session"] != _host_session(config)
                or operation["method"] not in COPY_METHODS
                or _operation_id(config["host"], operation["params"].get("operation_id")) != operation_id
                or operation["fingerprint"] != _fingerprint(operation["method"], operation["params"])):
            raise ValueError("副本操作与原请求或宿主会话不匹配；未授予修改资格")
        if not isinstance(result, dict):
            return
        finished = result.get("state") == "finished" if config["host"] == "solidworks" else (
            result.get("status") == "completed" and result.get("outcome") == "committed")
        if not finished:
            return
        if (result.get("operation_id") != operation_id or (config["host"] == "solidworks" and (
                result.get("session_id") != operation["host_session"] or result.get("fingerprint") != operation["fingerprint"]))):
            raise ValueError("宿主回执的操作 ID、会话或命令参数指纹不匹配；未授予修改资格")
        response = result.get("response")
        if not isinstance(response, dict) or "error" in response:
            return
        if response.get("id") != operation["request_id"]:
            raise ValueError("宿主回执与原请求 ID 不匹配；未授予修改资格")
        self._register_copy_result(operation, response.get("result"), project)

    def _request(self, config, method, params, timeout=30, request_id=None):
        if os.name != "nt":
            raise ValueError("该原生桥接需要在 Windows 上运行；发现文件不代表已连接")
        with self.lock:
            lock = self.locks.setdefault(config["host_id"], threading.Lock())
        if not lock.acquire(timeout=timeout):
            raise ValueError("上一次宿主操作尚未返回；请先确认结果，不应重复写入")
        future = Future()
        wire_id = request_id or uuid4().hex

        def transact():
            try:
                import ctypes
                pipe = "\\\\.\\pipe\\" + config["pipe_name"]
                kernel = ctypes.WinDLL("kernel32", use_last_error=True)
                kernel.WaitNamedPipeW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32]
                kernel.WaitNamedPipeW.restype = ctypes.c_int
                if not kernel.WaitNamedPipeW(pipe, int(timeout * 1000)):
                    raise ValueError("CAD 命名管道不可用；请检查插件加载状态")
                payload = {"id": wire_id, "method": method, "params": params, "token": config["token"]}
                with open(pipe, "r+b", buffering=0) as stream:
                    stream.write((json.dumps(payload, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8"))
                    data = bytearray()
                    while len(data) <= 8 * 1024 * 1024:
                        byte = stream.read(1)
                        if byte in {b"", b"\n"}:
                            break
                        data.extend(byte)
                    if len(data) > 8 * 1024 * 1024:
                        raise ValueError("宿主响应超过大小上限")
                reply = json.loads(data)
                if reply.get("id") != wire_id:
                    raise ValueError("宿主响应 ID 不匹配")
                if "error" in reply:
                    future.set_result({"error": reply["error"]})
                else:
                    future.set_result(reply["result"])
            except Exception as exc:
                future.set_exception(exc)
            finally:
                lock.release()
        threading.Thread(target=transact, daemon=True, name="cad-pipe").start()
        try:
            return future.result(timeout=timeout)
        except TimeoutError:
            raise ValueError("宿主操作超时，结果待确认；未自动重试，请查询原 operation_id") from None

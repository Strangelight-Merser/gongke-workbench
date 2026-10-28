"""本机 agent 命令桥。文档访问只在 Qt 主线程，计算在请求线程进行。"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import queue
import secrets
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore

from freecad.gongke import native_shaft


# 校核方法或条件结论改变时递增；模型未变不代表旧方法的结果仍然适用。
REVIEW_METHOD_VERSION = 2


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def _same_values(actual, expected):
    if isinstance(actual, dict) and isinstance(expected, dict):
        return actual.keys() == expected.keys() and all(_same_values(actual[k], expected[k]) for k in actual)
    if isinstance(actual, list) and isinstance(expected, list):
        return len(actual) == len(expected) and all(_same_values(a, b) for a, b in zip(actual, expected))
    if type(actual) in (int, float) and type(expected) in (int, float):
        return math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-15)
    return actual == expected


class DocumentState:
    """会话版本单调增加，包括手改和 Undo；不写入会污染撤销栈的缓存属性。"""

    def __init__(self, results_dir):
        self.sessions = {}
        self.changes = {}
        self.operations = {}
        self.results_dir = Path(results_dir)
        App.addDocumentObserver(self)

    def slotChangedObject(self, obj, prop):
        if prop in ("Label", "Label2", "Visibility"):
            return
        for state in self.sessions.values():
            if obj.Document == state["doc"]:
                state["revision"] += 1

    def slotUndoDocument(self, doc):
        self._edited(doc)

    def slotRedoDocument(self, doc):
        self._edited(doc)

    def slotDeletedDocument(self, doc):
        self.sessions = {sid: s for sid, s in self.sessions.items() if s["doc"] != doc}

    def _edited(self, doc):
        for state in self.sessions.values():
            if state["doc"] == doc:
                state["revision"] += 1

    def _session(self, session_id):
        state = self.sessions.get(session_id)
        if state is None or App.listDocuments().get(state["doc"].Name) != state["doc"]:
            raise ValueError("目标文档会话已关闭或不存在，请重新读取当前工程")
        return state

    def _body(self, state, entity_id):
        matches = [obj for obj in state["doc"].Objects if getattr(obj, "GkEntityId", None) == entity_id]
        if len(matches) != 1:
            raise ValueError("工程对象已删除或身份重复，请重新选择")
        return matches[0]

    def _writable(self, state):
        gui_doc = Gui.getDocument(state["doc"].Name)
        if gui_doc.getInEdit():
            raise ValueError("请先完成当前草图编辑，再应用候选")
        if state["doc"].HasPendingTransaction:
            raise ValueError("当前文档有未结束的编辑事务，请先完成该操作")

    def _context(self, doc):
        if doc is None:
            return {"session_id": None, "objects": [], "selection": [], "unbound_objects": [],
                    "unbound_selection": [], "message": "请打开原生轴工程"}
        sid = next((sid for sid, s in self.sessions.items() if s["doc"] == doc), None)
        if sid is None:
            sid = str(uuid.uuid4())
            self.sessions[sid] = {"doc": doc, "revision": 0}
        state = self.sessions[sid]
        objects = [{"entity_id": obj.GkEntityId, "name": obj.Name, "label": obj.Label,
                    **native_shaft.inspect(obj)} for obj in doc.Objects if hasattr(obj, "GkEntityId")]
        unbound = [{"name": obj.Name, "label": obj.Label, **native_shaft.describe_unbound(obj)}
                   for obj in doc.Objects if obj.TypeId == "PartDesign::Body" and not hasattr(obj, "GkEntityId")]
        selected = []
        unbound_selected = []
        for obj in Gui.Selection.getSelection():
            if obj.Document == doc:
                body = obj if obj.TypeId == "PartDesign::Body" else obj.getParentGeoFeatureGroup()
                if body is not None and hasattr(body, "GkEntityId"):
                    selected.append(body.GkEntityId)
                elif body is not None and body.TypeId == "PartDesign::Body":
                    unbound_selected.append(body.Name)
        return {"session_id": sid, "document": doc.Name, "path": doc.FileName,
                "undo_available": doc.UndoMode == 1,
                "revision": state["revision"], "objects": objects, "selection": list(dict.fromkeys(selected)),
                "unbound_objects": unbound, "unbound_selection": list(dict.fromkeys(unbound_selected))}

    def get_project_context(self):
        return self._context(App.ActiveDocument)

    def bind_existing_shaft(self, session_id, body_name, expected_revision, engineering, operation_id):
        """接管当前已有回转轴；一次事务只加映射，不重建学生模型。"""
        from gongke_core.shaft_binding import prepare_snapshot

        if not isinstance(operation_id, str) or not operation_id.strip():
            raise ValueError("operation_id 必须为非空字符串")
        if type(expected_revision) is not int or expected_revision < 0:
            raise ValueError("expected_revision 必须是读取工程时返回的非负整数")
        state = self._session(session_id)
        key = (session_id, operation_id)
        request_hash = _hash({"body_name": body_name, "revision": expected_revision, "engineering": engineering})
        if key in self.operations:
            prior = self.operations[key]
            if prior.get("kind") != "binding" or prior["request_hash"] != request_hash:
                raise ValueError("operation_id 已用于另一个操作")
            return {**prior["result"], "replayed": True, "receipt_only": True,
                    "message": "此为历史绑定收据；当前状态请重新读取工程"}
        self._writable(state)
        doc = state["doc"]
        if doc.UndoMode != 1:
            raise ValueError("目标文档未启用撤销，不能保证绑定回滚；请启用文档撤销后再绑定")
        if any("Touched" in obj.State for obj in doc.Objects):
            doc.recompute()
        if state["revision"] != expected_revision:
            raise ValueError("工程在读取后已修改，请重新读取再绑定")
        body = doc.getObject(body_name)
        description = native_shaft.describe_unbound(body)
        if not description["can_bind"]:
            raise ValueError(description["reason"])
        snapshot = prepare_snapshot(description, engineering)
        transaction = f"工科绑定轴 {operation_id}"
        doc.openTransaction(transaction)
        try:
            native_shaft.bind_existing(body, snapshot)
            actual_snapshot = native_shaft.read_snapshot(body)
            if not _same_values(actual_snapshot, snapshot):
                raise ValueError("绑定读回与当前尺寸及声明工况不一致，已回滚")
            fingerprint = _hash(actual_snapshot)
            doc.commitTransaction()
        except Exception:
            doc.abortTransaction()
            doc.recompute()
            raise
        result = {"session_id": session_id, "entity_id": snapshot["entity_id"],
                  "revision": state["revision"], "content_hash": fingerprint,
                  "snapshot": actual_snapshot, "supported": True,
                  "analysis": {"applicability": "missing", "result": None},
                  "operation_id": operation_id, "bound": True, "geometry_unchanged": True}
        self.operations[key] = {"kind": "binding", "request_hash": request_hash, "change_id": None,
                                "result": result, "transaction": transaction,
                                "revision": state["revision"], "undone": False}
        return result

    def find_engineering_object(self, entity_id):
        matches = [doc for doc in App.listDocuments().values()
                   for obj in doc.Objects if getattr(obj, "GkEntityId", None) == entity_id]
        if len(matches) != 1:
            raise ValueError("对象尚未打开或同时存在多份，无法唯一关联分析结果")
        context = self._context(matches[0])
        return self.read_engineering_object(context["session_id"], entity_id)

    def create_project(self, snapshot):
        if snapshot.get("scope") not in ("simplified_shaft", "course_shaft_review"):
            raise ValueError("不支持的原生轴案例")
        doc = App.newDocument("CourseShaft" if snapshot["scope"] == "course_shaft_review" else "ShaftStudy")
        doc.UndoMode = 1
        doc.openTransaction("创建原生轴工程")
        try:
            body = native_shaft.create_shaft(doc, snapshot)
            doc.commitTransaction()
        except Exception:
            doc.abortTransaction()
            App.closeDocument(doc.Name)
            raise
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(body)
        Gui.activeDocument().activeView().viewAxonometric()
        Gui.activeDocument().activeView().fitAll()
        return self._context(doc)

    def _result_path(self, entity_id):
        return self.results_dir / f"{hashlib.sha256(entity_id.encode()).hexdigest()}.json"

    def _store_result(self, context, result):
        record = {"entity_id": context["entity_id"], "content_hash": context["content_hash"],
                  "method_version": REVIEW_METHOD_VERSION, "result": result}
        self.results_dir.mkdir(parents=True, exist_ok=True)
        target = self._result_path(context["entity_id"])
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps(record, ensure_ascii=False, allow_nan=False), encoding="utf-8")
        temporary.replace(target)

    def _persist_result(self, context, result):
        try:
            self._store_result(context, result)
        except OSError as exc:
            return {"analysis_persisted": False, "persistence_error": str(exc)}
        return {"analysis_persisted": True}

    def remember_review(self, context, result):
        current = self.read_engineering_object(context["session_id"], context["entity_id"])
        if current.get("content_hash") != context["content_hash"] or current["revision"] != context["revision"]:
            raise ValueError("计算期间工程已修改，请重新复核")
        return {"session_id": context["session_id"], "entity_id": context["entity_id"],
                "content_hash": context["content_hash"], "revision": context["revision"],
                "applicability": "current", "result": result, **self._persist_result(context, result)}

    def read_engineering_object(self, session_id, entity_id):
        state = self._session(session_id)
        self._writable(state)
        if any("Touched" in obj.State for obj in state["doc"].Objects):
            state["doc"].recompute()
        body = self._body(state, entity_id)
        support = native_shaft.inspect(body)
        if not support["supported"]:
            return {"session_id": session_id, "entity_id": entity_id, "revision": state["revision"],
                    "applicability": "unsupported", **support}
        snapshot = native_shaft.read_snapshot(body)
        fingerprint = _hash(snapshot)
        result_path = self._result_path(entity_id)
        analysis = {"applicability": "missing", "result": None}
        try:
            prior = json.loads(result_path.read_text(encoding="utf-8"))
            if not isinstance(prior, dict) or not {"content_hash", "result"} <= prior.keys():
                raise ValueError("校核缓存缺少输入摘要或结果")
            analysis = {"applicability": "current" if prior["content_hash"] == fingerprint and
                        prior.get("method_version") == REVIEW_METHOD_VERSION else "stale", "result": prior["result"]}
        except FileNotFoundError:
            pass
        except (OSError, ValueError, UnicodeError) as exc:
            analysis["read_error"] = str(exc)
        return {"session_id": session_id, "entity_id": entity_id, "revision": state["revision"],
                "content_hash": fingerprint, "snapshot": snapshot, "supported": True,
                "analysis": analysis}

    def remember_preview(self, context, candidate):
        sid, eid = context["session_id"], context["entity_id"]
        current = self.read_engineering_object(sid, eid)
        if current.get("content_hash") != context["content_hash"] or current["revision"] != context["revision"]:
            raise ValueError("计算期间工程已修改，请重新预览")
        cid = str(uuid.uuid4())
        entry = {"context": context, "candidate": candidate}
        self.changes[cid] = entry
        return {"change_id": cid, "session_id": sid, "entity_id": eid,
                "revision": context["revision"], "content_hash": context["content_hash"], **candidate}

    def apply_change(self, session_id, change_id, operation_id):
        if not isinstance(operation_id, str) or not operation_id.strip():
            raise ValueError("operation_id 必须为非空字符串")
        key = (session_id, operation_id)
        if key in self.operations:
            prior = self.operations[key]
            if prior["change_id"] != change_id:
                raise ValueError("operation_id 已用于另一候选")
            return {**prior["result"], "replayed": True, "receipt_only": True,
                    "message": "此为历史操作收据；当前状态请重新读取工程"}
        entry = self.changes.get(change_id)
        if entry is None or entry["context"]["session_id"] != session_id:
            raise ValueError("候选不存在或属于另一文档会话")
        context, candidate = entry["context"], entry["candidate"]
        state = self._session(session_id)
        self._writable(state)
        current = self.read_engineering_object(session_id, context["entity_id"])
        if current["revision"] != context["revision"] or current.get("content_hash") != context["content_hash"]:
            raise ValueError("候选已过期，不能覆盖人工修改；请重新预览")
        if candidate.get("can_apply") is not True:
            raise ValueError("候选不满足其声明的编辑条件，不能应用")
        body = self._body(state, context["entity_id"])
        doc = state["doc"]
        if doc.UndoMode != 1:
            raise ValueError("目标文档未启用撤销，不能保证修改回滚；请启用文档撤销后再应用")
        change = candidate["change"]
        transaction = f"工科圆角 {operation_id}" if change["parameter"] == "fillet_radius_m" else f"工科改径 {operation_id}"
        doc.openTransaction(transaction)
        try:
            if change["parameter"] == "fillet_radius_m":
                native_shaft.set_fillet_radius(body, change["left_segment_id"], change["right_segment_id"], change["new_value"])
            elif change["parameter"] == "diameter_m":
                native_shaft.set_diameter(body, change["segment_id"], change["new_value"])
            else:
                raise ValueError("不支持的编辑参数")
            actual_snapshot = native_shaft.read_snapshot(body)
            if not _same_values(actual_snapshot, candidate["candidate_snapshot"]):
                raise ValueError("实际修改与候选不一致，已回滚")
            fingerprint = _hash(actual_snapshot)
            doc.commitTransaction()
        except Exception:
            doc.abortTransaction()
            doc.recompute()
            raise
        actual = {"entity_id": context["entity_id"], "content_hash": fingerprint, "snapshot": actual_snapshot}
        analysis = deepcopy(candidate["review"])
        if actual["snapshot"]["scope"] == "course_shaft_review":
            # 完整原生读回与候选一致后，条件计算才可关联到当前实体。
            analysis["geometry_basis"] = "current_parameters_declared_features"
            analysis["basis_verification"] = "native_readback_matches_candidate"
        result = {"operation_id": operation_id, "entity_id": context["entity_id"],
                  "revision": state["revision"], "content_hash": actual["content_hash"], "change": change,
                  "analysis": analysis, "applied": True}
        if actual["snapshot"]["scope"] == "course_shaft_review":
            result.update(validation_scope=candidate["validation_scope"], engineering_conclusion=analysis["status"])
        self.operations[key] = {"change_id": change_id, "result": result, "transaction": transaction,
                                "revision": state["revision"], "undone": False}
        result.update(self._persist_result(actual, analysis))
        return result

    def undo_last_agent_change(self, session_id, operation_id):
        state = self._session(session_id)
        self._writable(state)
        operation = self.operations.get((session_id, operation_id))
        if operation is None or operation["undone"]:
            raise ValueError("没有可撤销的对应操作")
        doc = state["doc"]
        names = list(doc.UndoNames)
        if state["revision"] != operation["revision"] or not names or names[0] != operation["transaction"]:
            raise ValueError("该操作之后已有编辑，不能跨过人工操作撤销")
        doc.undo()
        doc.recompute()
        operation["undone"] = True
        return {"undone": True, "operation_id": operation_id, "revision": state["revision"]}

    def save_project(self, session_id, path=None):
        state = self._session(session_id)
        self._writable(state)
        doc = state["doc"]
        if path:
            target = Path(path).expanduser()
            if not target.is_absolute() or target.suffix.lower() != ".fcstd":
                raise ValueError("保存路径必须是 .FCStd 绝对路径")
            if target.exists() and str(target) != doc.FileName:
                raise ValueError("目标文件已存在，请另选路径，避免覆盖另一工程")
            if not target.parent.is_dir():
                raise ValueError("保存目录不存在")
            doc.saveAs(str(target))
        elif doc.FileName:
            doc.save()
        else:
            raise ValueError("新工程请指定 .FCStd 保存路径")
        if not Path(doc.FileName).is_file():
            raise ValueError("工程未成功保存")
        return {"saved": True, "path": doc.FileName, "revision": state["revision"]}


class Bridge:
    def __init__(self, endpoint=None):
        self.queue = queue.Queue()
        self.token = secrets.token_urlsafe(32)
        self.jobs = None
        self.jobs_lock = threading.Lock()
        self.endpoint = Path(endpoint or os.environ.get("GONGKE_FREECAD_SESSION",
                              "~/.local/share/gongke/freecad-session.json")).expanduser()
        self.state = DocumentState(self.endpoint.parent / "results")
        bridge = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                if self.path != "/command" or self.headers.get("Authorization") != f"Bearer {bridge.token}":
                    self.send_error(403)
                    return
                try:
                    size = int(self.headers.get("Content-Length", "0"))
                    if not 0 < size <= 65536:
                        raise ValueError("命令大小无效")
                    request = json.loads(self.rfile.read(size))
                    result = bridge.dispatch(request["method"], request.get("params", {}))
                    payload = {"ok": True, "result": result}
                except Exception as exc:
                    payload = {"ok": False, "error": str(exc)}
                data = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.drain)
        self.timer.start(20)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.endpoint.parent.mkdir(parents=True, exist_ok=True)
        data = {"url": f"http://127.0.0.1:{self.server.server_port}", "token": self.token, "pid": os.getpid()}
        fd = os.open(self.endpoint, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
        os.chmod(self.endpoint, 0o600)
        with os.fdopen(fd, "w") as handle:
            json.dump(data, handle)

    def main_call(self, method, **params):
        reply = queue.Queue(maxsize=1)
        request = {"method": method, "params": params, "reply": reply, "state": "pending", "lock": threading.Lock()}
        self.queue.put(request)
        try:
            ok, value = reply.get(timeout=25)
        except queue.Empty:
            with request["lock"]:
                if request["state"] == "pending":
                    request["state"] = "cancelled"
                    raise ValueError("FreeCAD 尚未开始执行，请求已取消；请检查模态对话框")
            raise ValueError("FreeCAD 操作已开始但尚未返回，结果未知；读取工程后用原 operation_id 查询，勿重复新建操作")
        if not ok:
            raise ValueError(value)
        return value

    def drain(self):
        while not self.queue.empty():
            request = self.queue.get_nowait()
            with request["lock"]:
                if request["state"] == "cancelled":
                    continue
                request["state"] = "running"
            try:
                result = getattr(self.state, request["method"])(**request["params"])
                request["reply"].put((True, result))
            except Exception as exc:
                request["reply"].put((False, str(exc)))

    def dispatch(self, method, params):
        if method in ("run_analysis", "get_job", "cancel_job"):
            from gongke_core.shaft_jobs import JobManager, METHOD_VERSION
            with self.jobs_lock:
                if self.jobs is None:
                    self.jobs = JobManager(self.endpoint.parent / "runs")
            if method == "run_analysis":
                context = self.main_call("read_engineering_object", **params)
                if not context.get("supported"):
                    raise ValueError(context.get("reason", "当前对象不受支持"))
                source = {k: context[k] for k in ("session_id", "entity_id", "revision", "content_hash")}
                return self.jobs.start(context["snapshot"], source)
            record = self.jobs.cancel(params["job_id"]) if method == "cancel_job" else self.jobs.get(params["job_id"])
            source = record["source_context"]
            try:
                current = self.main_call("find_engineering_object", entity_id=source["entity_id"])
                applicability = "unsupported" if not current.get("supported") else (
                    "current" if current["content_hash"] == source["content_hash"]
                    and record.get("method_version") == METHOD_VERSION else "stale")
            except ValueError:
                applicability = "missing"
            return {**record, "applicability": applicability}
        if method in ("preview_shaft_change", "preview_fillet_change", "review_current_object"):
            context = self.main_call("read_engineering_object", session_id=params["session_id"], entity_id=params["entity_id"])
            if not context.get("supported"):
                raise ValueError(context.get("reason", "当前对象不受支持"))
            if method == "preview_fillet_change":
                from gongke_core.course_shaft import preview_fillet_change
                candidate = preview_fillet_change(context["snapshot"], params["left_segment_id"],
                                                  params["right_segment_id"], params["radius_m"])
                return self.main_call("remember_preview", context=context, candidate=candidate)
            if context["snapshot"]["scope"] == "course_shaft_review":
                from gongke_core.course_shaft import assess_diameter_change as preview, review
            else:
                from gongke_core.shaft_review import preview, review
            if method == "review_current_object":
                return self.main_call("remember_review", context=context, result=review(context["snapshot"]))
            candidate = preview(context["snapshot"], params["segment_id"], params["diameter_m"])
            return self.main_call("remember_preview", context=context, candidate=candidate)
        if method not in ("create_project", "get_project_context", "bind_existing_shaft", "read_engineering_object", "apply_change", "undo_last_agent_change", "save_project"):
            raise ValueError("未知工程命令")
        return self.main_call(method, **params)

    def close(self):
        self.timer.stop()
        if self.jobs is not None:
            for job_id in list(self.jobs._jobs):
                self.jobs.cancel(job_id)
        self.server.shutdown()
        self.server.server_close()
        App.removeDocumentObserver(self.state)
        if self.endpoint.exists() and json.loads(self.endpoint.read_text()).get("token") == self.token:
            self.endpoint.unlink()


_bridge = None


def start(endpoint=None):
    global _bridge
    if _bridge is None:
        _bridge = Bridge(endpoint)
        Gui.getMainWindow().destroyed.connect(_bridge.close)
    return _bridge

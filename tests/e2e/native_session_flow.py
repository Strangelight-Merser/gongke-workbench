"""真实 FreeCAD 会话与独立 stdio MCP 客户端的连续验收。

在 FreeCAD 主线程调用 start(output_dir, external_python)。测试线程只操作
MCP 子进程；学生手改、原生 Undo、关闭重开等本地动作由 Qt 定时器执行。
不会打开另一个 GUI，也不向命令桥暴露测试回调。完成后留下可编辑工程。
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
import queue
import select
import subprocess
import threading
import time
import traceback
import uuid


ROOT = Path(__file__).resolve().parents[2]
_runs = []


class _MCP:
    def __init__(self, python, endpoint, output, record):
        env = dict(os.environ)
        # FreeCAD 启动器的 Python/Qt 环境不能污染独立计算解释器。
        for name in ("PYTHONHOME", "PYTHONPATH", "LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH",
                     "QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH"):
            env.pop(name, None)
        env["PYTHONPATH"] = str(ROOT)
        self.root = Path(os.environ.get("GONGKE_MCP_ROOT", ROOT)).resolve()
        env["PYTHONPATH"] = str(self.root)
        env["GONGKE_FREECAD_SESSION"] = str(endpoint)
        self.stderr = (output / "native_session_mcp_stderr.txt").open("w", encoding="utf-8")
        self.process = subprocess.Popen([str(python), "-m", "gongke_core", "mcp"], cwd=self.root,
                                        env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=self.stderr, text=True, encoding="utf-8", bufsize=1)
        self.record = record
        self.counter = 0

    def rpc(self, method, params=None, notification=False):
        request = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            request["params"] = params
        if not notification:
            self.counter += 1
            request["id"] = self.counter
        self.record("request", request)
        self.process.stdin.write(json.dumps(request, ensure_ascii=False, allow_nan=False) + "\n")
        self.process.stdin.flush()
        if notification:
            return None
        readable, _, _ = select.select([self.process.stdout], [], [], 45.0)
        if not readable:
            raise TimeoutError(f"MCP {method} 45 秒内未响应")
        line = self.process.stdout.readline()
        if not line:
            raise RuntimeError(f"MCP 子进程结束，返回码 {self.process.poll()}")
        response = json.loads(line)
        self.record("response", response)
        assert response.get("id") == request["id"], "MCP 响应身份不匹配"
        assert "error" not in response, response.get("error")
        return response["result"]

    def tool(self, name, expect_error=False, **arguments):
        result = self.rpc("tools/call", {"name": name, "arguments": arguments})
        assert bool(result.get("isError")) == expect_error, {"tool": name, "result": result}
        if expect_error:
            return result
        if "structuredContent" in result:
            return result["structuredContent"]
        return json.loads(next(item["text"] for item in result["content"] if item["type"] == "text"))

    def close(self):
        if self.process.poll() is None:
            self.process.stdin.close()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.terminate()
                self.process.wait(timeout=5)
        self.stderr.close()


class _Session:
    def __init__(self, output, python):
        import FreeCAD as App
        import FreeCADGui as Gui
        from PySide import QtCore
        from freecad.gongke import bridge, native_shaft

        self.output = Path(output).resolve()
        self.output.mkdir(parents=True, exist_ok=True)
        if (self.output / "native_session.json").exists():
            raise FileExistsError("验收目录已有完整结果，请使用新目录保留历史证据")
        self.python = Path(python)
        if not self.python.is_file():
            raise FileNotFoundError(str(self.python))
        self.bridge = bridge.start()
        self.doc = App.ActiveDocument
        if self.doc is None:
            raise ValueError("先创建或打开原生教学轴工程")
        candidates = [obj for obj in self.doc.Objects if hasattr(obj, "GkEntityId") and native_shaft.supported(obj)]
        if len(candidates) != 1:
            raise ValueError("验收文档应包含且仅包含一根受支持的原生教学轴")
        self.entity_id = candidates[0].GkEntityId
        self.version = App.Version()
        self.doc.UndoMode = 1
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(candidates[0])
        self.calls = queue.Queue()
        self.events = []
        self.checks = []
        self.done = False
        self.run_id = uuid.uuid4().hex
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self._poll)
        self.timer.start(20)
        self.thread = threading.Thread(target=self._execute, name="gongke-native-session", daemon=True)
        self.thread.start()

    def _record(self, kind, payload):
        event = {"sequence": len(self.events) + 1, "kind": kind, "payload": payload}
        self.events.append(event)
        with (self.output / "native_session_trace.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False, allow_nan=False) + "\n")

    def _local(self, action, **arguments):
        reply = queue.Queue(maxsize=1)
        self.calls.put((action, arguments, reply))
        ok, result = reply.get(timeout=30)
        self._record("local_action", {"action": action, "arguments": arguments, "ok": ok, "result": result})
        if not ok:
            raise RuntimeError(result)
        return result

    def _poll(self):
        # 仅由 Qt 主线程消费本地动作，不在这里等待线程或 MCP 响应。
        while not self.calls.empty():
            action, arguments, reply = self.calls.get_nowait()
            try:
                reply.put((True, self._perform(action, **arguments)))
            except Exception:
                reply.put((False, traceback.format_exc()))
        if self.done:
            self.timer.stop()

    def _body(self):
        matches = [obj for obj in self.doc.Objects if getattr(obj, "GkEntityId", None) == self.entity_id]
        assert len(matches) == 1, "当前原生轴身份丢失或重复"
        return matches[0]

    def _perform(self, action, **arguments):
        import FreeCAD as App
        import FreeCADGui as Gui

        if action == "native_undo":
            names = list(self.doc.UndoNames)
            assert names and names[0] == arguments["transaction"], "Undo 栈顶不是测试操作，停止避免跨过人工修改"
            self.doc.undo()
            self.doc.recompute()
            return {"undone_transaction": arguments["transaction"]}
        if action == "manual_diameter":
            body = self._body()
            mapping = next(item for item in json.loads(body.GkMetadata)["dimensions"]
                           if item["segment_id"] == "middle")
            index = next(i for i, item in enumerate(body.GkSketch.Constraints) if item.Name == mapping["radius"])
            self.doc.openTransaction("学生手动改径")
            try:
                # 直接操作学生也会编辑的原生约束，明确不经过 native_shaft.set_diameter。
                body.GkSketch.setDatum(index, App.Units.Quantity(f"{arguments['diameter_m'] * 500.0} mm"))
                self.doc.recompute()
                self.doc.commitTransaction()
            except Exception:
                self.doc.abortTransaction()
                raise
            return {"constraint": mapping["radius"], "diameter_m": arguments["diameter_m"]}
        if action == "close_reopen":
            path = arguments["path"]
            old_name = self.doc.Name
            Gui.Selection.clearSelection()
            App.closeDocument(old_name)
            self.doc = App.openDocument(path)
            self.doc.UndoMode = 1
            App.setActiveDocument(self.doc.Name)
            body = self._body()
            Gui.Selection.addSelection(body)
            return {"old_document": old_name, "document": self.doc.Name, "entity_id": body.GkEntityId}
        if action == "add_unsupported_feature":
            body = self._body()
            self.doc.openTransaction("学生添加未支持特征")
            try:
                feature = body.newObject("PartDesign::Feature", "StudentFeature")
                feature.Label = "学生新增特征（验收）"
                feature.Shape = body.GkRevolution.Shape.copy()
                body.Tip = feature
                self.doc.recompute()
                self.doc.commitTransaction()
            except Exception:
                self.doc.abortTransaction()
                raise
            return {"feature_name": feature.Name, "retained": self.doc.getObject(feature.Name) is not None}
        if action == "feature_exists":
            return self.doc.getObject(arguments["name"]) is not None
        if action == "capture_view":
            Gui.Selection.clearSelection()
            view = Gui.getDocument(self.doc.Name).activeView()
            view.viewAxonometric()
            view.fitAll()
            path = self.output / "native_session.png"
            view.saveImage(str(path), 1600, 1000, "White")
            assert path.is_file() and path.stat().st_size > 0, "原生视图截图未生成"
            Gui.Selection.addSelection(self._body())
            return str(path)
        raise ValueError(f"未知本地验收动作 {action}")

    @staticmethod
    def _diameter(result):
        return next(segment["diameter_m"] for segment in result["snapshot"]["segments"]
                    if segment["segment_id"] == "middle")

    def _execute(self):
        client = None
        started = time.time()
        try:
            client = _MCP(self.python, self.bridge.endpoint, self.output, self._record)
            initialized = client.rpc("initialize", {"protocolVersion": "2025-11-25", "capabilities": {},
                                    "clientInfo": {"name": "gongke-native-session-test", "version": "1"}})
            client.rpc("notifications/initialized", notification=True)
            tools = client.rpc("tools/list")
            assert "preview_shaft_change" in [tool["name"] for tool in tools["tools"]]
            context = client.tool("get_project_context")
            assert self.entity_id in context["selection"]
            sid = context["session_id"]
            identity = {"session_id": sid, "entity_id": self.entity_id}
            before = client.tool("read_engineering_object", **identity)
            assert math.isclose(self._diameter(before), 0.04), "必须从新建 40 mm 教学轴开始"
            self.checks.append("stdio_mcp_reads_selected_native_object")

            bad = client.tool("preview_shaft_change", **identity, segment_id="middle", diameter_m=0.032)
            good = client.tool("preview_shaft_change", **identity, segment_id="middle", diameter_m=0.036)
            assert bad["status"] == "fail" and good["status"] == "pass", "候选校核结论与基准不符"
            after_previews = client.tool("read_engineering_object", **identity)
            assert math.isclose(self._diameter(after_previews), 0.04), "预览不应修改当前工程"
            client.tool("apply_change", expect_error=True, session_id=sid, change_id=bad["change_id"],
                        operation_id=f"rejected-{self.run_id}")
            self.checks.append("failed_candidate_rejected_and_preview_read_only")

            operation_id = f"accepted-{self.run_id}"
            applied = client.tool("apply_change", session_id=sid, change_id=good["change_id"], operation_id=operation_id)
            assert applied["applied"]
            actual = client.tool("read_engineering_object", **identity)
            assert math.isclose(self._diameter(actual), 0.036)
            assert actual["analysis"]["applicability"] == "current"
            self.checks.append("accepted_candidate_changes_same_native_object")

            self._local("native_undo", transaction=f"工科改径 {operation_id}")
            undone = client.tool("read_engineering_object", **identity)
            assert math.isclose(self._diameter(undone), 0.04)
            self.checks.append("native_undo_restores_original_dimension")
            self._local("manual_diameter", diameter_m=0.038)
            client.tool("apply_change", expect_error=True, session_id=sid, change_id=good["change_id"],
                        operation_id=f"stale-{self.run_id}")
            manual = client.tool("read_engineering_object", **identity)
            assert math.isclose(self._diameter(manual), 0.038)
            assert manual["analysis"]["applicability"] == "stale"
            self.checks.append("manual_edit_read_back_and_old_candidate_rejected")

            reviewed = client.tool("review_current_object", **identity)
            assert reviewed["applicability"] == "current" and reviewed["result"]["status"] == "pass"
            job = client.tool("run_analysis", **identity)
            deadline = time.monotonic() + 30
            while True:
                job = client.tool("get_job", job_id=job["job_id"])
                if job["status"] in ("succeeded", "failed", "cancelled", "interrupted"):
                    break
                assert time.monotonic() < deadline, "真实梁求解未在 30 秒内完成"
                time.sleep(0.2)
            assert job["status"] == "succeeded" and job["applicability"] == "current", job
            self.checks.append("current_snapshot_review_and_real_beam_job")

            project = self.output / "session_shaft.FCStd"
            if project.exists():
                project = self.output / f"session_shaft_{self.run_id}.FCStd"
            saved = client.tool("save_project", session_id=sid, path=str(project))
            assert saved["saved"]
            self._local("close_reopen", path=saved["path"])
            client.tool("read_engineering_object", expect_error=True, **identity)
            reopened_context = client.tool("get_project_context")
            assert reopened_context["session_id"] != sid
            assert self.entity_id in reopened_context["selection"]
            identity = {"session_id": reopened_context["session_id"], "entity_id": self.entity_id}
            reopened = client.tool("read_engineering_object", **identity)
            assert math.isclose(self._diameter(reopened), 0.038)
            assert reopened["analysis"]["applicability"] == "current"
            assert client.tool("get_job", job_id=job["job_id"])["applicability"] == "current"
            self.checks.append("save_reopen_preserves_identity_and_rejects_closed_session")

            self._local("manual_diameter", diameter_m=0.036)
            assert client.tool("read_engineering_object", **identity)["analysis"]["applicability"] == "stale"
            assert client.tool("get_job", job_id=job["job_id"])["applicability"] == "stale"
            self._local("native_undo", transaction="学生手动改径")
            assert client.tool("get_job", job_id=job["job_id"])["applicability"] == "current"
            self.checks.append("reopened_result_follows_manual_edit_and_undo")

            feature = self._local("add_unsupported_feature")
            unsupported = client.tool("read_engineering_object", **identity)
            assert not unsupported["supported"] and unsupported["applicability"] == "unsupported"
            assert self._local("feature_exists", name=feature["feature_name"]), "学生特征被意外删除"
            self._local("native_undo", transaction="学生添加未支持特征")
            assert not self._local("feature_exists", name=feature["feature_name"])
            recovered = client.tool("read_engineering_object", **identity)
            assert recovered["supported"] and math.isclose(self._diameter(recovered), 0.038)
            self.checks.append("unsupported_feature_preserved_and_native_undo_restores_support")
            saved = client.tool("save_project", session_id=identity["session_id"])
            image = self._local("capture_view")
            result = {"ok": True, "run_id": self.run_id, "freecad_version": self.version,
                      "mcp_protocol": initialized["protocolVersion"], "external_python": str(self.python),
                      "mcp_working_directory": str(client.root),
                      "entity_id": self.entity_id, "session_id": identity["session_id"],
                      "saved_project": saved["path"], "image": image, "checks": self.checks,
                      "elapsed_seconds": time.time() - started, "events": self.events,
                      "scope": "真实 stdio MCP 与原生 FreeCAD 操作；手改由本地 Sketcher API 回调模拟，未验证可访问性点击或完整课程轴。"}
            (self.output / "native_session.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            error = traceback.format_exc()
            (self.output / "native_session_error.txt").write_text(error, encoding="utf-8")
            (self.output / "native_session_failed.json").write_text(
                json.dumps({"ok": False, "run_id": self.run_id, "checks": self.checks, "events": self.events,
                            "error": error}, ensure_ascii=False, indent=2), encoding="utf-8")
        finally:
            try:
                if client is not None:
                    client.close()
            finally:
                self.done = True


def start(output_dir, external_python):
    """由现有 FreeCAD GUI 主线程启动；返回对象供宏保留，不等待完成。"""
    session = _Session(output_dir, external_python)
    _runs.append(session)
    return session

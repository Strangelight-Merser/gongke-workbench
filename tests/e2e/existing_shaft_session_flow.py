"""已有学生轴的真实 GUI/MCP 接管；本地原生 API 只模拟学生操作。"""

from copy import deepcopy
import json
import math
from pathlib import Path
import sys
import time
import traceback

sys.path.insert(0, str(Path(__file__).parent))
from existing_shaft_smoke import create_student_shaft
from native_session_flow import _MCP, _Session, _runs


ENGINEERING = {
    "coordinate_system": "body_local_x",
    "source": "已有轴接管验收的解析 fixture：显式假定简支位置、局部载荷、材料许用值及编辑区间，非实际课程设计认证。",
    "material": {"name": "解析测试材料", "young_modulus_pa": 2e11,
                 "allowable_stress_pa": 6e7, "source": "解析测试假定，非工程材料牌号"},
    "supports_m": [.025, .175], "loads": [{"z_m": .1, "fx_n": 0.0, "fy_n": -1000.0}],
    "torque_points": [], "constraints": {"alpha": .6, "max_deflection_m": .0001},
    "middle_diameter_bounds_m": [.032, .05],
}


class ExistingShaftSession(_Session):
    def __init__(self, output, python):
        target = Path(output).resolve()
        if target.exists() and any(target.iterdir()):
            raise FileExistsError("请使用新的空验收目录，保留已有工程与运行证据")
        super().__init__(output, python)

    def _student_body(self):
        body = self.doc.getObject(self.student_body_name)
        assert body is not None and body.TypeId == "PartDesign::Body", "学生原有 Body 丢失"
        return body

    def _student_state(self):
        return self._state_for_body(self._student_body())

    @staticmethod
    def _state_for_body(body):
        from freecad.gongke import native_shaft

        sketch = next(obj for obj in body.Group if obj.TypeId == "Sketcher::SketchObject")
        revolution = next(obj for obj in body.Group if obj.TypeId == "PartDesign::Revolution")
        middle = next(i for i, constraint in enumerate(sketch.Constraints) if constraint.Name == "my_radius_2")
        return {
            "metadata_properties": sorted(name for name in body.PropertiesList if name.startswith("Gk")),
            "middle_diameter_m": sketch.getDatum(middle).Value / 500.0,
            "native_state": {
                "names": [obj.Name for obj in (body, sketch, revolution)],
                "labels": [obj.Label for obj in (body, sketch, revolution)],
                "document_objects": [(obj.Name, obj.TypeId) for obj in body.Document.Objects],
                "placement": [list(obj.Placement.toMatrix().A) for obj in (body, sketch, revolution)],
                "geometry": [[list(g.StartPoint), list(g.EndPoint)] for g in sketch.Geometry],
                "constraints": native_shaft._constraint_signature(sketch),
                "dimensions": [sketch.getDatum(i).Value for i, c in enumerate(sketch.Constraints) if c.Name],
                "volume": body.Shape.Volume,
            },
        }

    def _perform(self, action, **arguments):
        import FreeCAD as App
        import FreeCADGui as Gui

        if action == "create_student":
            self.doc = App.newDocument("StudentShaft" + self.run_id[:8])
            self.doc.UndoMode = 1
            body = create_student_shaft(self.doc)
            self.student_body_name = body.Name
            self.entity_id = None
            for obj in body.Group:
                obj.Visibility = obj == body.Tip
            body.Visibility = True
            App.setActiveDocument(self.doc.Name)
            Gui.Selection.clearSelection()
            Gui.Selection.addSelection(body)
            return self._student_state()
        if action == "student_state":
            return self._student_state()
        if action == "activate_other_document":
            self.other_doc = App.newDocument("OtherStudentShaft" + self.run_id[:8])
            self.other_doc.UndoMode = 1
            body = create_student_shaft(self.other_doc)
            self.other_body_name = body.Name
            App.setActiveDocument(self.other_doc.Name)
            Gui.Selection.clearSelection()
            Gui.Selection.addSelection(body)
            return {"document": self.other_doc.Name, "state": self._state_for_body(body)}
        if action == "other_document_state":
            return self._state_for_body(self.other_doc.getObject(self.other_body_name))
        if action == "activate_student_document":
            App.setActiveDocument(self.doc.Name)
            Gui.Selection.clearSelection()
            Gui.Selection.addSelection(self._student_body())
            return {"document": self.doc.Name}
        if action == "student_undo_mode":
            self.doc.UndoMode = arguments["mode"]
            return {"undo_mode": self.doc.UndoMode}
        if action == "adopt_binding":
            body = self._student_body()
            assert body.GkEntityId == arguments["entity_id"]
            self.entity_id = body.GkEntityId
            return {"entity_id": self.entity_id, "body_name": body.Name}
        if action == "manual_student_diameter":
            body = self._student_body()
            sketch = next(obj for obj in body.Group if obj.TypeId == "Sketcher::SketchObject")
            index = next(i for i, c in enumerate(sketch.Constraints) if c.Name == "my_radius_2")
            self.doc.openTransaction("学生手动改径")
            try:
                sketch.setDatum(index, App.Units.Quantity(f"{arguments['diameter_m'] * 500.0} mm"))
                self.doc.recompute()
                self.doc.commitTransaction()
            except Exception:
                self.doc.abortTransaction()
                self.doc.recompute()
                raise
            return self._student_state()
        return super()._perform(action, **arguments)

    @staticmethod
    def _middle(result):
        return result["snapshot"]["segments"][1]["diameter_m"]

    @staticmethod
    def _unbound(context, body_name):
        matches = [row for row in context["unbound_objects"] if row["body_name"] == body_name]
        assert len(matches) == 1 and matches[0]["can_bind"], context
        assert body_name in context["unbound_selection"]
        return matches[0]

    def _execute(self):
        client = None
        started = time.monotonic()
        try:
            client = _MCP(self.python, self.bridge.endpoint, self.output, self._record)
            initialized = client.rpc("initialize", {"protocolVersion": "2025-11-25", "capabilities": {},
                                    "clientInfo": {"name": "gongke-existing-shaft-session-test", "version": "1"}})
            client.rpc("notifications/initialized", notification=True)
            assert "bind_existing_shaft" in [tool["name"] for tool in client.rpc("tools/list")["tools"]]
            initial = self._local("create_student")
            baseline = initial["native_state"]
            assert not initial["metadata_properties"] and math.isclose(initial["middle_diameter_m"], .038)
            body_name = baseline["names"][0]
            context = client.tool("get_project_context")
            sid = context["session_id"]
            described = self._unbound(context, body_name)
            assert math.isclose(described["segments"][1]["diameter_m"], .038)
            assert [s["radius_constraint"] for s in described["segments"]] == [f"my_radius_{i}" for i in range(1, 4)]
            assert [s["length_constraint"] for s in described["segments"]] == [f"my_length_{i}" for i in range(1, 4)]
            assert described["sketch"] == baseline["names"][1] and described["revolution"] == baseline["names"][2]
            assert self._local("student_state")["native_state"] == baseline
            self.checks.append("unbound_mcp_description_preserves_personal_names_geometry_order_and_body_placement")

            def binding_args(ctx, operation, engineering=None):
                assert ctx["session_id"] == sid
                return {"session_id": sid, "body_name": body_name, "expected_revision": ctx["revision"],
                        "engineering": deepcopy(ENGINEERING if engineering is None else engineering),
                        "operation_id": operation}

            self._local("student_undo_mode", mode=0)
            context = client.tool("get_project_context")
            assert context["undo_available"] is False
            self._unbound(context, body_name)
            refused = client.tool("bind_existing_shaft", expect_error=True,
                                  **binding_args(context, f"undo-disabled-{self.run_id}"))
            assert "撤销" in json.dumps(refused, ensure_ascii=False)
            state = self._local("student_state")
            assert not state["metadata_properties"] and state["native_state"] == baseline
            self._local("student_undo_mode", mode=1)
            self.checks.append("undo_disabled_document_remains_readable_and_binding_cannot_leave_metadata")

            context = client.tool("get_project_context")
            stale = binding_args(context, f"stale-binding-{self.run_id}")
            self._local("manual_student_diameter", diameter_m=.0375)
            refused = client.tool("bind_existing_shaft", expect_error=True, **stale)
            assert "读取后已修改" in json.dumps(refused, ensure_ascii=False)
            state = self._local("student_state")
            assert not state["metadata_properties"] and math.isclose(state["middle_diameter_m"], .0375)
            assert math.isclose(self._unbound(client.tool("get_project_context"), body_name)["segments"][1]["diameter_m"], .0375)
            self._local("native_undo", transaction="学生手动改径")
            assert self._local("student_state")["native_state"] == baseline
            self.checks.append("expected_revision_rejects_stale_binding_without_overwriting_student_edit")

            missing = deepcopy(ENGINEERING)
            missing.pop("loads")
            unsupported = deepcopy(ENGINEERING)
            unsupported["loads"][0]["fz_n"] = 1000.0
            for label, engineering in (("missing-loads", missing), ("unsupported-axial-load", unsupported)):
                context = client.tool("get_project_context")
                client.tool("bind_existing_shaft", expect_error=True,
                            **binding_args(context, f"{label}-{self.run_id}", engineering))
                state = self._local("student_state")
                assert not state["metadata_properties"] and state["native_state"] == baseline
            self.checks.append("missing_conditions_and_unsupported_load_components_cannot_bind_or_receive_defaults")

            context = client.tool("get_project_context")
            original_request = binding_args(context, f"binding-first-{self.run_id}")
            other = self._local("activate_other_document")
            assert client.tool("get_project_context")["document"] == other["document"]
            bound = client.tool("bind_existing_shaft", **original_request)
            assert bound["bound"] and bound["geometry_unchanged"] and bound["supported"]
            assert math.isclose(self._middle(bound), .038)
            assert bound["snapshot"]["coordinate_system"] == "body_local_x"
            assert bound["snapshot"]["conditions_source"] == {"reference": ENGINEERING["source"], "status": "declared"}
            for field in ("material", "supports_m", "loads", "torque_points", "constraints"):
                assert bound["snapshot"][field] == ENGINEERING[field]
            assert self._local("student_state")["native_state"] == baseline
            assert self._local("other_document_state") == other["state"]
            self._local("activate_student_document")
            current_context = client.tool("get_project_context")
            assert current_context["session_id"] == sid and bound["entity_id"] in current_context["selection"]
            self.checks.append("binding_original_session_ignores_a_different_active_document_with_the_same_body_name")
            assert client.tool("bind_existing_shaft", **original_request)["receipt_only"]
            conflict = deepcopy(original_request)
            conflict["engineering"]["source"] += "不同的声明"
            client.tool("bind_existing_shaft", expect_error=True, **conflict)
            assert self._local("student_state")["native_state"] == baseline
            self.checks.append("binding_only_adds_identity_and_mapping_with_idempotent_receipt_and_explicit_conditions")

            client.tool("undo_last_agent_change", session_id=sid, operation_id=original_request["operation_id"])
            state = self._local("student_state")
            assert not state["metadata_properties"] and state["native_state"] == baseline
            self._unbound(client.tool("get_project_context"), body_name)
            assert client.tool("bind_existing_shaft", **original_request)["receipt_only"]
            assert not self._local("student_state")["metadata_properties"]
            self.checks.append("one_undo_removes_binding_keeps_student_body_and_replayed_operation_does_not_rebind")

            context = client.tool("get_project_context")
            rebound = client.tool("bind_existing_shaft", **binding_args(context, f"binding-second-{self.run_id}"))
            assert rebound["entity_id"] != bound["entity_id"] and math.isclose(self._middle(rebound), .038)
            self._local("adopt_binding", entity_id=rebound["entity_id"])
            identity = {"session_id": sid, "entity_id": rebound["entity_id"]}
            middle_id = rebound["snapshot"]["segments"][1]["segment_id"]

            def preview(diameter):
                return client.tool("preview_shaft_change", **identity, segment_id=middle_id, diameter_m=diameter)

            def apply(candidate, operation):
                assert candidate["can_apply"] and candidate["status"] == "pass", candidate
                return client.tool("apply_change", session_id=identity["session_id"],
                                   change_id=candidate["change_id"], operation_id=operation)

            operation = f"bound-edit-{self.run_id}"
            assert apply(preview(.036), operation)["applied"]
            assert math.isclose(self._middle(client.tool("read_engineering_object", **identity)), .036)
            client.tool("undo_last_agent_change", session_id=sid, operation_id=operation)
            assert math.isclose(self._middle(client.tool("read_engineering_object", **identity)), .038)
            assert self._local("student_state")["native_state"] == baseline
            self._local("manual_student_diameter", diameter_m=.037)
            manual = client.tool("read_engineering_object", **identity)
            assert math.isclose(self._middle(manual), .037) and manual["analysis"]["applicability"] == "stale"
            reviewed = client.tool("review_current_object", **identity)
            assert reviewed["applicability"] == "current" and reviewed["result"]["status"] == "pass"
            self.checks.append("bound_axis_uses_original_constraint_for_agent_edit_undo_and_student_continuation")

            project = self.output / "bound_student_shaft.FCStd"
            saved = client.tool("save_project", session_id=sid, path=str(project))
            assert saved["saved"]
            before_reopen = self._local("student_state")["native_state"]
            self._local("close_reopen", path=saved["path"])
            client.tool("read_engineering_object", expect_error=True, **identity)
            context = client.tool("get_project_context")
            assert context["session_id"] != sid and identity["entity_id"] in context["selection"]
            identity = {"session_id": context["session_id"], "entity_id": identity["entity_id"]}
            reopened = client.tool("read_engineering_object", **identity)
            assert math.isclose(self._middle(reopened), .037) and reopened["analysis"]["applicability"] == "current"
            reopened_state = self._local("student_state")["native_state"]
            # FCStd 实体恢复后体积积分可有末位舍入差；其余原生状态仍精确比较。
            assert math.isclose(reopened_state["volume"], before_reopen["volume"], rel_tol=1e-12, abs_tol=1e-9)
            assert {k: v for k, v in reopened_state.items() if k != "volume"} == {
                k: v for k, v in before_reopen.items() if k != "volume"}
            assert apply(preview(.0365), f"bound-reopened-edit-{self.run_id}")["applied"]
            actual = client.tool("read_engineering_object", **identity)
            assert math.isclose(self._middle(actual), .0365) and actual["analysis"]["applicability"] == "current"
            self.checks.append("saved_existing_axis_reopens_with_same_identity_original_objects_and_continued_editing")

            job = client.tool("run_analysis", **identity)
            deadline = time.monotonic() + 30
            while True:
                job = client.tool("get_job", job_id=job["job_id"])
                if job["status"] in ("succeeded", "failed", "cancelled", "interrupted"):
                    break
                assert time.monotonic() < deadline, "已有轴真实梁求解未在 30 秒内完成"
                time.sleep(.2)
            assert job["status"] == "succeeded" and job["applicability"] == "current", job
            self.checks.append("bound_existing_axis_runs_real_calculix_with_current_result")

            before_feature = self._local("student_state")["native_state"]
            feature = self._local("add_unsupported_feature")
            unsupported = client.tool("read_engineering_object", **identity)
            assert not unsupported["supported"] and unsupported["applicability"] == "unsupported"
            assert self._local("feature_exists", name=feature["feature_name"])
            assert client.tool("get_job", job_id=job["job_id"])["applicability"] == "unsupported"
            self._local("native_undo", transaction="学生添加未支持特征")
            assert not self._local("feature_exists", name=feature["feature_name"])
            assert self._local("student_state")["native_state"] == before_feature
            recovered = client.tool("read_engineering_object", **identity)
            assert recovered["supported"] and recovered["analysis"]["applicability"] == "current"
            assert client.tool("get_job", job_id=job["job_id"])["applicability"] == "current"
            self.checks.append("new_student_feature_is_preserved_and_native_undo_restores_supported_bound_axis")

            final_review = client.tool("review_current_object", **identity)
            assert final_review["applicability"] == "current" and final_review["result"]["status"] == "pass"
            saved = client.tool("save_project", session_id=identity["session_id"])
            assert saved["saved"]
            image = self._local("capture_view")
            (self.output / "existing_shaft_session.json").write_text(json.dumps({
                "ok": True, "run_id": self.run_id, "freecad_version": self.version,
                "mcp_protocol": initialized["protocolVersion"], "external_python": str(self.python),
                "mcp_working_directory": str(client.root), "entity_id": identity["entity_id"],
                "session_id": identity["session_id"], "saved_project": saved["path"], "image": image,
                "checks": self.checks, "review": final_review, "beam_job": job,
                "initial_student_state": baseline, "final_snapshot": recovered["snapshot"],
                "elapsed_seconds": time.monotonic() - started,
                "scope": "真实 FreeCAD GUI 与独立 stdio MCP；学生手改、Undo 和重开由本地原生 API 模拟，未验证可访问性点击；工况为明确声明的解析 fixture。",
            }, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
        except Exception:
            error = traceback.format_exc()
            (self.output / "existing_shaft_session_error.txt").write_text(error, encoding="utf-8")
            (self.output / "existing_shaft_session_failed.json").write_text(json.dumps({
                "ok": False, "run_id": self.run_id, "checks": self.checks, "error": error,
            }, ensure_ascii=False, indent=2), encoding="utf-8")
        finally:
            try:
                if client is not None:
                    client.close()
            finally:
                self.done = True


def start(output_dir, external_python):
    session = ExistingShaftSession(output_dir, external_python)
    _runs.append(session)
    return session

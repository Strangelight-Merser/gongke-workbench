"""安装副本的真实 MCP 圆角编辑；本地原生 API 模拟学生操作。"""

from copy import deepcopy
import json
import math
from pathlib import Path
import sys
import time
import traceback

sys.path.insert(0, str(Path(__file__).parent))
from course_session_flow import CourseSession
from native_session_flow import _MCP, _runs


class FilletSession(CourseSession):
    def _execute(self):
        client = None
        try:
            client = _MCP(self.python, self.bridge.endpoint, self.output, self._record)
            client.rpc("initialize", {"protocolVersion": "2025-11-25", "capabilities": {},
                                      "clientInfo": {"name": "gongke-fillet-session-test", "version": "1"}})
            client.rpc("notifications/initialized", notification=True)
            context = client.tool("create_shaft_project", case="course_output")
            identity = {"session_id": context["session_id"], "entity_id": context["selection"][0]}
            self._local("bind_created", document=context["document"], entity_id=identity["entity_id"])
            initial = client.tool("read_engineering_object", **identity)
            fillet = initial["snapshot"]["fillet_assumptions"][3]
            target = {k: fillet[k] for k in ("left_segment_id", "right_segment_id")}

            def preview(radius):
                return client.tool("preview_fillet_change", **identity, **target, radius_m=radius)

            def apply(candidate, operation):
                return client.tool("apply_change", session_id=identity["session_id"],
                                   change_id=candidate["change_id"], operation_id=operation)

            candidate = preview(0.0012)
            assert candidate["can_apply"] and candidate["status"] == "ready", candidate
            assert candidate["review"]["status"] == "blocked"
            assert candidate["review"]["geometry_basis"] == "hypothetical_snapshot"
            assert client.tool("read_engineering_object", **identity)["content_hash"] == initial["content_hash"]
            self.checks.append("preview_keeps_cad_unchanged_and_engineering_blocked")

            self._local("manual_course_fillet", index=3, radius_m=0.0011)
            client.tool("apply_change", expect_error=True, session_id=identity["session_id"],
                        change_id=candidate["change_id"], operation_id="stale-candidate")
            manual = client.tool("read_engineering_object", **identity)
            assert math.isclose(manual["snapshot"]["fillet_assumptions"][3]["cad_radius_m"], 0.0011)
            self._local("native_undo", transaction="学生手动轴肩圆角")
            self.checks.append("stale_candidate_does_not_overwrite_student_fillet")

            candidate = preview(0.0012)
            operation = f"fillet-first-{self.run_id}"
            result = apply(candidate, operation)
            assert result["applied"] and result["engineering_conclusion"] == "blocked"
            assert result["analysis"]["basis_verification"] == "native_readback_matches_candidate"
            assert result["analysis"]["geometry_basis"] == "current_parameters_declared_features"
            current = client.tool("read_engineering_object", **identity)
            expected = deepcopy(initial["snapshot"])
            expected["fillet_assumptions"][3]["cad_radius_m"] = 0.0012
            assert current["snapshot"] == expected
            assert current["analysis"]["applicability"] == "current"
            assert any(math.isclose(s["z"], .164) and math.isclose(s["r"], .0012)
                       for s in result["analysis"]["fatigue_sections"])
            assert apply(candidate, operation)["receipt_only"]
            client.tool("undo_last_agent_change", session_id=identity["session_id"], operation_id=operation)
            assert client.tool("read_engineering_object", **identity)["content_hash"] == initial["content_hash"]
            assert apply(candidate, operation)["receipt_only"]
            assert client.tool("read_engineering_object", **identity)["content_hash"] == initial["content_hash"]
            self.checks.append("one_native_fillet_transaction_readback_receipt_and_undo")

            candidate = preview(0.0012)
            operation = f"fillet-student-{self.run_id}"
            apply(candidate, operation)
            self._local("manual_course_fillet", index=3, radius_m=0.0013)
            client.tool("undo_last_agent_change", expect_error=True,
                        session_id=identity["session_id"], operation_id=operation)
            assert math.isclose(client.tool("read_engineering_object", **identity)["snapshot"]
                                ["fillet_assumptions"][3]["cad_radius_m"], .0013)
            self._local("native_undo", transaction="学生手动轴肩圆角")
            self._local("native_undo", transaction=f"工科圆角 {operation}")
            self.checks.append("agent_undo_never_crosses_a_later_student_edit")

            for radius in (.002, .0008):
                refused = preview(radius)
                assert not refused["can_apply"]
                client.tool("apply_change", expect_error=True, session_id=identity["session_id"],
                            change_id=refused["change_id"], operation_id=f"refused-{radius}")
            wrong = initial["snapshot"]["fillet_assumptions"][0]
            refused = client.tool("preview_fillet_change", **identity, radius_m=.0012,
                                  **{k: wrong[k] for k in target})
            assert not refused["can_apply"]
            assert client.tool("read_engineering_object", **identity)["content_hash"] == initial["content_hash"]
            self.checks.append("out_of_scope_or_oversize_candidates_cannot_write")

            apply(preview(.0012), f"fillet-save-{self.run_id}")
            project = self.output / "course_shaft.FCStd"
            client.tool("save_project", session_id=identity["session_id"], path=str(project))
            self._local("close_reopen", path=str(project))
            context = client.tool("get_project_context")
            identity = {"session_id": context["session_id"], "entity_id": self.entity_id}
            assert client.tool("read_engineering_object", **identity)["analysis"]["applicability"] == "current"
            apply(preview(.0015), f"fillet-reopened-{self.run_id}")
            actual = client.tool("read_engineering_object", **identity)
            assert actual["supported"] and actual["snapshot"]["cad_geometry_state"]["fillets_current"]
            assert math.isclose(actual["snapshot"]["fillet_assumptions"][3]["cad_radius_m"], .0015)
            self.checks.append("saved_reopened_model_remains_editable_with_current_review")

            job = client.tool("run_analysis", **identity)
            deadline = time.monotonic() + 30
            while job["status"] not in ("succeeded", "failed", "cancelled", "interrupted"):
                assert time.monotonic() < deadline
                time.sleep(.2)
                job = client.tool("get_job", job_id=job["job_id"])
            assert job["status"] == "succeeded" and job["applicability"] == "current", job
            final_review = client.tool("review_current_object", **identity)
            assert final_review["result"]["status"] == "blocked" and not final_review["result"]["errors"]
            client.tool("save_project", session_id=identity["session_id"])
            image = self._local("capture_view")
            self.checks.append("modified_course_runs_real_solver_and_keeps_engineering_limits")
            (self.output / "course_fillet_session.json").write_text(json.dumps({
                "ok": True, "freecad_version": self.version, "checks": self.checks,
                "saved_project": str(project), "image": image, "mcp_working_directory": str(client.root),
                "review": final_review, "beam_job": job,
                "scope": "真实 FreeCAD 与独立 stdio MCP；本地原生 API 模拟学生编辑，未验证可访问性点击。"
            }, ensure_ascii=False, indent=2))
        except Exception:
            (self.output / "course_fillet_session_error.txt").write_text(traceback.format_exc())
        finally:
            if client is not None:
                client.close()
            self.done = True


def start(output_dir, external_python):
    session = FilletSession(output_dir, external_python)
    _runs.append(session)
    return session

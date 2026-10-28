"""真实七段轴：独立 stdio MCP 创建/复核，原生编辑、保存重开与梁任务关联。"""

import json
import math
from pathlib import Path
import sys
import time
import traceback

sys.path.insert(0, str(Path(__file__).parent))
from native_session_flow import _Session, _MCP, _runs


class CourseSession(_Session):
    def _perform(self, action, **arguments):
        import FreeCAD as App
        if action == "bind_created":
            self.doc = App.getDocument(arguments["document"])
            self.entity_id = arguments["entity_id"]
            assert self._body().TypeId == "PartDesign::Body"
            return {"document": self.doc.Name, "entity_id": self.entity_id}
        if action == "manual_course_key_depth":
            self.doc.openTransaction("学生手动键槽深度")
            try:
                self._body().GkKeyPockets[0].Length = arguments["value_m"] * 1000.0
                self.doc.recompute()
                self.doc.commitTransaction()
            except Exception:
                self.doc.abortTransaction()
                raise
            return {"depth_m": arguments["value_m"]}
        if action == "manual_course_fillet":
            self.doc.openTransaction("学生手动轴肩圆角")
            try:
                self._body().GkFillets[arguments["index"]].Radius = arguments["radius_m"] * 1000.0
                self.doc.recompute()
                self.doc.commitTransaction()
            except Exception:
                self.doc.abortTransaction()
                raise
            return {"radius_m": arguments["radius_m"]}
        if action in ("manual_course_diameter", "manual_course_length"):
            body = self._body()
            mapping = next(item for item in json.loads(body.GkMetadata)["dimensions"]
                           if item["segment_id"] == arguments["segment_id"])
            dimension = mapping["radius" if action == "manual_course_diameter" else "length"]
            index = next(i for i, item in enumerate(body.GkSketch.Constraints) if item.Name == dimension)
            value_mm = arguments["value_m"] * (500.0 if action == "manual_course_diameter" else 1000.0)
            self.doc.openTransaction("学生手动课程轴尺寸")
            try:
                body.GkSketch.setDatum(index, App.Units.Quantity(f"{value_mm:.12g} mm"))
                self.doc.recompute()
                self.doc.commitTransaction()
            except Exception:
                self.doc.abortTransaction()
                raise
            return {"constraint": dimension, "value_m": arguments["value_m"]}
        return super()._perform(action, **arguments)

    def _execute(self):
        client = None
        try:
            client = _MCP(self.python, self.bridge.endpoint, self.output, self._record)
            client.rpc("initialize", {"protocolVersion": "2025-11-25", "capabilities": {},
                                      "clientInfo": {"name": "gongke-course-session-test", "version": "1"}})
            client.rpc("notifications/initialized", notification=True)
            context = client.tool("create_shaft_project", case="course_output")
            assert len(context["selection"]) == 1
            identity = {"session_id": context["session_id"], "entity_id": context["selection"][0]}
            self._local("bind_created", document=context["document"], entity_id=identity["entity_id"])
            current = client.tool("read_engineering_object", **identity)
            snapshot = current["snapshot"]
            assert snapshot["scope"] == "course_shaft_review" and len(snapshot["segments"]) == 7
            assert snapshot["cad_geometry_state"]["keyways_current"]
            assert snapshot["cad_geometry_state"]["load_binding_current"]
            assert snapshot["loads"][0]["fz_n"] != 0 and snapshot["loads"][0]["couple_xz_nm"] != 0
            shoulder = next(s for s in snapshot["segments"] if s["role"] == "轴肩")
            assert math.isclose(shoulder["diameter_m"], 0.064)
            self.checks.append("stdio_creates_native_seven_segment_shaft_with_two_keyways")

            review = client.tool("review_current_object", **identity)
            assert review["result"]["status"] == "blocked" and not review["result"]["errors"], review
            assert len(review["result"]["checks"]) >= 7
            assert all(c["name"] != "fatigue_assumed_geometry" for c in review["result"]["checks"])
            assert next(c for c in review["result"]["checks"] if c["name"] == "bearing_seat_right")["status"] == "pass"
            assert snapshot["cad_geometry_state"]["fillets_current"]
            assert any(math.isclose(s["z"], 0.164) and math.isclose(s["r"], 0.001)
                       for s in review["result"]["fatigue_unsupported_sections"])
            candidate = client.tool("preview_shaft_change", **identity, segment_id=shoulder["segment_id"], diameter_m=0.063)
            assert candidate["status"] == "blocked" and not candidate["can_apply"]
            assert not candidate["review"]["errors"], candidate["review"]
            client.tool("apply_change", expect_error=True, session_id=identity["session_id"],
                        change_id=candidate["change_id"], operation_id=f"course-rejected-{self.run_id}")
            after = client.tool("read_engineering_object", **identity)
            assert after["content_hash"] == current["content_hash"]
            self.checks.append("fixed_current_dimensions_review_and_constrained_candidate_rejection")

            self._local("manual_course_fillet", index=3, radius_m=0.0015)
            fillet_read = client.tool("read_engineering_object", **identity)
            assert math.isclose(fillet_read["snapshot"]["fillet_assumptions"][3]["cad_radius_m"], 0.0015)
            fillet_review = client.tool("review_current_object", **identity)
            assert not any(math.isclose(s["z"], 0.164) for s in fillet_review["result"]["fatigue_unsupported_sections"])
            assert any(math.isclose(s["z"], 0.164) and math.isclose(s["r"], 0.0015)
                       for s in fillet_review["result"]["fatigue_sections"])
            self._local("native_undo", transaction="学生手动轴肩圆角")
            self.checks.append("actual_fillet_radius_controls_fatigue_model_applicability")

            self._local("manual_course_diameter", segment_id=shoulder["segment_id"], value_m=0.065)
            unsupported = client.tool("read_engineering_object", **identity)
            assert not unsupported["supported"] and unsupported["applicability"] == "unsupported"
            client.tool("review_current_object", expect_error=True, **identity)
            client.tool("run_analysis", expect_error=True, **identity)
            self._local("native_undo", transaction="学生手动课程轴尺寸")
            assert client.tool("read_engineering_object", **identity)["supported"]
            review = client.tool("review_current_object", **identity)
            self.checks.append("invalid_intermediate_fillet_blocks_cached_final_shape_and_undo_recovers")

            job = client.tool("run_analysis", **identity)
            deadline = time.monotonic() + 30
            while True:
                job = client.tool("get_job", job_id=job["job_id"])
                if job["status"] in ("succeeded", "failed", "cancelled", "interrupted"):
                    break
                assert time.monotonic() < deadline, "课程梁求解未在30秒内完成"
                time.sleep(0.2)
            assert job["status"] == "succeeded" and job["applicability"] == "current", job
            assert len(job["result"]["checks"]) == len(snapshot["stiffness_limits"])
            assert job["result"]["normalized_max_difference"] < 0.01
            self.checks.append("real_calculix_with_axial_force_eccentric_couple_and_position_limits")

            project = self.output / "course_shaft.FCStd"
            saved = client.tool("save_project", session_id=identity["session_id"], path=str(project))
            old_identity = identity
            self._local("close_reopen", path=saved["path"])
            context = client.tool("get_project_context")
            identity = {"session_id": context["session_id"], "entity_id": self.entity_id}
            client.tool("read_engineering_object", expect_error=True, **old_identity)
            assert client.tool("read_engineering_object", **identity)["analysis"]["applicability"] == "current"
            assert client.tool("get_job", job_id=job["job_id"])["applicability"] == "current"
            self.checks.append("saved_course_reopens_with_current_analysis_and_beam_result")

            self._local("manual_course_diameter", segment_id=shoulder["segment_id"], value_m=0.063)
            manual = client.tool("read_engineering_object", **identity)
            assert math.isclose(next(s["diameter_m"] for s in manual["snapshot"]["segments"]
                                    if s["segment_id"] == shoulder["segment_id"]), 0.063)
            assert manual["analysis"]["applicability"] == "stale"
            assert client.tool("get_job", job_id=job["job_id"])["applicability"] == "stale"
            changed_review = client.tool("review_current_object", **identity)
            assert not changed_review["result"]["errors"]
            old_deflection = next(c["value"] for c in review["result"]["checks"] if c["name"] == "stiffness_0")
            new_deflection = next(c["value"] for c in changed_review["result"]["checks"] if c["name"] == "stiffness_0")
            assert not math.isclose(old_deflection, new_deflection, rel_tol=1e-4)
            self._local("native_undo", transaction="学生手动课程轴尺寸")
            self.checks.append("manual_shoulder_edit_recomputes_current_geometry_without_reselecting")

            bearing_seat = next(s for s in snapshot["segments"] if s["role"] == "轴承" and s["z0_m"] > shoulder["z0_m"])
            # 54 mm 会使相邻 R1 圆角退化；54.5 mm 保持可行几何，单独验证孔径冲突。
            self._local("manual_course_diameter", segment_id=bearing_seat["segment_id"], value_m=0.0545)
            fit_review = client.tool("review_current_object", **identity)
            fit = next(c for c in fit_review["result"]["checks"] if c["name"] == "bearing_seat_right")
            assert fit["status"] == "fail", fit
            self._local("native_undo", transaction="学生手动课程轴尺寸")
            self.checks.append("manual_bearing_seat_mismatch_is_detected_against_fixed_interface")

            self._local("manual_course_key_depth", value_m=0.007)
            key_review = client.tool("review_current_object", **identity)
            key = next(c for c in key_review["result"]["checks"] if c["name"] == "key_0")
            assert key["status"] == "blocked" and "value" not in key, key
            self._local("native_undo", transaction="学生手动键槽深度")
            self.checks.append("manual_key_depth_change_does_not_reuse_original_key_pass")

            self._local("manual_course_length", segment_id=shoulder["segment_id"], value_m=shoulder["length_m"] + 0.001)
            moved = client.tool("read_engineering_object", **identity)
            assert moved["snapshot"]["cad_geometry_state"]["load_binding_current"] is False
            blocked = client.tool("review_current_object", **identity)
            assert not blocked["result"]["checks"]
            client.tool("run_analysis", expect_error=True, **identity)
            self._local("native_undo", transaction="学生手动课程轴尺寸")
            self.checks.append("length_edit_invalidates_fixed_load_binding_in_review_and_solver")

            final_review = client.tool("review_current_object", **identity)
            assert not final_review["result"]["errors"]
            client.tool("save_project", session_id=identity["session_id"])
            image = self._local("capture_view")
            result = {"ok": True, "freecad_version": self.version, "entity_id": self.entity_id,
                      "mcp_working_directory": str(client.root),
                      "saved_project": str(project), "image": image, "checks": self.checks,
                      "review": final_review, "beam_job": client.tool("get_job", job_id=job["job_id"]),
                      "scope": "真实原生七段轴与键槽、stdio MCP、CalculiX；本地Sketcher API模拟手改，未验证可访问性点击。"}
            (self.output / "course_session.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
        except Exception:
            (self.output / "course_session_error.txt").write_text(traceback.format_exc())
        finally:
            if client is not None:
                client.close()
            self.done = True


def start(output_dir, external_python):
    session = CourseSession(output_dir, external_python)
    _runs.append(session)
    return session

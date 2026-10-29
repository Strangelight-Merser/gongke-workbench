"""只读修订用例与 CLI 集成；宿主响应为契约替身，真实 CAD 另行验收。"""

from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
from threading import Thread

import pytest

from gongke_core import native_client, revision_calculations
from gongke_core.revision_case import format_summary, inspect_revision


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def revision():
    path = "/课程 设计/shaft.FCStd"
    signature = [{"type": "DistanceY", "name": "middle_radius", "driving": True}]
    case = {
        "schema_version": 1, "case_id": "case-integration",
        "document": {"path": path, "body": "Rotor", "sketch": "Outline", "revolution": "Turned",
                     "structure_signature": signature},
        "target": {"radius_constraint": "middle_radius", "segment_index": 1}, "pages": ["Drawing"],
        "annotations": [{"page": "Drawing", "view": "Front", "dimension": "MiddleDiameter", "target": "diameter"}],
        "conditions": json.loads((ROOT / "examples/revision_conditions.json").read_text(encoding="utf-8")),
    }
    dimension = {
        "name": "MiddleDiameter", "type": "Diameter", "measurement_m": .038, "raw_value": 38,
        "raw_unit": "mm", "measure_type": "Projected", "display_text": "⌀38.00 mm", "display_unit": "mm",
        "format_spec": "⌀%.2w", "precision": 2, "arbitrary": False, "arbitrary_tolerances": False,
        "valid": True, "state": ["Up-to-date"], "issues": [], "reference_status": "valid",
        "references2d": [{"path": path, "object": "Front", "subelements": ["Edge5"]}], "references3d": [],
        "over_tolerance_m": 0, "under_tolerance_m": 0,
    }
    capture = {
        "host": "freecad", "session_id": "session-a",
        "document": {"path": path, "name": "Shaft", "pending_transaction": False, "needs_rebuild": False},
        "geometry": {"supported": True, "body_name": "Rotor", "sketch": "Outline", "revolution": "Turned",
                     "structure_signature": deepcopy(signature), "segments": [
                         {"length_m": .05, "diameter_m": .03, "radius_constraint": "left_radius"},
                         {"length_m": .1, "diameter_m": .038, "radius_constraint": "middle_radius"},
                         {"length_m": .05, "diameter_m": .03, "radius_constraint": "right_radius"}]},
        "drawing": {"coverage": {"status": "complete", "scope": "selected_pages"}, "issues": [], "pages": [
            {"name": "Drawing", "state": ["Up-to-date"], "keep_updated": True, "unknown_objects": [], "views": [
                {"name": "Front", "state": ["Up-to-date"], "sources": [{"path": path, "object": "Rotor"}],
                 "dimensions": [dimension]}]}]},
    }
    return case, capture


def checks(result):
    return {check["name"]: check for check in result["calculation"]["checks"]}


def test_offline_result_is_explicit_and_detached_from_its_inputs(revision, monkeypatch):
    case, capture = revision
    original = deepcopy(revision)
    monkeypatch.setattr(native_client, "call", lambda *args, **kwargs: pytest.fail("离线检查不能访问当前宿主"))
    result = inspect_revision(case, capture)
    assert result["source_mode"] == "recorded_capture"
    assert result["applicability"]["status"] == "recorded_capture"
    assert result["stage"] == "assessed" and result["read_only"] is True
    assert result["modification_eligibility"]["allowed"] is False
    assert result["drawing_review"]["status"] == "pass"
    assert revision == original
    result["capture"]["geometry"]["segments"][1]["diameter_m"] = 1
    assert capture == original[1]
    summary = format_summary(result)
    assert "离线采集" in summary and "不证明当前 CAD" in summary


def test_live_result_calls_only_the_explicit_read_context(revision, monkeypatch):
    case, capture = revision
    requests = []

    def call(method, **params):
        requests.append((method, params))
        return deepcopy(capture)

    monkeypatch.setattr(native_client, "call", call)
    result = inspect_revision(case)
    assert requests == [("read_revision_context", {"document_path": case["document"]["path"],
                                                   "body_name": "Rotor", "pages": ["Drawing"]})]
    assert result["source_mode"] == "live" and result["applicability"]["status"] == "current_at_capture"
    assert "实时读取" in format_summary(result)


def test_identity_mismatch_never_passes_foreign_geometry_to_calculation(revision, monkeypatch):
    case, capture = revision
    capture["document"]["path"] = "/其他 同名文件/shaft.FCStd"
    passed_geometry = []
    assess = revision_calculations.assess

    def recording_assess(geometry, conditions):
        passed_geometry.append(deepcopy(geometry))
        return assess(geometry, conditions)

    monkeypatch.setattr(revision_calculations, "assess", recording_assess)
    result = inspect_revision(case, capture)
    assert result["mapping"]["status"] == "mismatch" and result["stage"] == "captured"
    assert passed_geometry == [{}]
    assert all(check["value"] is None and check["status"] == "unavailable" for check in checks(result).values())
    assert result["drawing_review"]["status"] == "fail"


def test_missing_E_preserves_stress_and_drawing_results(revision):
    case, capture = revision
    case["conditions"]["fields"].pop("young_modulus")
    result = inspect_revision(case, capture)
    actual = checks(result)
    assert actual["nominal_combined_stress"]["status"] == "pass"
    assert actual["nominal_combined_stress"]["value"] > 0
    assert actual["maximum_deflection"]["status"] == "unavailable"
    assert result["drawing_review"]["status"] == "pass"
    assert "young_modulus" in format_summary(result)


def test_optional_material_name_does_not_block_complete_numeric_inputs(revision):
    case, capture = revision
    case["conditions"]["fields"].pop("material_name")
    result = inspect_revision(case, capture)
    assert result["calculation"]["numerical_status"] == "pass"
    assert all(check["value"] is not None for check in checks(result).values())
    assert result["drawing_review"]["status"] == "pass"


def test_summary_keeps_condition_units_sources_and_declared_confirmation(revision):
    case, capture = revision
    modulus = case["conditions"]["fields"]["young_modulus"]
    modulus["source"] = {"reference": "材料参数页第 3 页", "text": "原始声明 E = 200 GPa"}
    summary = format_summary(inspect_revision(case, capture))
    assert "确认状态由输入者声明" in summary
    assert "200 GPa；用于计算；confirmed" in summary
    assert "来源：材料参数页第 3 页；原文：原始声明 E = 200 GPa" in summary
    modulus["status"] = "unknown"
    summary = format_summary(inspect_revision(case, capture))
    assert "200 GPa；未用于计算；unknown" in summary
    assert "原始声明 E = 200 GPa" in summary


@pytest.mark.parametrize("flag", ["pending_transaction", "needs_rebuild"])
def test_document_edit_state_preserves_identity_without_calculating_stale_geometry(revision, monkeypatch, flag):
    case, capture = revision
    previous = inspect_revision(case, capture)
    capture["document"][flag] = True
    original = deepcopy(revision)
    passed_geometry = []
    assess = revision_calculations.assess

    def recording_assess(geometry, conditions):
        passed_geometry.append(deepcopy(geometry))
        return assess(geometry, conditions)

    monkeypatch.setattr(revision_calculations, "assess", recording_assess)
    result = inspect_revision(case, capture, previous)
    assert result["mapping"]["status"] == "mapped"
    assert result["mapping"]["mapping"]["target"]["diameter_m"] == .038
    assert passed_geometry == [{}]
    assert all(check["value"] is None and check["status"] == "unavailable" for check in checks(result).values())
    assert any("事务" in reason or "更新" in reason for reason in result["calculation"]["geometry_issues"])
    assert result["drawing_review"]["status"] == "unknown"
    assert result["drawing_review"]["coverage"]["checked"] == 0
    assert result["applicability"]["previous"] == {"status": "stale", "changed": ["document_state"]}
    assert "已过期（document_state）" in format_summary(result)
    assert revision == original
    assert previous["calculation"]["numerical_status"] == "pass"


@pytest.mark.parametrize("edit,changed", [("drawing", "drawing"), ("conditions", "conditions"), ("session", "session_id")])
def test_previous_result_detects_independent_changes(revision, edit, changed):
    case, capture = revision
    previous = inspect_revision(case, capture)
    before = deepcopy(previous)
    if edit == "drawing":
        capture["drawing"]["pages"][0]["views"][0]["dimensions"][0]["arbitrary"] = True
    elif edit == "conditions":
        case["conditions"]["fields"]["supports"]["source"]["reference"] = "更正后的教学条件页"
    else:
        capture["session_id"] = "session-b"
    result = inspect_revision(case, capture, previous)
    assert result["applicability"]["previous"] == {"status": "stale", "changed": [changed]}
    assert "已过期" in format_summary(result)
    assert previous == before


def test_previous_result_without_mapping_is_rejected(revision):
    with pytest.raises(ValueError, match="previous"):
        inspect_revision(*revision, previous={"schema_version": 1})


def write_inputs(tmp_path, revision):
    base = tmp_path / "中文 任务"
    base.mkdir()
    paths = []
    for name, data in zip(("case.json", "capture.json"), revision):
        path = base / name
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        paths.append(path)
    return paths


def run_cli(case, out, capture=None, previous=None, env=None):
    command = [sys.executable, "-m", "gongke_core", "inspect-revision", "--host", "freecad",
               "--case", str(case), "--out", str(out)]
    if capture:
        command.extend(("--capture", str(capture)))
    if previous:
        command.extend(("--previous", str(previous)))
    return subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, timeout=20)


def test_cli_offline_writes_readable_result_and_does_not_touch_input_files(tmp_path, revision):
    case, capture = write_inputs(tmp_path, revision)
    before = [p.read_bytes() for p in (case, capture)]
    out = tmp_path / "中文 输出"
    response = run_cli(case, out, capture)
    assert response.returncode == 0, response.stderr
    assert "离线采集" in response.stdout and "38 mm" in response.stdout
    result = json.loads((out / "revision.json").read_text(encoding="utf-8"))
    assert result["source_mode"] == "recorded_capture" and result["read_only"] is True
    assert sorted(p.name for p in out.iterdir()) == ["revision.json"]
    assert before == [p.read_bytes() for p in (case, capture)]


@pytest.mark.parametrize("failure", ["missing_E", "override", "identity", "pending_transaction", "needs_rebuild"])
def test_cli_returns_one_for_failed_or_unknown_checks_and_keeps_results(tmp_path, revision, failure):
    case, capture = revision
    if failure == "missing_E":
        case["conditions"]["fields"].pop("young_modulus")
    elif failure == "override":
        capture["drawing"]["pages"][0]["views"][0]["dimensions"][0]["arbitrary"] = True
    elif failure == "identity":
        capture["document"]["path"] = "/different/shaft.FCStd"
    else:
        capture["document"][failure] = True
    case_path, capture_path = write_inputs(tmp_path, revision)
    out = tmp_path / "review"
    response = run_cli(case_path, out, capture_path)
    assert response.returncode == 1, response.stderr
    result = json.loads((out / "revision.json").read_text(encoding="utf-8"))
    assert result["modification_eligibility"]["allowed"] is False
    if failure == "missing_E":
        assert checks(result)["nominal_combined_stress"]["status"] == "pass"
    elif failure in ("pending_transaction", "needs_rebuild"):
        assert result["drawing_review"]["status"] == "unknown"
        assert all(check["value"] is None for check in checks(result).values())


def test_cli_previous_result_reports_stale_drawing(tmp_path, revision):
    case, capture = write_inputs(tmp_path, revision)
    first = tmp_path / "first"
    assert run_cli(case, first, capture).returncode == 0
    changed = deepcopy(revision[1])
    changed["drawing"]["pages"][0]["views"][0]["dimensions"][0]["arbitrary"] = True
    capture.write_text(json.dumps(changed), encoding="utf-8")
    response = run_cli(case, tmp_path / "second", capture, first / "revision.json")
    assert response.returncode == 1 and "已过期（drawing）" in response.stdout
    assert json.loads((first / "revision.json").read_text())["drawing_review"]["status"] == "pass"


def test_cli_refuses_existing_output_without_overwriting_it(tmp_path, revision):
    case, capture = write_inputs(tmp_path, revision)
    out = tmp_path / "existing"
    out.mkdir()
    original = out / "revision.json"
    original.write_bytes(b'original evidence\n')
    response = run_cli(case, out, capture)
    assert response.returncode == 2 and "输出目录已存在" in response.stderr
    assert original.read_bytes() == b'original evidence\n'


def test_cli_bad_json_and_unsupported_host_are_usage_errors(tmp_path, revision):
    case, capture = write_inputs(tmp_path, revision)
    case.write_text("{", encoding="utf-8")
    out = tmp_path / "bad-input"
    response = run_cli(case, out, capture)
    assert response.returncode == 2 and not out.exists()
    response = subprocess.run([sys.executable, "-m", "gongke_core", "inspect-revision", "--host", "solidworks-capture",
                               "--case", str(case), "--out", str(out)], cwd=ROOT, capture_output=True, text=True, timeout=20)
    assert response.returncode == 2 and "invalid choice" in response.stderr and not out.exists()


def test_cli_live_uses_read_context_and_marks_actual_transport_mode(tmp_path, revision):
    case, capture = write_inputs(tmp_path, revision)
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            requests.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            payload = json.dumps({"ok": True, "result": revision[1]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    session = tmp_path / "session.json"
    session.write_text(json.dumps({"url": f"http://127.0.0.1:{server.server_port}", "token": "fixture-only"}))
    out = tmp_path / "live-review"
    try:
        response = run_cli(case, out, env={**os.environ, "GONGKE_FREECAD_SESSION": str(session)})
        assert response.returncode == 0, response.stderr
        result = json.loads((out / "revision.json").read_text())
        assert result["source_mode"] == "live" and "实时读取" in response.stdout
        assert requests == [{"method": "read_revision_context", "params": {
            "document_path": revision[0]["document"]["path"], "body_name": "Rotor", "pages": ["Drawing"]}}]
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_cli_missing_live_host_is_actionable_error_without_output(tmp_path, revision):
    case, _ = write_inputs(tmp_path, revision)
    out = tmp_path / "missing-host"
    response = run_cli(case, out, env={**os.environ, "GONGKE_FREECAD_SESSION": str(tmp_path / "no-session.json")})
    assert response.returncode == 2 and "未连接 FreeCAD" in response.stderr and not out.exists()

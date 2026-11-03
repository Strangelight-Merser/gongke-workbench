"""验收脚本读取真实配置、保留失败证据并核对持久收据。"""
import json
import os
from pathlib import Path
import sqlite3

import pytest

from tests.e2e.workbuddy_acceptance import main, read_receipt
from tests.mcp_helpers import ROOT, ServiceProcess


def test_config_probe_and_supplied_receipts(tmp_path):
    service = ServiceProcess(tmp_path, env={**os.environ,
        "GONGKE_FREECAD_SESSION": str(tmp_path / "absent-freecad-session.json")})
    try:
        service.request("mcp.configure", {"allow_writes": False, "confirm_user_config": True})
        output = tmp_path / "probe.json"
        assert main(["probe", "--project", str(service.project), "--output", str(output)]) == 0
        evidence = json.loads(output.read_text())
        assert evidence["origin"] == "official_mcp_sdk_probe"
        assert evidence["workbuddy_ui_verified"] is False
        assert not Path(evidence["child_cwd"]).is_relative_to(ROOT)
        assert [row["tool"] for row in evidence["calls"]] == ["project.current", "project.files", "hosts.list"]
        assert all(row["receipt_matches"] for row in evidence["calls"])
        assert evidence["freecad_connected"] is False
        task_ids = [row["response"]["structured_content"]["task_id"] for row in evidence["calls"]]
        checked = tmp_path / "receipts.json"
        arguments = ["receipts", "--project", str(service.project), "--output", str(checked)]
        for task_id in task_ids:
            arguments.extend(["--task-id", task_id])
        assert main(arguments) == 0
        assert len(json.loads(checked.read_text())["service_records"]) == 3
        with pytest.raises(FileExistsError):
            main(arguments)
        required = tmp_path / "required.json"
        assert main(["probe", "--project", str(service.project), "--output", str(required),
                     "--require-freecad"]) == 1
        failed = json.loads(required.read_text())
        assert len(failed["calls"]) == 3 and "FreeCAD 未连接" in failed["traceback"]
    finally:
        service.close()


def test_receipt_rejects_wrong_project_and_result(tmp_path):
    state, project = tmp_path / "state", tmp_path / "project"
    state.mkdir()
    project.mkdir()
    result = {"value": 1}
    record = {"task_id": "task", "project": str(project), "status": "complete", "result": result}
    receipt = {"command": "project.current", "phase": "finished", "result": result}
    with sqlite3.connect(state / "tasks.sqlite3") as db:
        db.execute("CREATE TABLE tasks (id TEXT, record TEXT)")
        db.execute("CREATE TABLE receipts (task_id TEXT, record TEXT)")
        db.execute("INSERT INTO tasks VALUES (?, ?)", ("task", json.dumps(record)))
        db.execute("INSERT INTO receipts VALUES (?, ?)", ("task", json.dumps(receipt)))
    assert read_receipt(state, project, "task", response=record, tool="project.current")["receipts"] == [receipt]
    with pytest.raises(ValueError, match="所属工程不符"):
        read_receipt(state, tmp_path / "another-project", "task")
    with pytest.raises(ValueError, match="回传与服务记录不符"):
        read_receipt(state, project, "task", response={**record, "result": {"value": 2}})


# 配置测试使用独立用户目录，不读取开发者真实 WorkBuddy 配置。
import pytest

@pytest.fixture(autouse=True)
def workbuddy_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))


def test_probe_reads_confirmed_project_specific_service(tmp_path):
    user = Path.home() / ".workbuddy/mcp.json"
    user.parent.mkdir(parents=True)
    user.write_text('{"mcpServers":{"gongke":{"command":"old"}}}')
    original = user.read_bytes()
    service = ServiceProcess(tmp_path, env={**os.environ,
        "GONGKE_FREECAD_SESSION": str(tmp_path / "absent.json")})
    try:
        pending = service.request("mcp.configure", {"allow_writes": False})
        assert pending["status"] == "confirmation_required"
        configured = service.request("mcp.configure", {"allow_writes": False, "confirm_user_config": True})
        assert configured["service_name"] != "gongke"
        output = tmp_path / "renamed-probe.json"
        assert main(["probe", "--project", str(service.project), "--output", str(output)]) == 0
        report = json.loads(output.read_text())
        assert report["config"]["service_name"] == configured["service_name"]
        assert all(c["receipt_matches"] for c in report["calls"])
        assert Path(configured["backup_path"]).read_bytes() == original
    finally:
        service.close()

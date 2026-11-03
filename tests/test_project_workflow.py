"""真实工程状态、历史对话资料保留与过期交付的回归。"""
import json
import threading
from copy import deepcopy

import pytest

from gongke_app.commands import Commands
from gongke_app.project import Project
from gongke_app.service import Application
from gongke_core import api
from tests.test_app_service import finished


def test_delivery_tracks_input_reopen_and_missing_files(tmp_path):
    project = Project.create(str(tmp_path / "project"))
    commands = Commands()
    result = commands.generate({"name": "first", "drawings": False, "report_docx": False}, project)
    assert result["exports_complete"]
    view = project.view()
    assert view["delivery"]["artifacts"]["markdown"]["available"]
    task = project.task()
    changed = deepcopy(task)
    changed["conveyor"]["belt_pull_N"] += 100
    project.set_task(changed)
    assert project.view()["delivery"] is None
    reopened = Project.open(str(project.path))
    assert not reopened.view()["generations"][0]["current"]
    reopened.set_task(task)
    assert reopened.view()["delivery"]["current"]
    (project.path / "revisions/first/report.md").unlink()
    assert not reopened.view()["delivery"]["artifacts"]["markdown"]["available"]


def test_failed_latest_generation_does_not_reuse_old_success(tmp_path, monkeypatch):
    project = Project.create(str(tmp_path / "project"))
    commands = Commands()
    commands.generate({"name": "good", "drawings": False, "report_docx": False}, project)
    def fail(*args, **kwargs):
        raise RuntimeError("export failed")
    monkeypatch.setattr(api, "generate", fail)
    with pytest.raises(RuntimeError):
        commands.generate({"name": "failed"}, project)
    assert project.view()["delivery"]["status"] == "failed"
    assert len(project.view()["generations"]) == 2
    assert (project.path / "revisions/good/report.md").exists()


def test_teaching_change_invalidates_delivery(tmp_path):
    project = Project.create(str(tmp_path / "project"))
    Commands().generate({"drawings": False, "report_docx": False}, project)
    project.set_task(project.task(), teaching=False)
    assert project.view()["delivery"] is None


def test_queued_generation_uses_submitted_conditions_and_source(tmp_path):
    app = Application(tmp_path / "state")
    app.dispatch("project.create", {"path": str(tmp_path / "project"), "teaching": True})
    original = app.project.task()
    gate = threading.Event()
    blockers = [app.tasks.pool.submit(gate.wait, 5) for _ in range(3)]
    try:
        job = app.dispatch("design.generate", {"drawings": False, "report_docx": False})
        changed = deepcopy(original)
        changed["conveyor"]["belt_pull_N"] += 100
        app.dispatch("project.set_task", {"task": changed, "teaching": False})
        gate.set()
        result = finished(app, job["task_id"])
        assert result["status"] == "complete", result
        assert result["result"]["teaching"] is True
        view = app.project.view()
        assert view["delivery"] is None
        revision = view["generations"][0]
        assert revision["input_hash"] == Project.input_hash(original, True)
        assert json.loads((app.project.path / revision["path"] / "task.json").read_text()) == original
    finally:
        gate.set()
        app.close()


def test_retired_assistant_history_is_preserved(tmp_path):
    project = Project.create(str(tmp_path / "project"))
    history = project.path / ".gongke-conversation.json"
    original = '[{"task_id":"old","user":"保留候选 B","messages":[]}]\n'.encode("utf-8")
    history.write_bytes(original)
    app = Application(tmp_path / "state")
    try:
        app.dispatch("project.open", {"path": str(project.path)})
        app.dispatch("design.calculate", {})
        assert history.read_bytes() == original
        for method in ("agent.configure", "agent.run", "agent.history", "agent.disconnect"):
            with pytest.raises(ValueError, match="未知应用命令"):
                app.dispatch(method, {})
    finally:
        app.close()

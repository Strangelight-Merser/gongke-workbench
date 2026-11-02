"""真实工程状态、连续对话与过期交付的回归；保留原验收程序不变。"""
import json
import threading
from copy import deepcopy

import pytest

from gongke_app.commands import Commands
from gongke_app.project import Project
from gongke_app.service import Application
from gongke_core import api
from tests.test_app_service import ProviderFixture, tool_reply, finished


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


def test_agent_saves_conditions_and_continues_after_reopen(tmp_path):
    app = Application(tmp_path / "state")
    path = str(tmp_path / "project")
    app.dispatch("project.create", {"path": path, "teaching": False})
    task = api.example_task()
    fixture = ProviderFixture([
        tool_reply("project_set_task", {"task": task, "teaching": True}),
        tool_reply("design_calculate", {}, "calculate"),
        [({"content": "已保存教学条件；选中候选 B。"}, "stop")],
        [({"content": "继续使用上一轮的候选 B。"}, "stop")],
    ])
    try:
        fixture.configure(app)
        record = finished(app, app.dispatch("agent.run", {"message": "保存教学任务并选候选 B", "allow_writes": True,
            "selection": {"stage": "gears", "check": {"item": "高速级接触强度"}}})["task_id"])
        assert record["status"] == "complete", record
        assert app.project.task() == task
        assert app.project.manifest["teaching"] is True
        app.close()
        app = Application(tmp_path / "state")
        app.dispatch("project.open", {"path": path})
        fixture.configure(app)
        record = finished(app, app.dispatch("agent.run", {"message": "按刚才的选择继续"})["task_id"])
        assert record["status"] == "complete", record
        sent = fixture.requests[-1]["messages"]
        assert any("候选 B" in (m.get("content") or "") for m in sent)
        assert any("高速级接触强度" in (m.get("content") or "") for m in sent)
        assert any(m["role"] == "tool" and "power_kw" in m["content"] for m in sent)
        assert len(app.dispatch("agent.history", {})["turns"]) == 2
        app.dispatch("project.create", {"path": str(tmp_path / "other"), "teaching": False})
        assert not app.dispatch("agent.history", {})["turns"]
    finally:
        app.close()
        fixture.close()


def test_agent_cannot_compute_unsaved_task_or_write_without_authorization(tmp_path):
    project = Project.create(str(tmp_path / "project"), teaching=False)
    commands = Commands()
    class Context:
        def check(self): pass
    with pytest.raises(ValueError, match="先用 project_set_task"):
        commands.agent_call("design_calculate", {"task": api.example_task()}, project, True, Context())
    with pytest.raises(ValueError, match="未授权"):
        commands.agent_call("project_set_task", {"task": api.example_task(), "teaching": True}, project, False, Context())
    assert project.manifest["task"] is None


def test_running_agent_rejects_concurrent_turn_and_project_switch(tmp_path):
    app = Application(tmp_path / "state")
    app.dispatch("project.create", {"path": str(tmp_path / "project")})
    started, release = threading.Event(), threading.Event()
    class Provider:
        model = "fixture"
        def complete(self, *args):
            started.set()
            release.wait(3)
            return {"role": "assistant", "content": "done"}
    app.provider = Provider()
    try:
        app.dispatch("agent.run", {"message": "first"})
        assert started.wait(1)
        with pytest.raises(ValueError, match="上一条任务"):
            app.dispatch("agent.run", {"message": "second"})
        with pytest.raises(ValueError, match="切换工程"):
            app.dispatch("project.create", {"path": str(tmp_path / "other")})
    finally:
        release.set()
        app.close()


def test_interrupted_history_does_not_replay_unanswered_tool_calls(tmp_path):
    from gongke_app.agent.loop import history
    turns = [{"status": "running", "user": "modify", "messages": [
        {"role": "user", "content": "modify"},
        {"role": "assistant", "tool_calls": [{"id": "original-operation"}]}]}]
    messages = history(turns)
    assert not any("tool_calls" in item for item in messages)
    assert "original-operation" in messages[-1]["content"]
    assert "不能重复写入" in messages[-1]["content"]


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

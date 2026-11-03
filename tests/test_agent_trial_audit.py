"""审计失败与中断的回执，不能把无结果/旧修订当作模型通过。"""
from tests.e2e.agent_modeling_check import current_receipts, collect_tasks
import json
import sqlite3


def test_receipts_must_match_revision_and_checked_body():
    document = {"document_id": "doc", "revision": 2}
    receipts = [{"command": "host.model_save", "result": None}, {"command": "host.check", "result": None},
                {"command": "host.model_save", "result": {"document": {**document, "revision": 1}, "outcome": "committed"}},
                {"command": "host.check", "result": {"document": document, "object_ref": "OtherBody", "status": "pass"}}]
    assert current_receipts(receipts, document, "Body") == {"saved_current_revision": False, "self_check_current_revision": False}
    receipts += [{"command": "host.model_save", "result": {"document": document, "outcome": "committed"}},
                 {"command": "host.check", "result": {"document": document, "object_ref": "Body", "status": "pass"}}]
    assert all(current_receipts(receipts, document, "Body").values())


def test_collect_all_calls_keeps_failed_and_prepared_beyond_100(tmp_path):
    project = tmp_path / "project"
    with sqlite3.connect(tmp_path / "tasks.sqlite3") as db:
        db.execute("CREATE TABLE tasks (id TEXT, record TEXT)")
        db.execute("CREATE TABLE receipts (task_id TEXT, command TEXT, record TEXT)")
        for i in range(105):
            task = {"task_id": str(i), "project": str(project), "status": "failed" if i == 0 else "complete"}
            db.execute("INSERT INTO tasks VALUES (?,?)", (str(i), json.dumps(task)))
            db.execute("INSERT INTO receipts VALUES (?,?,?)", (str(i), "host.model_save", json.dumps({"command": "host.model_save", "result": None})))
        db.execute("INSERT INTO tasks VALUES (?,?)", ("other", json.dumps({"project": "other"})))
    tasks = collect_tasks(tmp_path, project)
    assert len(tasks) == 105
    assert tasks[0]["status"] == "failed"
    assert tasks[-1]["receipts"][0]["result"] is None


def test_input_requires_actual_delivery_without_forcing_duplicate_tool_reads():
    from tests.e2e.agent_modeling_check import input_was_read
    assert not input_was_read([], [], "attachment", "image-hash")
    assert input_was_read([], [{"images": [{"sha256": "image-hash"}]}], "attachment", "image-hash")
    users = [{"text": "dimensions.json dimension-hash"}]
    receipts = [{"command": "project.read_file", "result": {"sha256": "dimension-hash"}}]
    assert input_was_read([], users, "dimensions", "dimension-hash")
    assert not input_was_read(receipts, [], "dimensions", "dimension-hash")
    assert not input_was_read(receipts, users, "dimensions", "wrong-hash")
    assert input_was_read(receipts, users, "dimensions", "dimension-hash")

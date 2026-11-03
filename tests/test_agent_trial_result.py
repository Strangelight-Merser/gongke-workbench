"""最终模型分类与重复试验隔离；不把协议替身计入建模成功率。"""
from argparse import Namespace
import json
from types import SimpleNamespace

from scripts.agent_modeling_trial import isolated_runs
from tests.e2e.agent_modeling_result import classify, summarize


def complete():
    return {"transport_completed": True, "prompt_sent": True, "modeling_prompt_sent": True,
            "audit": dict.fromkeys(("input_read", "native_tree", "saved_current_revision", "archive_valid",
                                    "self_check_current_revision", "reference_pass"), True),
            "reopened": {"verified": True}, "vision": {"verified": False}}


def test_final_correct_model_can_recover_from_initial_misreading():
    result = classify(complete())
    assert result["status"] == "passed" and result["initial_reading_mismatch"]
    assert result["construction_passed"] and not result["failure_reasons"]


def test_reopen_failure_and_unknown_drawing_are_different():
    failure = complete()
    failure["reopened"]["verified"] = False
    assert classify(failure)["status"] == "reopen_failed"
    review = complete()
    review["audit"]["reference_pass"] = None
    assert classify(review)["status"] == "review_required"
    assert review["construction_passed"] and not review["modeling_passed"]
    wrong = complete()
    wrong["audit"]["reference_pass"] = False
    assert classify(wrong)["status"] == "drawing_mismatch"
    assert wrong["construction_passed"]
    report = summarize([failure, review, wrong, classify(complete())])
    assert (report["passed"], report["review_required"], report["failed"], report["construction_passed"]) == (1, 1, 2, 3)


def test_receipt_missing_and_run_incomplete_fail_but_screenshot_error_does_not():
    row = complete()
    row["audit"]["self_check_current_revision"] = False
    assert classify(row)["status"] == "modeling_failed"
    row = complete()
    row["transport_completed"] = False
    assert classify(row)["status"] == "run_failed"
    row = complete()
    row["errors"] = ["screenshot failed"]
    assert classify(row)["status"] == "passed"
    row = complete()
    row["audit"]["error"] = "reference checker failed"
    assert classify(row)["status"] == "verification_failed"


def test_every_repetition_launches_separate_host_and_continues_after_failure(tmp_path, monkeypatch):
    calls = []
    def run(command, cwd):
        calls.append(command)
        folder = tmp_path / "runs" / f"{command[command.index('--cases')+1]}-{command[command.index('--repetition-index')+1]}"
        assert str(folder) == command[command.index("--output")+1]
        assert "--repeats" not in command  # 子进程只跑一次，不能再次递归。
        folder.mkdir(parents=True)
        row = complete()
        if len(calls) == 1:
            row["transport_completed"] = False
        (folder / "summary.json").write_text(json.dumps(summarize([classify(row)])))
        return SimpleNamespace(returncode=1 if len(calls) == 1 else 0)
    monkeypatch.setattr("scripts.agent_modeling_trial.subprocess.run", run)
    args = Namespace(cases=["p7", "p6"], repeats=2, output=tmp_path, delivery="vision", timeout=1200,
                     source="source.jpg", study="study", dsh="dsh", freecad="FreeCAD", background=False, reasoning="high")
    assert isolated_runs(args) == 1
    report = json.loads((tmp_path / "summary.json").read_text())
    assert len(calls) == report["attempted"] == 4 and report["passed"] == 3
    assert len({row["run_directory"] for row in report["results"]}) == 4


def test_provider_balance_error_is_distinct_from_model_quality():
    row = complete()
    row.update(error="账户余额不足", acp_error={"code":-32603, "message":"Internal error: Insufficient Balance (request_id: example)"})
    assert classify(row)["status"] == "run_failed"
    assert row["failure_category"] == "provider_balance_exhausted"


def test_repetition_stops_after_explicit_provider_balance_error(tmp_path, monkeypatch):
    calls = []
    def run(command, cwd):
        calls.append(command)
        folder = tmp_path / "runs" / "p7-1"
        folder.mkdir(parents=True)
        row = complete()
        row.update(error="余额不足", acp_error={"message":"Insufficient Balance"})
        (folder / "summary.json").write_text(json.dumps(summarize([classify(row)])))
        return SimpleNamespace(returncode=1)
    monkeypatch.setattr("scripts.agent_modeling_trial.subprocess.run", run)
    args = Namespace(cases=["p7", "p6"], repeats=2, output=tmp_path, delivery="vision", timeout=1200,
                     source="source.jpg", study="study", dsh="dsh", freecad="FreeCAD", background=True, reasoning="low")
    assert isolated_runs(args) == 1 and len(calls) == 1
    report = json.loads((tmp_path / "summary.json").read_text())
    assert report["stopped_reason"] == "provider_balance_exhausted"
    assert report["requested_trials"] == 4 and report["attempted"] == 1

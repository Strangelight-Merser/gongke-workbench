"""试验最终分类：区分执行失败、图纸不符和资料待复核，不靠初次读数否决后续纠正。"""


def classify(row):
    audit = row.get("audit", {})
    reasons = []
    diagnostic = str(row.get("acp_error", {}).get("message", ""))
    if "Insufficient Balance" in diagnostic:
        row["failure_category"] = "provider_balance_exhausted"
    if row.get("error") or not row.get("transport_completed") or row.get("cancel_pending"):
        reasons.append("agent_run_incomplete")
    for gate in ("input_read", "native_tree", "saved_current_revision", "archive_valid", "self_check_current_revision"):
        if audit.get(gate) is not True:
            reasons.append(gate)
    construction = not reasons
    if not row.get("reopened", {}).get("verified"):
        reasons.append("saved_model_reopen_not_verified")
    if audit.get("reference_pass") is False:
        reasons.append("independent_drawing_check_failed")
    if row.get("audit_error") or audit.get("error"):
        reasons.append("independent_audit_incomplete")
    if "agent_run_incomplete" in reasons:
        status = "run_failed"
    elif not construction:
        status = "modeling_failed"
    elif "saved_model_reopen_not_verified" in reasons:
        status = "reopen_failed"
    elif "independent_audit_incomplete" in reasons:
        status = "verification_failed"
    elif audit.get("reference_pass") is False:
        status = "drawing_mismatch"
    elif audit.get("reference_pass") is not True or audit.get("requires_drawing_review"):
        status = "review_required"
    else:
        status = "passed"
    row.update(status=status, failure_reasons=reasons,
               construction_passed=construction and row.get("reopened", {}).get("verified") is True,
               modeling_passed=status == "passed",
               initial_reading_mismatch=row.get("vision", {}).get("verified") is False)
    return row


def summarize(results):
    return {"attempted": len(results), "prompts_sent": sum(bool(r.get("prompt_sent")) for r in results),
            "modeling_prompts_sent": sum(bool(r.get("modeling_prompt_sent")) for r in results),
            "passed": sum(r["status"] == "passed" for r in results),
            "review_required": sum(r["status"] == "review_required" for r in results),
            "failed": sum(r["status"] not in {"passed", "review_required"} for r in results),
            "construction_passed": sum(bool(r.get("construction_passed")) for r in results),
            "construction_pass_rate": sum(bool(r.get("construction_passed")) for r in results)/len(results) if results else None,
            "automatic_pass_rate": sum(r["status"] == "passed" for r in results)/len(results) if results else None,
            "results": results}

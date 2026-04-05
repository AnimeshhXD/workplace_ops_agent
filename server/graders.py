# Copyright (c) Meta Platforms, Inc. and affiliates.
"""Deterministic task graders: each returns a score in [0.0, 1.0]."""

from __future__ import annotations

from typing import Any

from .tasks import TASKS, TaskName


def _bug_keyword_hits(text_lower: str) -> int:
    exp = TASKS["hard"]["expected"]
    return sum(1 for k in exp["bug_slack_substrings"] if k in text_lower)


def hard_bug_reply_quality_ok(state: dict[str, Any]) -> bool:
    exp = TASKS["hard"]["expected"]
    bug_id = exp["first_slack_id"]
    body = (state.get("slack_replies") or {}).get(bug_id, "").lower()
    need = int(exp.get("bug_slack_min_required", 3))
    return _bug_keyword_hits(body) >= need


def hard_client_email_ok(state: dict[str, Any]) -> bool:
    exp = TASKS["hard"]["expected"]
    body = (state.get("email_replies") or {}).get(exp["client_email_id"], "").lower()
    return all(s in body for s in exp["client_reply_substrings"])


def hard_calendar_ok(state: dict[str, Any]) -> bool:
    exp = TASKS["hard"]["expected"]
    cal_id = exp["calendar_id"]
    events = {e["id"]: e for e in state.get("calendar_events") or []}
    cal = events.get(cal_id)
    return bool(
        cal
        and cal.get("title") == exp["calendar_title"]
        and cal.get("start_iso") == exp["calendar_start"]
        and cal.get("end_iso") == exp["calendar_end"]
    )


def _events_overlap(a_start: str, a_end: str, b_start: str, b_end: str) -> bool:
    """ISO8601 naive string compare sufficient for fixed dataset."""
    return not (a_end <= b_start or b_end <= a_start)


def _first_milestone_step(
    trace: list[dict[str, Any]], want_type: str, want_target: str, require_ok: bool = True
) -> int | None:
    for i, row in enumerate(trace):
        if row.get("type") != want_type or row.get("target_id") != want_target:
            continue
        if require_ok and not row.get("ok"):
            continue
        return i
    return None


def grade_easy(state: dict[str, Any]) -> float:
    spec = TASKS["easy"]
    expected: dict[str, str] = spec["expected"]["email_labels"]
    got = state.get("email_classifications") or {}
    if not expected:
        return 0.0
    correct = sum(1 for eid, label in expected.items() if got.get(eid) == label)
    return correct / len(expected)


def grade_medium(state: dict[str, Any]) -> float:
    spec = TASKS["medium"]
    exp = spec["expected"]
    events = {e["id"]: e for e in state.get("calendar_events") or []}
    cal_a = events.get("cal_a")
    cal_b = events.get("cal_b")
    if not cal_a or not cal_b:
        return 0.0

    overlap = _events_overlap(
        cal_a["start_iso"], cal_a["end_iso"], cal_b["start_iso"], cal_b["end_iso"]
    )
    resolved_time = (
        cal_b["start_iso"] == exp["required_start_iso"]
        and cal_b["end_iso"] == exp["required_end_iso"]
    )
    slack_body = (state.get("slack_replies") or {}).get(exp["notify_slack_id"], "").lower()
    notified = all(s in slack_body for s in exp["notify_substrings"])

    parts = [
        0.0 if overlap else 1.0,
        1.0 if resolved_time else 0.0,
        1.0 if notified else 0.0,
    ]
    return sum(parts) / len(parts)


def grade_hard(state: dict[str, Any]) -> float:
    """
    Multi-axis rubric (deterministic, partial credit):
    0.4 completion + 0.3 priority_order + 0.2 response_quality + 0.1 efficiency
    """
    exp = TASKS["hard"]["expected"]
    trace = list(state.get("action_trace") or [])
    steps = int(state.get("step_count") or 0)
    max_steps = int(state.get("max_steps") or 18)

    bug_id = exp["first_slack_id"]
    email_id = exp["client_email_id"]
    cal_id = exp["calendar_id"]

    bug_ok = hard_bug_reply_quality_ok(state)

    email_ok = hard_client_email_ok(state)
    cal_ok = hard_calendar_ok(state)

    completion = sum(1.0 for x in (bug_ok, email_ok, cal_ok) if x) / 3.0

    i_bug = _first_milestone_step(trace, "respond_slack", bug_id, require_ok=True)
    i_mail = _first_milestone_step(trace, "reply_email", email_id, require_ok=True)
    i_cal = _first_milestone_step(trace, "schedule_meeting", cal_id, require_ok=True)

    if i_bug is not None and i_mail is not None and i_cal is not None:
        if i_bug < i_mail < i_cal:
            priority_order = 1.0
        elif i_bug < i_mail:
            priority_order = 0.55
        elif i_bug < i_cal:
            priority_order = 0.35
        else:
            priority_order = 0.12
    else:
        found = sum(1 for x in (i_bug, i_mail, i_cal) if x is not None)
        priority_order = 0.14 * found

    response_quality = 0.0
    if bug_ok:
        response_quality += 0.45
    if email_ok:
        response_quality += 0.45
    if cal_ok:
        response_quality += 0.10
    response_quality = min(1.0, response_quality)

    ideal = int(exp.get("ideal_step_count", 6))
    if steps <= ideal:
        efficiency = 1.0
    else:
        span = max(1, max_steps - ideal)
        over = min(steps - ideal, span)
        efficiency = max(0.0, 1.0 - (over / span))

    score = (
        0.4 * completion
        + 0.3 * priority_order
        + 0.2 * response_quality
        + 0.1 * efficiency
    )
    if not bug_ok and (email_ok or cal_ok):
        score *= 0.45
    return max(0.0, min(1.0, score))


def grade(task_id: TaskName, state: dict[str, Any]) -> float:
    if task_id == "easy":
        return grade_easy(state)
    if task_id == "medium":
        return grade_medium(state)
    return grade_hard(state)

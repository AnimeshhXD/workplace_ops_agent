# Copyright (c) Meta Platforms, Inc. and affiliates.
"""Step reward shaping: trajectory-aware, bounded, deterministic."""

from __future__ import annotations

from typing import Any

from .graders import (
    grade,
    hard_bug_reply_quality_ok,
    hard_calendar_ok,
    hard_client_email_ok,
)
from .tasks import TASKS, TaskName

R_CLASSIFY_OK = 0.2
R_CLASSIFY_BAD = -0.1
R_REPLY_OK = 0.4
R_REPLY_BAD = -0.3
R_SCHEDULE_OK = 0.5
R_CONFLICT_UNRESOLVED = -0.2
R_TASK_DONE = 1.0
R_REPEAT_CONSECUTIVE = -0.2
R_REPEAT_LOOP_EXTRA = -0.1
R_URGENT_IGNORE = -0.5
R_DELAY_HIGH = -0.3
R_PRIORITY_ORDER_BONUS = 0.3
R_CONTEXT_SWITCH = -0.1
R_ATTENTION_STEP = -0.05
R_COMPLETION_BONUS = 1.5

STEP_REWARD_CLIP = 2.5


def _calendar_has_overlap(events: list[dict[str, Any]]) -> bool:
    ev = list(events)
    for i, a in enumerate(ev):
        for b in ev[i + 1 :]:
            if a["id"] == b["id"]:
                continue
            if not (a["end_iso"] <= b["start_iso"] or b["end_iso"] <= a["start_iso"]):
                return True
    return False


def compute_step_reward(
    *,
    task_id: TaskName,
    action_type: str,
    target_id: str,
    success: bool,
    detail: str,
    _state_before: dict[str, Any],
    state_after: dict[str, Any],
    is_duplicate_action: bool,
    urgent_violation: bool,
    repeat_streak: int,
    context_switch: bool,
    delay_high_fire: bool,
    priority_bonus_fire: bool,
    attention_overage_steps: int,
) -> tuple[float, dict[str, float]]:
    """Return (total_reward, breakdown). All branches deterministic."""
    breakdown: dict[str, float] = {}
    total = 0.0

    if is_duplicate_action:
        breakdown["repeat_consecutive"] = R_REPEAT_CONSECUTIVE
        total += R_REPEAT_CONSECUTIVE
    if repeat_streak >= 3:
        breakdown["repeat_loop"] = R_REPEAT_LOOP_EXTRA
        total += R_REPEAT_LOOP_EXTRA

    if urgent_violation:
        breakdown["urgent_misorder"] = R_URGENT_IGNORE
        total += R_URGENT_IGNORE

    if delay_high_fire:
        breakdown["delay_high_priority"] = R_DELAY_HIGH
        total += R_DELAY_HIGH

    if priority_bonus_fire:
        breakdown["priority_order_bonus"] = R_PRIORITY_ORDER_BONUS
        total += R_PRIORITY_ORDER_BONUS

    if context_switch:
        breakdown["context_switch"] = R_CONTEXT_SWITCH
        total += R_CONTEXT_SWITCH

    if attention_overage_steps > 0:
        att = R_ATTENTION_STEP * attention_overage_steps
        breakdown["attention_budget"] = att
        total += att

    spec = TASKS[task_id]

    if action_type == "classify_email" and success:
        eid = detail.split(":", 1)[0] if ":" in detail else ""
        exp = spec.get("expected", {})
        if task_id == "easy":
            expected_labels = exp.get("email_labels", {})
            if eid in expected_labels and state_after.get("email_classifications", {}).get(
                eid
            ) == expected_labels[eid]:
                breakdown["classify"] = R_CLASSIFY_OK
                total += R_CLASSIFY_OK
            elif eid in expected_labels:
                breakdown["classify"] = R_CLASSIFY_BAD
                total += R_CLASSIFY_BAD
        elif task_id == "hard":
            pass
    elif action_type == "classify_email" and not success:
        if task_id != "hard":
            breakdown["classify"] = R_CLASSIFY_BAD
            total += R_CLASSIFY_BAD

    if action_type == "reply_email":
        if not success or "reply recorded" not in detail.lower():
            breakdown["reply"] = R_REPLY_BAD
            total += R_REPLY_BAD
        elif urgent_violation:
            pass
        elif task_id == "hard":
            if hard_client_email_ok(state_after):
                breakdown["reply"] = R_REPLY_OK
                total += R_REPLY_OK
        else:
            breakdown["reply"] = R_REPLY_OK
            total += R_REPLY_OK

    if action_type == "schedule_meeting":
        if not success:
            breakdown["schedule"] = -0.15
            total -= 0.15
        elif urgent_violation:
            pass
        elif task_id == "hard":
            if success and "updated" in detail.lower():
                if hard_calendar_ok(state_after):
                    breakdown["schedule"] = R_SCHEDULE_OK
                    total += R_SCHEDULE_OK
                else:
                    breakdown["schedule"] = -0.1
                    total -= 0.1
        elif success and "updated" in detail.lower():
            breakdown["schedule"] = R_SCHEDULE_OK
            total += R_SCHEDULE_OK

    if action_type == "respond_slack":
        if not success:
            breakdown["reply"] = R_REPLY_BAD
            total += R_REPLY_BAD
        elif urgent_violation:
            pass
        elif task_id == "hard":
            bug = TASKS["hard"]["expected"]["first_slack_id"]
            if target_id == bug and hard_bug_reply_quality_ok(state_after):
                breakdown["reply"] = R_REPLY_OK
                total += R_REPLY_OK
        else:
            breakdown["reply"] = R_REPLY_OK
            total += R_REPLY_OK

    if action_type == "complete_task" and success:
        breakdown["task"] = R_TASK_DONE
        total += R_TASK_DONE

    if task_id == "medium" and _calendar_has_overlap(state_after.get("calendar_events", [])):
        breakdown["conflict"] = R_CONFLICT_UNRESOLVED
        total += R_CONFLICT_UNRESOLVED

    total = max(-STEP_REWARD_CLIP, min(STEP_REWARD_CLIP, total))
    return total, breakdown


def maybe_completion_bonus(
    task_id: TaskName, state_dict: dict[str, Any], already_applied: bool
) -> tuple[float, bool]:
    if already_applied:
        return 0.0, False
    g = grade(task_id, state_dict)
    if g >= 0.999:
        return R_COMPLETION_BONUS, True
    return 0.0, False

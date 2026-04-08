# Copyright (c) Meta Platforms, Inc. and affiliates.
"""Core Gym-style environment: reset, step, state."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, Optional, Set
from uuid import UUID

from openenv.core.env_server.interfaces import Environment

from .anti_exploit import ActionDiversityTracker, adjust_reward_for_anti_exploit
from .graders import grade, hard_client_email_ok
from .models import (
    CalendarEventItem,
    EmailItem,
    SlackMessageItem,
    TaskBoardItem,
    WorkplaceAction,
    WorkplaceObservation,
    WorkplaceState,
)
from .reward import compute_step_reward, maybe_completion_bonus
from .tasks import TASKS, TaskName
from .validation import ActionValidator, ValidationError

logger = logging.getLogger(__name__)


def _deterministic_uuid(task_id: str, seed: int, counter: int) -> str:
    """
    Generate deterministic UUID-like string from seed.
    Same seed + task_id + counter = same result.
    """
    import hashlib
    base = f"{task_id}:{seed}:{counter}"
    digest = hashlib.sha256(base.encode()).hexdigest()
    # Format as UUID-like string
    return f"{digest[:8]}-{digest[8:12]}-{digest[12:16]}-{digest[16:20]}-{digest[20:32]}"


def _fp(action: WorkplaceAction) -> str:
    return f"{action.type}|{action.target_id}|{action.content or ''}"


def _parse_schedule_content(raw: Optional[str]) -> dict[str, str]:
    if not raw:
        return {}
    raw = raw.strip()
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items()}
    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse schedule JSON: {e}")
        pass
    m = re.search(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})", raw)
    times = re.findall(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})", raw)
    out: dict[str, str] = {}
    if "title:" in raw.lower():
        title_part = raw.split("title:", 1)[-1].split(",", 1)[0].strip()
        if title_part:
            out["title"] = title_part
    if len(times) >= 2:
        out["start_iso"], out["end_iso"] = times[0], times[1]
    elif m:
        out["start_iso"] = m.group(1)
    return out


def _task_priority_tier(t: dict[str, Any]) -> str:
    if "priority_tier" in t:
        return str(t["priority_tier"])
    p = str(t.get("priority", "normal")).lower()
    if p in ("urgent", "high"):
        return "HIGH"
    if p == "low":
        return "LOW"
    return "MEDIUM"


class WorkplaceOpsEnvironment(Environment[WorkplaceAction, WorkplaceObservation, WorkplaceState]):
    """Simulates cross-system workplace assistant workflows."""

    SUPPORTS_CONCURRENT_SESSIONS = True

    def __init__(self) -> None:
        super().__init__()
        self._st = self._blank_state()
        # ID caches for O(1) lookup (populated at reset)
        self._email_ids: Set[str] = set()
        self._slack_ids: Set[str] = set()
        self._calendar_ids: Set[str] = set()
        self._task_ids: Set[str] = set()
        # Action diversity tracking for anti-exploit
        self._action_tracker = ActionDiversityTracker()

    def _blank_state(self) -> WorkplaceState:
        return WorkplaceState(
            episode_id="",  # Set deterministically at reset
            step_count=0,
            task_id="easy",
            seed=0,
            max_steps=50,
        )

    def _reset_rubric(self) -> None:
        """Reset grading internal state (if any). Placeholder for compatibility."""
        pass

    def _load_scenario(self, task_id: TaskName, seed: int) -> None:
        spec = TASKS[task_id]
        self._st.task_id = task_id
        self._st.seed = seed
        self._st.max_steps = int(spec.get("episode_max_steps", 50))
        self._st.emails = [dict(e) for e in spec["emails"]]
        self._st.slack_messages = [dict(s) for s in spec["slack_messages"]]
        self._st.calendar_events = [dict(c) for c in spec["calendar_events"]]
        self._st.tasks = [dict(t) for t in spec["tasks"]]
        self._st.email_classifications = {}
        self._st.email_replies = {}
        self._st.slack_replies = {}
        self._st.escalations = {}
        self._st.completed_task_ids = []
        self._st.task_completion_order = []
        self._st.action_trace = []
        self._st.action_fingerprints = []
        self._st.repeat_streak = 0
        self._st.last_focus_key = ""
        self._st.context_switch_count = 0
        self._st.urgent_penalty_applied = False
        self._st.delay_high_penalty_applied = False
        self._st.priority_order_bonus_applied = False
        self._st.context_switch_penalty_applied = False
        self._st.completion_bonus_applied = False
        self._st.last_action_result = ""
        self._st.last_reward_breakdown = {}

        # Index all valid IDs for O(1) lookup
        self._email_ids = {e["id"] for e in self._st.emails}
        self._slack_ids = {s["id"] for s in self._st.slack_messages}
        self._calendar_ids = {c["id"] for c in self._st.calendar_events}
        self._task_ids = {t["id"] for t in self._st.tasks}

        # Reset action diversity tracker
        self._action_tracker = ActionDiversityTracker()

    def _state_as_dict(self) -> dict[str, Any]:
        return {
            "email_classifications": dict(self._st.email_classifications),
            "email_replies": dict(self._st.email_replies),
            "slack_replies": dict(self._st.slack_replies),
            "calendar_events": [dict(e) for e in self._st.calendar_events],
            "completed_task_ids": list(self._st.completed_task_ids),
            "task_completion_order": list(self._st.task_completion_order),
            "action_trace": [dict(x) for x in self._st.action_trace],
            "tasks": [dict(t) for t in self._st.tasks],
            "step_count": self._st.step_count,
            "max_steps": self._st.max_steps,
        }

    def _build_observation(self, done: bool, reward: Optional[float], include_debug: bool = False) -> WorkplaceObservation:
        emails = [
            EmailItem(
                id=e["id"],
                subject=e["subject"],
                from_address=e["from_address"],
                body_preview=e["body_preview"],
                priority_tier=e.get("priority_tier", "MEDIUM"),
            )
            for e in self._st.emails
        ]
        slack = [
            SlackMessageItem(
                id=s["id"],
                channel=s["channel"],
                sender=s["sender"],
                body=s["body"],
                urgent=bool(s.get("urgent", False)),
                priority_tier=s.get("priority_tier", "MEDIUM"),
            )
            for s in self._st.slack_messages
        ]
        cal = [
            CalendarEventItem(
                id=c["id"],
                title=c["title"],
                start_iso=c["start_iso"],
                end_iso=c["end_iso"],
                attendees=list(c.get("attendees", [])),
                priority_tier=c.get("priority_tier", "MEDIUM"),
            )
            for c in self._st.calendar_events
        ]
        tasks = [
            TaskBoardItem(
                id=t["id"],
                title=t["title"],
                priority=t.get("priority", "normal"),
                status=t.get("status", "pending"),
                priority_tier=_task_priority_tier(t),
            )
            for t in self._st.tasks
        ]
        
        # SECURITY FIX: Hide grader_score and reward_breakdown from metadata in production
        # Agent should NOT be able to reverse-engineer reward function or grading logic
        metadata = {
            "episode_id": self._st.episode_id,
        }
        
        # Only include debug info if explicitly requested or in dev mode
        if include_debug:
            metadata["grader_score"] = grade(self._st.task_id, self._state_as_dict())
            metadata["reward_breakdown"] = dict(self._st.last_reward_breakdown)
        
        return WorkplaceObservation(
            emails=emails,
            slack_messages=slack,
            calendar_events=cal,
            tasks=tasks,
            last_action_result=self._st.last_action_result,
            task_id=self._st.task_id,
            step_count=self._st.step_count,
            max_steps=self._st.max_steps,
            done=done,
            reward=reward,
            metadata=metadata,
        )

    def _overlap_exists(self) -> bool:
        ev = self._st.calendar_events
        for i, a in enumerate(ev):
            for b in ev[i + 1 :]:
                if not (a["end_iso"] <= b["start_iso"] or b["end_iso"] <= a["start_iso"]):
                    return True
        return False

    def _natural_done(self) -> bool:
        tid = self._st.task_id
        if tid == "easy":
            ids = {e["id"] for e in self._st.emails}
            return bool(ids and ids == set(self._st.email_classifications.keys()))
        if tid == "medium":
            exp = TASKS["medium"]["expected"]
            body = self._st.slack_replies.get(exp["notify_slack_id"], "").lower()
            notified = all(s in body for s in exp["notify_substrings"])
            ev = {e["id"]: e for e in self._st.calendar_events}
            cal_b = ev.get("cal_b")
            time_ok = bool(
                cal_b
                and cal_b["start_iso"] == exp["required_start_iso"]
                and cal_b["end_iso"] == exp["required_end_iso"]
            )
            return notified and time_ok and not self._overlap_exists()
        if tid == "hard":
            return grade("hard", self._state_as_dict()) >= 0.99
        return False

    def _hard_first_slack_id(self) -> str:
        return str(TASKS["hard"]["expected"]["first_slack_id"])

    def _urgent_slack_pending(self) -> bool:
        if self._st.task_id != "hard":
            return False
        bug = self._hard_first_slack_id()
        return bug not in self._st.slack_replies

    def _urgent_violation(self, action: WorkplaceAction) -> bool:
        if not self._urgent_slack_pending():
            return False
        bug = self._hard_first_slack_id()
        if action.type == "respond_slack" and action.target_id == bug:
            return False
        return True

    def _execute(self, action: WorkplaceAction) -> tuple[bool, str]:
        """Execute action with detailed error reporting. Returns (success, detail_message)."""
        success = True
        detail = ""
        
        try:
            if action.type == "classify_email":
                ids = {e["id"] for e in self._st.emails}
                if action.target_id not in ids:
                    success = False
                    detail = "unknown email id"
                elif not action.content or action.content.lower() not in ("spam", "important"):
                    success = False
                    detail = "label must be spam or important"
                else:
                    label = action.content.lower()
                    self._st.email_classifications[action.target_id] = label
                    self._action_tracker.record_classification(action.target_id, label)
                    detail = f"{action.target_id}:{label}"
            
            elif action.type == "reply_email":
                ids = {e["id"] for e in self._st.emails}
                if action.target_id not in ids:
                    success = False
                    detail = "unknown email id"
                elif not action.content:
                    success = False
                    detail = "empty reply"
                else:
                    self._st.email_replies[action.target_id] = action.content
                    detail = "reply recorded"
            
            elif action.type == "schedule_meeting":
                ids = {c["id"] for c in self._st.calendar_events}
                if action.target_id not in ids:
                    success = False
                    detail = "unknown calendar id"
                else:
                    fields = _parse_schedule_content(action.content)
                    updated = False
                    for c in self._st.calendar_events:
                        if c["id"] == action.target_id:
                            if "title" in fields:
                                c["title"] = fields["title"]
                            if "start_iso" in fields:
                                c["start_iso"] = fields["start_iso"]
                            if "end_iso" in fields:
                                c["end_iso"] = fields["end_iso"]
                            detail = "event updated"
                            updated = True
                            break
                    if not updated:
                        success = False
                        detail = "event not found"
            
            elif action.type == "respond_slack":
                ids = {s["id"] for s in self._st.slack_messages}
                if action.target_id not in ids:
                    success = False
                    detail = "unknown slack id"
                elif not action.content:
                    success = False
                    detail = "empty slack response"
                else:
                    self._st.slack_replies[action.target_id] = action.content
                    self._st.task_completion_order.append(action.target_id)
                    detail = "slack response recorded"
            
            elif action.type == "complete_task":
                ids = {t["id"] for t in self._st.tasks}
                if action.target_id not in ids:
                    success = False
                    detail = "unknown task id"
                else:
                    for t in self._st.tasks:
                        if t["id"] == action.target_id:
                            t["status"] = "done"
                            break
                    if action.target_id not in self._st.completed_task_ids:
                        self._st.completed_task_ids.append(action.target_id)
                    self._st.task_completion_order.append(action.target_id)
                    detail = "task marked done"
            
            elif action.type == "escalate":
                if not action.target_id:
                    success = False
                    detail = "missing target"
                else:
                    self._st.escalations[action.target_id] = action.content or "escalated"
                    detail = "escalation logged"
            
            else:
                success = False
                detail = "unsupported action"
        
        except Exception as e:
            # Catch any unexpected errors and report them instead of crashing
            logger.exception(f"Error executing action {action.type}: {e}")
            success = False
            detail = f"internal error: {type(e).__name__}"
        
        return success, detail

    def reset(
        self,
        seed: Optional[int] = None,
        episode_id: Optional[str] = None,
        **kwargs: Any,
    ) -> WorkplaceObservation:
        self._reset_rubric()
        task_raw = kwargs.get("task") or kwargs.get("task_id") or "easy"
        if task_raw not in TASKS:
            task_raw = "easy"
        task_id: TaskName = task_raw  # type: ignore[assignment]
        s = int(seed or 0)
        self._st = self._blank_state()
        
        # Use deterministic UUID based on seed + task
        self._st.episode_id = episode_id or _deterministic_uuid(task_id, s, 0)
        self._st.step_count = 0
        self._load_scenario(task_id, s)
        self._st.last_action_result = (
            f"Reset scenario={task_id} seed={s}. Use workplace actions to complete the workflow."
        )
        return self._build_observation(done=False, reward=0.0)

    def step(
        self,
        action: WorkplaceAction,
        timeout_s: Optional[float] = None,
        **kwargs: Any,
    ) -> WorkplaceObservation:
        """Execute one step with strict validation and anti-exploit measures."""
        _ = timeout_s
        
        # ========== STRICT ACTION VALIDATION ==========
        validation_err, validated_action = ActionValidator.validate_action(
            action,
            task_id=self._st.task_id,
            valid_email_ids=self._email_ids,
            valid_slack_ids=self._slack_ids,
            valid_calendar_ids=self._calendar_ids,
            valid_task_ids=self._task_ids,
        )
        
        if validation_err:
            # Return safe observation with error message, no state change
            self._st.step_count += 1
            self._st.last_action_result = f"validation error: {validation_err.message}"
            logger.warning(f"Action validation failed: {validation_err.code} - {validation_err.message}")
            
            obs = self._build_observation(done=False, reward=-0.5)
            obs.metadata["info"] = {
                "success": False,
                "detail": validation_err.message,
                "error_code": validation_err.code,
                "validation_error": True,
            }
            return self._apply_transform(obs)
        
        action = validated_action  # Use validated action
        
        # ========== EXECUTION & STATE TRACKING ==========
        prev = self._state_as_dict()
        fp = _fp(action)
        dup = bool(
            self._st.action_fingerprints and self._st.action_fingerprints[-1] == fp
        )
        if dup:
            self._st.repeat_streak += 1
        else:
            self._st.repeat_streak = 0
        self._st.action_fingerprints.append(fp)

        focus_key = f"{action.type}:{action.target_id}"
        if self._st.last_focus_key and self._st.last_focus_key != focus_key:
            self._st.context_switch_count += 1
        self._st.last_focus_key = focus_key

        urgent_charge = self._urgent_violation(action) and not self._st.urgent_penalty_applied

        # Execute action
        success, detail = self._execute(action)
        self._st.action_trace.append(
            {"type": action.type, "target_id": action.target_id, "ok": success}
        )

        self._st.last_action_result = detail if success else f"error: {detail}"
        self._st.step_count += 1

        # ========== MILESTONE PENALTIES ==========
        exp_hard = TASKS["hard"]["expected"] if self._st.task_id == "hard" else {}
        delay_fire = False
        if self._st.task_id == "hard" and not self._st.delay_high_penalty_applied:
            deadline = int(exp_hard.get("urgent_handle_deadline_step", 4))
            bug = self._hard_first_slack_id()
            if (
                self._st.step_count >= deadline
                and bug not in self._st.slack_replies
            ):
                delay_fire = True
                self._st.delay_high_penalty_applied = True

        prio_bonus = False
        if (
            self._st.task_id == "hard"
            and success
            and action.type == "reply_email"
            and action.target_id == exp_hard.get("client_email_id")
            and self._hard_first_slack_id() in self._st.slack_replies
            and not self._st.priority_order_bonus_applied
            and hard_client_email_ok(self._state_as_dict())
        ):
            prio_bonus = True
            self._st.priority_order_bonus_applied = True

        ctx_penalty = (
            not self._st.context_switch_penalty_applied
            and self._st.context_switch_count >= 3
            and self._st.step_count <= 8
        )
        if ctx_penalty:
            self._st.context_switch_penalty_applied = True

        budget = int(exp_hard.get("attention_budget_steps", 10**6))
        att_steps = 0
        if self._st.task_id == "hard" and self._st.step_count > budget:
            att_steps = 1

        # ========== COMPUTE BASE REWARD ==========
        reward, breakdown = compute_step_reward(
            task_id=self._st.task_id,
            action_type=action.type,
            target_id=action.target_id,
            success=success,
            detail=detail,
            _state_before=prev,
            state_after=self._state_as_dict(),
            is_duplicate_action=dup,
            urgent_violation=urgent_charge,
            repeat_streak=self._st.repeat_streak,
            context_switch=ctx_penalty,
            delay_high_fire=delay_fire,
            priority_bonus_fire=prio_bonus,
            attention_overage_steps=att_steps,
        )
        
        if urgent_charge:
            self._st.urgent_penalty_applied = True

        # ========== ANTI-EXPLOIT ADJUSTMENT ==========
        # Track action for diversity analysis
        self._action_tracker.record_action(action.type, action.target_id, success, reward)
        
        # Apply anti-exploit penalties
        reward = adjust_reward_for_anti_exploit(
            reward,
            self._action_tracker,
            action.type,
            action.target_id,
            success,
            self._st.task_id,
        )
        breakdown["anti_exploit_adjusted"] = reward

        # ========== COMPLETION BONUS ==========
        done = self._st.step_count >= self._st.max_steps or self._natural_done()
        bonus, applied = maybe_completion_bonus(
            self._st.task_id,
            self._state_as_dict(),
            self._st.completion_bonus_applied,
        )
        if done and applied:
            self._st.completion_bonus_applied = True
            reward += bonus
            breakdown = {**breakdown, "completion_bonus": bonus}

        self._st.last_reward_breakdown = breakdown
        obs = self._build_observation(done=done, reward=reward)
        obs.metadata["info"] = {
            "success": success,
            "detail": detail,
            "duplicate_action": dup,
            "repeat_streak": self._st.repeat_streak,
            "anti_exploit_adjusted": True,
        }
        return self._apply_transform(obs)

    @property
    def state(self) -> WorkplaceState:
        return self._st

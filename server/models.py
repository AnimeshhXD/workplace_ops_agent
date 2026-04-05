# Copyright (c) Meta Platforms, Inc. and affiliates.
"""Pydantic models: actions, observations, and environment state."""

from __future__ import annotations

from typing import Any, Literal, Optional

from openenv.core.env_server.types import Action, Observation, State
from pydantic import BaseModel, Field

ActionType = Literal[
    "classify_email",
    "reply_email",
    "schedule_meeting",
    "respond_slack",
    "complete_task",
    "escalate",
]

PriorityTier = Literal["HIGH", "MEDIUM", "LOW"]


class EmailItem(BaseModel):
    id: str
    subject: str
    from_address: str
    body_preview: str
    priority_tier: PriorityTier = "MEDIUM"


class SlackMessageItem(BaseModel):
    id: str
    channel: str
    sender: str
    body: str
    urgent: bool = False
    priority_tier: PriorityTier = "MEDIUM"


class CalendarEventItem(BaseModel):
    id: str
    title: str
    start_iso: str
    end_iso: str
    attendees: list[str] = Field(default_factory=list)
    priority_tier: PriorityTier = "MEDIUM"


class TaskBoardItem(BaseModel):
    id: str
    title: str
    priority: Literal["low", "normal", "high", "urgent"] = "normal"
    status: Literal["pending", "in_progress", "done"] = "pending"
    priority_tier: PriorityTier = "MEDIUM"


class WorkplaceAction(Action):
    """Agent action across email, calendar, Slack, and task systems."""

    type: ActionType = Field(..., description="High-level workplace operation")
    target_id: str = Field(..., description="Entity id (email, slack, event, task)")
    content: Optional[str] = Field(
        default=None,
        description="Payload: label, reply text, ISO schedule JSON, or completion note",
    )


class WorkplaceObservation(Observation):
    """What the agent sees after reset or each step."""

    emails: list[EmailItem] = Field(default_factory=list)
    slack_messages: list[SlackMessageItem] = Field(default_factory=list)
    calendar_events: list[CalendarEventItem] = Field(default_factory=list)
    tasks: list[TaskBoardItem] = Field(default_factory=list)
    last_action_result: str = ""
    task_id: str = Field(
        default="easy",
        description="Current benchmark task: easy | medium | hard",
    )
    step_count: int = 0
    max_steps: int = 50


class WorkplaceState(State):
    """Full internal state (episode + domain)."""

    task_id: str = "easy"
    seed: int = 0
    max_steps: int = 50

    emails: list[dict[str, Any]] = Field(default_factory=list)
    slack_messages: list[dict[str, Any]] = Field(default_factory=list)
    calendar_events: list[dict[str, Any]] = Field(default_factory=list)
    tasks: list[dict[str, Any]] = Field(default_factory=list)

    email_classifications: dict[str, str] = Field(default_factory=dict)
    email_replies: dict[str, str] = Field(default_factory=dict)
    slack_replies: dict[str, str] = Field(default_factory=dict)
    escalations: dict[str, str] = Field(default_factory=dict)

    completed_task_ids: list[str] = Field(default_factory=list)
    task_completion_order: list[str] = Field(default_factory=list)
    action_trace: list[dict[str, Any]] = Field(default_factory=list)

    action_fingerprints: list[str] = Field(default_factory=list)
    repeat_streak: int = 0
    last_focus_key: str = ""
    context_switch_count: int = 0

    urgent_penalty_applied: bool = False
    delay_high_penalty_applied: bool = False
    priority_order_bonus_applied: bool = False
    context_switch_penalty_applied: bool = False
    completion_bonus_applied: bool = False

    last_action_result: str = ""
    last_reward_breakdown: dict[str, float] = Field(default_factory=dict)

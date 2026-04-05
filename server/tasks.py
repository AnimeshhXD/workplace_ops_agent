# Copyright (c) Meta Platforms, Inc. and affiliates.
"""Deterministic task scenarios and expected outcomes for graders."""

from __future__ import annotations

from typing import Any, Literal, TypedDict

TaskName = Literal["easy", "medium", "hard"]


class TaskSpec(TypedDict, total=False):
    task_id: TaskName
    difficulty: str
    description: str
    emails: list[dict[str, Any]]
    slack_messages: list[dict[str, Any]]
    calendar_events: list[dict[str, Any]]
    tasks: list[dict[str, Any]]
    expected: dict[str, Any]
    episode_max_steps: int


TASKS: dict[TaskName, TaskSpec] = {
    "easy": {
        "task_id": "easy",
        "difficulty": "easy",
        "description": "Classify inbox emails as spam vs important.",
        "emails": [
            {
                "id": "em_001",
                "subject": "WINNER!!! Claim your prize now",
                "from_address": "promo@lottery-spam.test",
                "body_preview": "Click here for free money guaranteed...",
                "priority_tier": "LOW",
            },
            {
                "id": "em_002",
                "subject": "Q3 board deck — review before Friday",
                "from_address": "ceo@company.internal",
                "body_preview": "Please review slides attached for board session.",
                "priority_tier": "HIGH",
            },
            {
                "id": "em_003",
                "subject": "Weekly digest: 47 unread newsletters",
                "from_address": "digest@newsletters.test",
                "body_preview": "Top stories you may have missed...",
                "priority_tier": "LOW",
            },
        ],
        "slack_messages": [],
        "calendar_events": [],
        "tasks": [],
        "expected": {
            "email_labels": {
                "em_001": "spam",
                "em_002": "important",
                "em_003": "spam",
            },
        },
    },
    "medium": {
        "task_id": "medium",
        "difficulty": "medium",
        "description": "Resolve overlapping meetings and notify stakeholders on Slack.",
        "emails": [],
        "slack_messages": [
            {
                "id": "sl_010",
                "channel": "#eng-calendar",
                "sender": "calendar-bot",
                "body": "Reminder: two events overlap tomorrow 2–3pm for Alice.",
                "urgent": False,
                "priority_tier": "MEDIUM",
            }
        ],
        "calendar_events": [
            {
                "id": "cal_a",
                "title": "1:1 Alice / Bob",
                "start_iso": "2024-06-11T14:00:00",
                "end_iso": "2024-06-11T15:00:00",
                "attendees": ["alice@company.internal", "bob@company.internal"],
                "priority_tier": "MEDIUM",
            },
            {
                "id": "cal_b",
                "title": "Sprint planning",
                "start_iso": "2024-06-11T14:30:00",
                "end_iso": "2024-06-11T15:30:00",
                "attendees": ["alice@company.internal", "team@company.internal"],
                "priority_tier": "MEDIUM",
            },
        ],
        "tasks": [],
        "expected": {
            "resolved_event_id": "cal_b",
            "required_start_iso": "2024-06-11T15:00:00",
            "required_end_iso": "2024-06-11T16:00:00",
            "notify_slack_id": "sl_010",
            "notify_substrings": ["rescheduled", "15:00", "16:00"],
        },
    },
    "hard": {
        "task_id": "hard",
        "difficulty": "hard",
        "description": (
            "Conflicting priorities: production incident Slack, angry client email, "
            "and an imminent meeting — tight step budget."
        ),
        "episode_max_steps": 18,
        "emails": [
            {
                "id": "em_client_cancel",
                "subject": "Re: contract — considering cancellation",
                "from_address": "vp@major-client.example",
                "body_preview": (
                    "Unless we see a concrete plan in the next hour, we will cancel "
                    "the renewal. Call me."
                ),
                "priority_tier": "HIGH",
            },
        ],
        "slack_messages": [
            {
                "id": "sl_prod_bug",
                "channel": "#incidents",
                "sender": "pagerduty",
                "body": "URGENT: production checkout is erroring — revenue impact, all hands on deck.",
                "urgent": True,
                "priority_tier": "HIGH",
            },
        ],
        "calendar_events": [
            {
                "id": "cal_imminent",
                "title": "Team standup — starts in 2 minutes",
                "start_iso": "2024-06-11T16:58:00",
                "end_iso": "2024-06-11T17:00:00",
                "attendees": ["you@company.internal", "team@company.internal"],
                "priority_tier": "MEDIUM",
            },
        ],
        "tasks": [],
        "expected": {
            "first_slack_id": "sl_prod_bug",
            "client_email_id": "em_client_cancel",
            "calendar_id": "cal_imminent",
            "expected_action_order": [
                ["respond_slack", "sl_prod_bug"],
                ["reply_email", "em_client_cancel"],
                ["schedule_meeting", "cal_imminent"],
            ],
            "bug_slack_substrings": ["investigating", "patch", "mitigation", "rollback", "fix"],
            "bug_slack_min_required": 3,
            "client_reply_substrings": ["renewal", "retain", "call", "mitigation", "plan"],
            "calendar_title": "Standup deferred — incident response",
            "calendar_start": "2024-06-11T17:30:00",
            "calendar_end": "2024-06-11T17:45:00",
            "urgent_handle_deadline_step": 4,
            "ideal_step_count": 6,
            "attention_budget_steps": 12,
            "attention_overage_penalty_per_step": 0.05,
        },
    },
}


def get_task(name: TaskName) -> TaskSpec:
    return TASKS[name]

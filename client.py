# Copyright (c) Meta Platforms, Inc. and affiliates.
"""Typed WebSocket client for workplace-ops-agent."""

from __future__ import annotations

from typing import Any, Dict

from openenv.core.client_types import StepResult
from openenv.core.env_client import EnvClient

try:
    from workplace_ops_agent.models import (
        CalendarEventItem,
        EmailItem,
        SlackMessageItem,
        TaskBoardItem,
        WorkplaceAction,
        WorkplaceObservation,
        WorkplaceState,
    )
except ImportError:
    from server.models import (
        CalendarEventItem,
        EmailItem,
        SlackMessageItem,
        TaskBoardItem,
        WorkplaceAction,
        WorkplaceObservation,
        WorkplaceState,
    )


class WorkplaceOpsEnv(EnvClient[WorkplaceAction, WorkplaceObservation, WorkplaceState]):
    """Client with persistent WebSocket session to the workplace environment."""

    def _step_payload(self, action: WorkplaceAction) -> Dict[str, Any]:
        return action.model_dump(mode="json")

    def _parse_result(self, payload: Dict[str, Any]) -> StepResult[WorkplaceObservation]:
        obs_data = payload.get("observation", {})

        emails = [
            EmailItem(
                id=e["id"],
                subject=e["subject"],
                from_address=e["from_address"],
                body_preview=e["body_preview"],
                priority_tier=e.get("priority_tier", "MEDIUM"),
            )
            for e in obs_data.get("emails") or []
        ]
        slack_messages = [
            SlackMessageItem(
                id=s["id"],
                channel=s["channel"],
                sender=s["sender"],
                body=s["body"],
                urgent=bool(s.get("urgent", False)),
                priority_tier=s.get("priority_tier", "MEDIUM"),
            )
            for s in obs_data.get("slack_messages") or []
        ]
        calendar_events = [
            CalendarEventItem(
                id=c["id"],
                title=c["title"],
                start_iso=c["start_iso"],
                end_iso=c["end_iso"],
                attendees=list(c.get("attendees", [])),
                priority_tier=c.get("priority_tier", "MEDIUM"),
            )
            for c in obs_data.get("calendar_events") or []
        ]
        tasks = [
            TaskBoardItem(
                id=t["id"],
                title=t["title"],
                priority=t.get("priority", "normal"),
                status=t.get("status", "pending"),
                priority_tier=t.get("priority_tier", "MEDIUM"),
            )
            for t in obs_data.get("tasks") or []
        ]

        observation = WorkplaceObservation(
            emails=emails,
            slack_messages=slack_messages,
            calendar_events=calendar_events,
            tasks=tasks,
            last_action_result=obs_data.get("last_action_result", ""),
            task_id=obs_data.get("task_id", "easy"),
            step_count=obs_data.get("step_count", 0),
            max_steps=obs_data.get("max_steps", 50),
            done=payload.get("done", False),
            reward=payload.get("reward"),
            metadata=obs_data.get("metadata", {}),
        )

        return StepResult(
            observation=observation,
            reward=payload.get("reward"),
            done=payload.get("done", False),
        )

    def _parse_state(self, payload: Dict[str, Any]) -> WorkplaceState:
        return WorkplaceState.model_validate(payload)

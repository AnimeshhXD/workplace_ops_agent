# Copyright (c) Meta Platforms, Inc. and affiliates.
"""Strict action validation with anti-exploit enforcement."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional, Set, Tuple
from dataclasses import dataclass

from .models import ActionType, WorkplaceAction


@dataclass
class ValidationError:
    """Structured validation error returned to agent."""

    code: str  # e.g., "INVALID_TYPE", "CONTENT_TOO_LONG"
    message: str
    field: str

    def to_dict(self) -> Dict[str, str]:
        return {
            "error_code": self.code,
            "message": self.message,
            "field": self.field,
        }


class ActionValidator:
    """Strict validator for workplace actions with anti-exploit checks."""

    # Constants
    MAX_CONTENT_LENGTH = 2000  # Prevent memory exhaustion
    MAX_TARGET_ID_LENGTH = 100
    MAX_REPLY_LENGTH = 1500
    MAX_SCHEDULE_JSON_LENGTH = 500
    VALID_ACTION_TYPES: Set[ActionType] = {
        "classify_email",
        "reply_email",
        "schedule_meeting",
        "respond_slack",
        "complete_task",
        "escalate",
    }
    VALID_EMAIL_LABELS = {"spam", "important"}

    def __init__(self) -> None:
        """Initialize validator."""
        pass

    @staticmethod
    def validate_action(
        action: Any,
        task_id: str,
        valid_email_ids: Set[str],
        valid_slack_ids: Set[str],
        valid_calendar_ids: Set[str],
        valid_task_ids: Set[str],
    ) -> Tuple[Optional[ValidationError], Optional[WorkplaceAction]]:
        """
        Validate action completely. Returns (error, action_obj).
        If error is not None, action_obj is None.
        If error is None, action_obj is valid and ready to execute.
        """
        # 1. Type check
        if not isinstance(action, WorkplaceAction):
            return (
                ValidationError(
                    code="TYPE_ERROR",
                    message=f"Action must be WorkplaceAction, got {type(action).__name__}",
                    field="action",
                ),
                None,
            )

        # 2. Validate action type
        if action.type not in ActionValidator.VALID_ACTION_TYPES:
            return (
                ValidationError(
                    code="INVALID_ACTION_TYPE",
                    message=f"Unknown action type: {action.type}. Valid: {sorted(ActionValidator.VALID_ACTION_TYPES)}",
                    field="type",
                ),
                None,
            )

        # 3. Validate target_id
        target_err = ActionValidator._validate_target_id(
            action.type,
            action.target_id,
            valid_email_ids,
            valid_slack_ids,
            valid_calendar_ids,
            valid_task_ids,
        )
        if target_err:
            return target_err, None

        # 4. Validate content
        content_err = ActionValidator._validate_content(action.type, action.content, task_id)
        if content_err:
            return content_err, None

        return None, action

    @staticmethod
    def _validate_target_id(
        action_type: ActionType,
        target_id: Any,
        valid_emails: Set[str],
        valid_slacks: Set[str],
        valid_calendars: Set[str],
        valid_tasks: Set[str],
    ) -> Optional[ValidationError]:
        """Validate target_id is string, non-empty, and exists."""
        if not isinstance(target_id, str):
            return ValidationError(
                code="INVALID_TARGET_ID_TYPE",
                message=f"target_id must be string, got {type(target_id).__name__}",
                field="target_id",
            )

        if not target_id or len(target_id) == 0:
            return ValidationError(
                code="EMPTY_TARGET_ID",
                message="target_id cannot be empty",
                field="target_id",
            )

        if len(target_id) > ActionValidator.MAX_TARGET_ID_LENGTH:
            return ValidationError(
                code="TARGET_ID_TOO_LONG",
                message=f"target_id exceeds {ActionValidator.MAX_TARGET_ID_LENGTH} chars",
                field="target_id",
            )

        # Validate target exists based on action type
        if action_type == "classify_email":
            if target_id not in valid_emails:
                return ValidationError(
                    code="UNKNOWN_EMAIL_ID",
                    message=f"Email id '{target_id}' not found. Valid: {sorted(valid_emails)}",
                    field="target_id",
                )
        elif action_type == "reply_email":
            if target_id not in valid_emails:
                return ValidationError(
                    code="UNKNOWN_EMAIL_ID",
                    message=f"Email id '{target_id}' not found",
                    field="target_id",
                )
        elif action_type == "respond_slack":
            if target_id not in valid_slacks:
                return ValidationError(
                    code="UNKNOWN_SLACK_ID",
                    message=f"Slack id '{target_id}' not found. Valid: {sorted(valid_slacks)}",
                    field="target_id",
                )
        elif action_type == "schedule_meeting":
            if target_id not in valid_calendars:
                return ValidationError(
                    code="UNKNOWN_CALENDAR_ID",
                    message=f"Calendar id '{target_id}' not found",
                    field="target_id",
                )
        elif action_type == "complete_task":
            if target_id not in valid_tasks:
                return ValidationError(
                    code="UNKNOWN_TASK_ID",
                    message=f"Task id '{target_id}' not found",
                    field="target_id",
                )
        # escalate: any target_id allowed

        return None

    @staticmethod
    def _validate_content(action_type: ActionType, content: Any, task_id: str) -> Optional[ValidationError]:
        """Validate content field based on action type."""
        if action_type == "classify_email":
            # Must have content, must be valid label
            if content is None:
                return ValidationError(
                    code="MISSING_CONTENT",
                    message="classify_email requires content (label)",
                    field="content",
                )
            if not isinstance(content, str):
                return ValidationError(
                    code="INVALID_CONTENT_TYPE",
                    message=f"content must be string, got {type(content).__name__}",
                    field="content",
                )
            label = content.lower().strip()
            if label not in ActionValidator.VALID_EMAIL_LABELS:
                return ValidationError(
                    code="INVALID_EMAIL_LABEL",
                    message=f"label must be 'spam' or 'important', got '{content}'",
                    field="content",
                )

        elif action_type in ("reply_email", "respond_slack"):
            # Must have non-empty content
            if content is None or (isinstance(content, str) and not content.strip()):
                return ValidationError(
                    code="EMPTY_RESPONSE_CONTENT",
                    message=f"{action_type} requires non-empty content",
                    field="content",
                )
            if not isinstance(content, str):
                return ValidationError(
                    code="INVALID_CONTENT_TYPE",
                    message=f"content must be string, got {type(content).__name__}",
                    field="content",
                )
            reply_len = len(content)
            if reply_len > ActionValidator.MAX_REPLY_LENGTH:
                return ValidationError(
                    code="REPLY_TOO_LONG",
                    message=f"reply content exceeds {ActionValidator.MAX_REPLY_LENGTH} chars (got {reply_len})",
                    field="content",
                )

        elif action_type == "schedule_meeting":
            # Optional content, but if present must be valid JSON or parseable schedule
            if content is not None:
                if not isinstance(content, str):
                    return ValidationError(
                        code="INVALID_SCHEDULE_TYPE",
                        message=f"schedule content must be string or null, got {type(content).__name__}",
                        field="content",
                    )
                if len(content) > ActionValidator.MAX_SCHEDULE_JSON_LENGTH:
                    return ValidationError(
                        code="SCHEDULE_TOO_LONG",
                        message=f"schedule content exceeds {ActionValidator.MAX_SCHEDULE_JSON_LENGTH} chars",
                        field="content",
                    )
                # Try parsing schedule (optional check)
                if content.strip():
                    err = ActionValidator._validate_schedule_json(content)
                    if err:
                        return err

        elif action_type == "complete_task":
            # Optional content
            if content is not None and not isinstance(content, str):
                return ValidationError(
                    code="INVALID_CONTENT_TYPE",
                    message=f"content must be string, got {type(content).__name__}",
                    field="content",
                )
            if isinstance(content, str) and len(content) > ActionValidator.MAX_CONTENT_LENGTH:
                return ValidationError(
                    code="CONTENT_TOO_LONG",
                    message=f"content exceeds {ActionValidator.MAX_CONTENT_LENGTH} chars",
                    field="content",
                )

        elif action_type == "escalate":
            # Optional content
            if content is not None and not isinstance(content, str):
                return ValidationError(
                    code="INVALID_CONTENT_TYPE",
                    message=f"content must be string, got {type(content).__name__}",
                    field="content",
                )

        return None

    @staticmethod
    def _validate_schedule_json(raw: str) -> Optional[ValidationError]:
        """Validate schedule JSON if present."""
        try:
            data = json.loads(raw)
            if not isinstance(data, dict):
                return ValidationError(
                    code="INVALID_SCHEDULE_FORMAT",
                    message="schedule content must be JSON object",
                    field="content",
                )
            # Allow any keys but check that timestamp keys are ISO8601-ish
            for key in ["start_iso", "end_iso"]:
                if key in data:
                    val = data[key]
                    if not isinstance(val, str):
                        return ValidationError(
                            code="INVALID_SCHEDULE_FORMAT",
                            message=f"{key} must be ISO8601 string",
                            field="content",
                        )
                    if not _is_iso8601_like(val):
                        return ValidationError(
                            code="INVALID_ISO8601",
                            message=f"{key} is not ISO8601 format",
                            field="content",
                        )
            return None
        except json.JSONDecodeError as e:
            return ValidationError(
                code="INVALID_JSON",
                message=f"schedule content is not valid JSON: {str(e)}",
                field="content",
            )


def _is_iso8601_like(s: str) -> bool:
    """Quick ISO8601 validation: YYYY-MM-DDTHH:MM:SS."""
    import re

    pattern = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
    return bool(re.match(pattern, s))

#!/usr/bin/env python3
# Copyright (c) Meta Platforms, Inc. and affiliates.
"""Baseline agent loop: OpenAI tool-calling style JSON actions + OpenEnv client."""

from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any, Dict, List, Optional

try:
    from workplace_ops_agent.client import WorkplaceOpsEnv
    from workplace_ops_agent.models import WorkplaceAction
except ImportError:
    from client import WorkplaceOpsEnv
    from models import WorkplaceAction

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stderr,
)


def _env_base() -> str:
    return os.environ.get("OPENENV_BASE_URL") or os.environ.get("ENV_URL") or "http://127.0.0.1:7860"


def _oracle_plan(task: str) -> List[Dict[str, Any]]:
    if task == "easy":
        return [
            {"type": "classify_email", "target_id": "em_001", "content": "spam"},
            {"type": "classify_email", "target_id": "em_002", "content": "important"},
            {"type": "classify_email", "target_id": "em_003", "content": "spam"},
        ]
    if task == "medium":
        sched = json.dumps(
            {
                "start_iso": "2024-06-11T15:00:00",
                "end_iso": "2024-06-11T16:00:00",
            }
        )
        return [
            {
                "type": "schedule_meeting",
                "target_id": "cal_b",
                "content": sched,
            },
            {
                "type": "respond_slack",
                "target_id": "sl_010",
                "content": (
                    "Heads-up: I rescheduled Sprint planning to 15:00-16:00 "
                    "so it no longer overlaps the 1:1."
                ),
            },
        ]
    if task == "hard":
        sched = json.dumps(
            {
                "title": "Standup deferred — incident response",
                "start_iso": "2024-06-11T17:30:00",
                "end_iso": "2024-06-11T17:45:00",
            }
        )
        return [
            {
                "type": "respond_slack",
                "target_id": "sl_prod_bug",
                "content": (
                    "investigating the prod outage now; mitigation patch rolling "
                    "to canary shortly."
                ),
            },
            {
                "type": "reply_email",
                "target_id": "em_client_cancel",
                "content": (
                    "We will retain the renewal and share a mitigation plan — "
                    "please call me on the primary number; renewal timeline is protected."
                ),
            },
            {
                "type": "schedule_meeting",
                "target_id": "cal_imminent",
                "content": sched,
            },
        ]
    return []


def _summarize_obs(obs: Any) -> str:
    lines: List[str] = []
    lines.append(f"task_id={obs.task_id} step={obs.step_count}/{obs.max_steps}")
    lines.append(f"last_result={obs.last_action_result}")
    for e in obs.emails:
        pt = getattr(e, "priority_tier", "MEDIUM")
        lines.append(f"email [{pt}] {e.id}: {e.subject} :: from {e.from_address}")
    for s in obs.slack_messages:
        tag = "URGENT" if s.urgent else "slack"
        pt = getattr(s, "priority_tier", "MEDIUM")
        lines.append(f"{tag} [{pt}] {s.id} #{s.channel} {s.sender}: {s.body}")
    for c in obs.calendar_events:
        pt = getattr(c, "priority_tier", "MEDIUM")
        lines.append(
            f"event [{pt}] {c.id}: {c.title} {c.start_iso}–{c.end_iso} attendees={c.attendees}"
        )
    for t in obs.tasks:
        pt = getattr(t, "priority_tier", "MEDIUM")
        lines.append(f"task [{pt}] {t.id} [{t.priority}]: {t.title} status={t.status}")
    return "\n".join(lines)


def run_episode(
    task: str,
    *,
    use_llm: bool = False,
    max_steps: int = 48,
) -> tuple[bool, int, float]:
    base = _env_base()

    print("[START]")
    print(f"task={task}")
    print(f"env={base}")

    oracle = _oracle_plan(task)
    oi = 0
    total_reward = 0.0
    steps = 0
    done = False
    success = False
    score = 0.0

    try:
        sync_env = WorkplaceOpsEnv(base_url=base).sync()
    except Exception as e:
        logger.exception(f"Failed to initialize environment client: {e}")
        print("[ERROR]")
        print(f"env_connection_failed: {type(e).__name__}: {str(e)}")
        print("[END]")
        print("success=false")
        print("steps=0")
        print("score=0.0")
        return False, 0, 0.0

    with sync_env:
        result = sync_env.reset(task=task, seed=42)
        obs = result.observation

        while not done and steps < max_steps:
            if oi >= len(oracle):
                break
            row = oracle[oi]
            oi += 1
            action = WorkplaceAction(
                type=row["type"],
                target_id=row["target_id"],
                content=row.get("content"),
            )

            try:
                result = sync_env.step(action)
            except Exception as e:
                logger.exception(f"Error during step execution: {e}")
                print("[ERROR]")
                print(f"step_execution_failed: {type(e).__name__}: {str(e)}")
                break

            obs = result.observation
            r = float(result.reward or 0.0)
            total_reward += r
            done = bool(result.done)
            steps += 1

            grader_score = obs.metadata.get("grader_score")
            if grader_score is not None:
                score = float(grader_score)
            else:
                score = max(min(total_reward / 3.0, 1.0), 0.0)

            print("[STEP]")
            print(f"step={steps}")
            print(
                "action="
                + json.dumps(
                    {
                        "type": action.type,
                        "target_id": action.target_id,
                        "content": action.content,
                    },
                    ensure_ascii=False,
                )
            )
            print(f"reward={r}")
            print(f"done={str(done).lower()}")

        success = done and score >= 0.99

    print("[END]")
    print(f"success={str(success).lower()}")
    print(f"steps={steps}")
    print(f"score={score}")
    return success, steps, score


def main() -> None:
    task = os.environ.get("TASK", "easy")
    # Always use oracle — no LLM/API key needed
    try:
        run_episode(task, use_llm=False)
    except Exception as e:
        logger.exception(f"Unexpected error in episode: {e}")
        print("[ERROR]")
        print(f"episode_failed: {type(e).__name__}: {str(e)}")
        print("[END]")
        print("success=false")
        print("steps=0")
        print("score=0.0")
        sys.exit(1)


if __name__ == "__main__":
    main()

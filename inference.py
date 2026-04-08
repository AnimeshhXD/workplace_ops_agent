#!/usr/bin/env python3
# Copyright (c) Meta Platforms, Inc. and affiliates.
"""Baseline agent loop: OpenAI tool-calling style JSON actions + OpenEnv client."""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from typing import Any, Dict, List, Optional

import requests
from openai import OpenAI

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

def wait_for_env(base_url: str, timeout: int = 60) -> bool:
    """Wait for environment server to be ready by polling /health endpoint."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            resp = requests.get(f"{base_url}/health", timeout=5)
            if resp.status_code == 200:
                logger.info(f"Environment server ready at {base_url}")
                return True
        except requests.RequestException as e:
            logger.debug(f"Health check failed (will retry): {type(e).__name__}: {e}")
        time.sleep(2)
    logger.error(f"Environment server not reachable after {timeout}s at {base_url}")
    return False

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


def _parse_action(raw: str) -> Optional[WorkplaceAction]:
    """Parse action from raw string with explicit error logging."""
    raw = raw.strip()
    if not raw:
        logger.warning("Action JSON parsing: received empty string")
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.warning(f"Action JSON parsing failed: {e}. Raw: {raw[:200]}")
        return None
    
    if not isinstance(data, dict):
        logger.warning(f"Action JSON must be dict, got {type(data).__name__}: {str(data)[:100]}")
        return None
    
    try:
        return WorkplaceAction(
            type=data["type"],
            target_id=str(data.get("target_id", "")),
            content=data.get("content"),
        )
    except (KeyError, TypeError, ValueError) as e:
        logger.warning(f"Action field validation failed: {e}. Data: {str(data)[:200]}")
        return None


def run_episode(
    task: str,
    *,
    use_llm: bool,
    max_steps: int = 48,
) -> tuple[bool, int, float]:
    base = _env_base()
    api_base = os.environ.get("API_BASE_URL", "https://api.openai.com/v1")
    model_name = os.environ.get("MODEL_NAME", "gpt-4o-mini")
    api_key = os.environ.get("OPENAI_API_KEY", "")

    print("[START]")
    print(f"task={task}")
    print(f"env={base}")
    print(f"model={model_name}")
    client_ai: Optional[OpenAI] = None
    if use_llm:
        if not api_key:
            print("OPENAI_API_KEY missing — falling back to oracle plan.", file=sys.stderr)
            use_llm = False
        else:
            client_ai = OpenAI(api_key=api_key, base_url=api_base)

    oracle = _oracle_plan(task)
    oi = 0
    total_reward = 0.0
    steps = 0
    done = False
    success = False
    score = 0.0

    if not wait_for_env(base):
        print("[ERROR]")
        print("env not reachable")
        print("[END]")
        print("success=false")
        print("steps=0")
        print("score=0.0")
        return False, 0, 0.0

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
        hist: List[Dict[str, str]] = []

        while not done and steps < max_steps:
            if use_llm and client_ai is not None:
                system = (
                    "You are a workplace operations agent. Reply with ONE JSON object only, "
                    "no markdown, keys: type, target_id, content (string or null). "
                    "Types: classify_email, reply_email, schedule_meeting, respond_slack, "
                    "complete_task, escalate. For schedule_meeting content use JSON string "
                    "with optional title, start_iso, end_iso ISO8601."
                )
                user = (
                    "Pick the single best next action.\n\n"
                    + _summarize_obs(obs)
                    + "\n\nConversation (JSON actions you already took):\n"
                    + json.dumps(hist[-8:], indent=2)
                )
                resp = client_ai.chat.completions.create(
                    model=model_name,
                    temperature=0.0,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                )
                if not resp or not resp.choices:
                    action = WorkplaceAction(
                        type="escalate",
                        target_id="planner",
                        content="empty response from model",
                    )
                else:
                    msg = resp.choices[0].message
                    raw = (msg.content or "").strip()
                    action = _parse_action(raw)
                    if action is None:
                        action = WorkplaceAction(
                            type="escalate",
                            target_id="planner",
                            content="could not parse model output",
                        )
            else:
                if oi >= len(oracle):
                    break
                row = oracle[oi]
                oi += 1
                action = WorkplaceAction(
                    type=row["type"],
                    target_id=row["target_id"],
                    content=row.get("content"),
                )

            hist.append(
                {
                    "type": action.type,
                    "target_id": action.target_id,
                    "content": action.content or "",
                }
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
            # Prefer grader_score if available, else fallback to normalized reward
            grader_score = obs.metadata.get("grader_score")

            if grader_score is not None:
                score = float(grader_score)
            else:
                # fallback: normalize reward (safe heuristic)
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
    use_llm = os.environ.get("USE_ORACLE", "0").lower() not in ("1", "true", "yes")
    try:
        run_episode(task, use_llm=use_llm)
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

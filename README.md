Here’s your **clean, accurate, no-BS README** — fully aligned with your actual implementation and fixes 👇

---


# Workplace Ops Agent — OpenEnv Hackathon Submission

An OpenEnv-compatible environment that simulates real workplace operations.  
An agent manages emails, Slack messages, and calendar events under priority constraints, evaluated using deterministic graders.

---

## Motivation

Workplace operations require handling multiple responsibilities at once:

- Responding to urgent incidents
- Communicating with clients
- Managing schedules

These tasks are interdependent and time-sensitive. This environment evaluates whether an agent can:

- Prioritize correctly
- Take the right action at the right time
- Produce context-appropriate responses

---

## Environment Overview

| Property | Value |
|---|---|
| Environment ID | `workplace-ops-agent` |
| Interface | OpenEnv (`reset`, `step`, `state`) |
| Max Steps | Task-dependent |
| Score Range | `0.0` – `1.0` |
| Scoring Type | Deterministic |
| Reproducible | Yes (`seed=42`, oracle available) |

---

## Action Space

Each action is a JSON object:

```json
{
  "type": "string",
  "target_id": "string",
  "content": "string or JSON"
}
```

### Supported actions

* `classify_email` — classify email (`spam` or `important`)
* `reply_email` — respond to email
* `respond_slack` — reply to Slack message
* `schedule_meeting` — update calendar event
* `escalate` — escalate issue
* `complete_task` — mark task done

### Notes

* `schedule_meeting` content must be a JSON string:

  ```json
  {
    "title": "...",          // required in hard task
    "start_iso": "...",
    "end_iso": "..."
  }
  ```

---

## Observation Space

Returned by `state()`:

```json
{
  "emails": [
    { "id": "...", "subject": "...", "from_address": "...", "priority_tier": "HIGH" }
  ],
  "slack_messages": [
    { "id": "...", "body": "...", "urgent": true, "priority_tier": "HIGH" }
  ],
  "calendar_events": [
    { "id": "...", "title": "...", "start_iso": "...", "end_iso": "..." }
  ],
  "tasks": [],
  "metadata": {
    "grader_score": 0.0
  },
  "step_count": 0,
  "max_steps": 10
}
```

### Fields

* `priority_tier`: `"LOW" | "MEDIUM" | "HIGH"`
* `urgent`: indicates incident-level Slack messages
* `grader_score`: updated after every step
* `tasks`: may be empty depending on scenario

---

## Task Definitions

### Easy

* Classify 3 emails
* No ordering constraints
* Graded on correctness

---

### Medium

* Resolve calendar conflict
* Reschedule meeting
* Notify via Slack

---

### Hard

Multi-step operations scenario:

1. Respond to urgent Slack incident
2. Reply to high-risk client email
3. Update calendar

### Constraints

* Strict ordering enforced:

  ```
  incident → client → calendar
  ```
* Acting out of order incurs penalties
* All actions must meet quality requirements

---

## Reward Design

* Dense reward shaping
* Positive reward for correct actions
* Penalties for:

  * Incorrect ordering
  * Low-quality responses
* Final score aligns with grader output
* Fully deterministic (no randomness)

---

## Grading Logic

All graders are deterministic — no LLM evaluation.

### Easy

* Score = correct classifications / total

---

### Medium

* Validates:

  * Calendar conflict resolved
  * Slack notification sent

---

### Hard

Checks:

* Correct action ordering
* Slack incident reply quality (keyword-based, minimum threshold)
* Client email quality (required phrases)
* Exact calendar update (title + time)

Score normalized to `[0, 1]`.

---

## Key Features

* **Strict priority enforcement**
  Acting before resolving critical incidents results in penalties

* **Action trace tracking**
  Ordering is verified using recorded action history

* **Deterministic evaluation**
  Same actions always produce same score

* **Multi-domain reasoning**
  Combines email, Slack, and calendar tasks

* **Oracle baseline**
  Deterministic solution achieving score = 1.0

---

## Setup & Run

### 1. Install dependencies

```bash
uv sync
```

---

### 2. Start the server

```bash
python -m uvicorn server.app:app --host 0.0.0.0 --port 8000
```

---

### 3. Validate environment

```bash
openenv validate
```

---

## Running Inference

### Oracle (deterministic baseline)

#### Windows (PowerShell)

```bash
$env:USE_ORACLE="1"
$env:TASK="hard"
python inference.py
```

#### Linux / Mac

```bash
USE_ORACLE=1 TASK=hard python inference.py
```

---

### With OpenAI model

```bash
export OPENAI_API_KEY=your_key
python inference.py
```

---

## Output Format

Example run:

```
[START]
task=hard
env=http://127.0.0.1:8000
model=gpt-4o-mini
[STEP]
step=1
action={"type":"respond_slack",...}
reward=0.4
done=false
[STEP]
step=2
...
[END]
success=true
steps=3
score=1.0
```

---

## Docker

```bash
docker build -t workplace-ops-agent .
docker run -p 8000:8000 workplace-ops-agent
```

---

## Limitations

* Keyword-based grading (not semantic)
* Fixed scenarios (no procedural generation)
* Calendar validation requires exact match
* No multi-turn conversation within a single action
* No authentication layer
* Oracle is hardcoded (not learned)

---

## Why This Environment Matters

* Tests **priority-based decision making**
* Requires **correct sequencing**, not just correctness
* Provides **dense reward signals** for training
* Fully **reproducible and deterministic**
* Reflects **real-world operational workflows**

```

---


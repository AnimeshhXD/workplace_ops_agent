```markdown
# workplace-ops-agent

An OpenEnv-compatible environment that simulates a simplified workplace operations scenario. An AI agent manages emails, Slack messages, and calendar events across three difficulty levels, evaluated by fully deterministic graders.

---

## Motivation

Workplace operations require handling multiple concurrent task types with different priorities and dependencies. This environment tests whether an agent can correctly sequence actions, produce contextually appropriate responses, and manage scheduling — using structured observations and a deterministic reward signal.

---

## Environment Overview

| Property | Value |
|---|---|
| Environment ID | `workplace-ops-agent` |
| Interface | OpenEnv (`reset`, `step`, `state`) |
| Task Levels | Easy, Medium, Hard |
| Score Range | `0.0` – `1.0` |
| Grading | Deterministic |
| Server | FastAPI + WebSocket |
| Oracle Baseline | Score = `1.0` on all tasks |

---

## Action Space

Each action is a JSON object with the following fields:

| Field | Type | Description |
|---|---|---|
| `type` | string | One of the supported action types (see below) |
| `target_id` | string | ID of the target entity (email, message, event, or task) |
| `content` | string or JSON | Reply text, classification label, or scheduling payload |

**Supported action types:**

| Action | Description |
|---|---|
| `classify_email` | Assign `spam` or `important` to an email |
| `reply_email` | Send a text reply to an email |
| `respond_slack` | Send a text response to a Slack message |
| `schedule_meeting` | Create or update a calendar event |
| `escalate` | Escalate a task or incident |
| `complete_task` | Mark a task as complete |

---

## Observation Space

State returned by `state()` is a structured dictionary:

```json
{
  "emails": [
    {
      "id": "string",
      "subject": "string",
      "body": "string",
      "priority_tier": 1
    }
  ],
  "slack_messages": [
    {
      "id": "string",
      "text": "string",
      "urgent": true,
      "priority_tier": 0
    }
  ],
  "calendar_events": [
    {
      "id": "string",
      "title": "string",
      "start": "ISO 8601 string",
      "end": "ISO 8601 string",
      "attendees": ["string"]
    }
  ],
  "tasks": [],
  "metadata": {
    "grader_score": 0.0
  },
  "step_count": 0,
  "max_steps": 10
}
```

- `priority_tier` — Integer indicating urgency; lower values indicate higher priority
- `urgent` — Boolean flag on Slack messages indicating incident-level severity
- `grader_score` — Cumulative score updated after each step
- `tasks` — Optional list of named tasks the agent is expected to complete

---

## Task Descriptions

### Easy

- Classify 3 emails, each labeled either `spam` or `important`
- No ordering constraint between actions
- Graded purely on label correctness

### Medium

- Resolve a scheduling conflict between two calendar events
- Reschedule one meeting to a non-conflicting time
- Notify the relevant party via Slack
- No strict ordering enforced between these actions

### Hard

- Handle an urgent production incident flagged in Slack
- Reply to a client email in a retention scenario
- Update a calendar event to reflect rescheduled commitments
- **Strict ordering required:**
  1. `respond_slack` — incident response
  2. `reply_email` — client reply
  3. `schedule_meeting` — calendar update

Actions taken out of order are penalized.

---

## Grading Logic

All grading is deterministic. No LLM-based evaluation is used at any point.

**Easy grader:**
- Checks each email's assigned label against expected value
- Score = correct labels / total emails

**Medium grader:**
- Validates rescheduled event does not overlap with the conflicting event
- Checks that a Slack notification was sent to the correct target

**Hard grader (all checks must pass for full score):**

| Check | Description |
|---|---|
| Action ordering | `respond_slack` before `reply_email` before `schedule_meeting` |
| Slack content | Reply must contain a minimum set of required keywords |
| Email content | Reply must contain retention-related keywords |
| Calendar update | Title and ISO start/end times must match expected values exactly |

Partial scores are awarded per completed check. Calendar validation has no fuzzy matching — exact values are required.

---

## Reward Design

The environment uses dense reward shaping:

- Partial rewards are given for correct intermediate actions within an episode
- Penalties are applied for ordering violations on the hard task (e.g., updating the calendar before resolving the incident)
- Reward logic is aligned with grader logic — there is no hidden scoring mismatch between `step()` rewards and final grader score
- No stochastic components — identical action sequences always produce identical rewards

---

## How to Run Locally

**Requirements:** Python 3.10+, `uv`

```bash
# Clone the repository
git clone https://github.com/<your-username>/workplace-ops-agent
cd workplace-ops-agent

# Install dependencies
<<<<<<< HEAD
uv pip install -e .

# Start the environment server
uvicorn server.app:app --host 0.0.0.0 --port 8000
=======
uv pip install -r requirements.txt

# Start the environment server
uvicorn app:app --host 0.0.0.0 --port 8000
>>>>>>> bd3b20d535ba861b5e08abef2c5d1ba545731a17

# Validate the environment (requires openenv CLI)
openenv validate --url http://localhost:8000
```

---

## Running Inference

**Oracle mode (no API key required, always scores 1.0):**

```bash
USE_ORACLE=1 python inference.py --url http://localhost:8000 --task hard
```

**LLM mode (OpenAI-compatible API):**

```bash
export OPENAI_API_KEY=your_key_here
python inference.py --url http://localhost:8000 --task hard
```

**Log format produced by `inference.py`:**

```
[START] task=hard
[STEP 1] action=respond_slack target=msg_001 reward=0.25
[STEP 2] action=reply_email target=email_003 reward=0.40
[STEP 3] action=schedule_meeting target=event_002 reward=0.35
[END] total_score=1.0
```

Score is normalized to `[0.0, 1.0]`.

---

## Docker Usage

```bash
# Build the image
docker build -t workplace-ops-agent .

# Run the container
docker run -p 8000:8000 workplace-ops-agent
```

The Dockerfile uses Python 3.10. The server starts automatically via `uvicorn` on container launch.

If deploying to Hugging Face Spaces, update the port to `7860`:

```bash
docker run -p 7860:7860 workplace-ops-agent
```

---

## Project Structure

```
.
<<<<<<< HEAD
├── client.py        # Client for interacting with the environment
├── inference.py     # Agent loop (oracle + LLM modes)
├── Dockerfile
├── pyproject.toml   # Project configuration and dependencies
├── openenv.yaml     # OpenEnv configuration
└── server/
    ├── __init__.py
    ├── app.py       # FastAPI entrypoint
    ├── env.py       # Core environment logic
    ├── tasks.py     # Task definitions (easy, medium, hard)
    ├── graders.py   # Deterministic graders
    ├── reward.py    # Step-level reward logic
    └── models.py    # Pydantic models for actions and state
=======
├── app.py           # FastAPI entrypoint
├── env.py           # Core environment logic
├── tasks.py         # Task definitions (easy, medium, hard)
├── graders.py       # Deterministic graders
├── reward.py        # Step-level reward logic
├── models.py        # Pydantic models for actions and state
├── inference.py     # Agent loop (oracle + LLM modes)
├── Dockerfile
└── requirements.txt
>>>>>>> bd3b20d535ba861b5e08abef2c5d1ba545731a17
```

---

## Limitations

The following limitations are explicit and intentional:

- **Keyword-based content grading:** Slack and email reply quality is evaluated using keyword matching against a fixed list. Semantically correct responses that use different phrasing may not receive full credit.
- **Fixed task scenarios:** Tasks are not procedurally generated. Each difficulty level has exactly one canonical scenario.
- **Exact calendar validation:** Calendar grading checks for exact title strings and ISO 8601 timestamps. Near-correct values do not receive partial credit on this check.
- **No authentication:** The local server has no API key or access control.
- **No conversational memory:** The agent has no memory beyond what is present in the current state object. There is no multi-turn dialogue support within a single action.
- **Oracle is hardcoded:** `USE_ORACLE=1` executes a predetermined correct action sequence. It is a reproducibility baseline, not a learned policy.

---

## Why This Environment Is Useful

- **Multi-domain task management:** The agent must operate across three distinct task types (email, Slack, calendar) within a single episode, requiring it to interpret heterogeneous state.
- **Explicit ordering constraints:** The hard task requires correct action sequencing. Agents that act greedily or randomly will be penalized, making ordering a measurable skill.
- **Deterministic evaluation:** Results are fully reproducible. There is no variance from LLM-based graders, which makes this suitable for controlled benchmarking.
- **Dense learning signal:** Partial step rewards make the environment viable for reinforcement learning experimentation, not just prompted inference evaluation.
<<<<<<< HEAD
- **Transparent grading:** Every scoring decision is traceable to a specific check in `graders.py`. There are no opaque scoring components.
=======
- **Transparent grading:** Every scoring decision is traceable to a specific check in `graders.py`. There are no opaque scoring components.
```
>>>>>>> bd3b20d535ba861b5e08abef2c5d1ba545731a17

# Comprehensive Code Audit: workplace_ops_agent

**Date:** April 8, 2026  
**Audit Focus:** Code quality, security, performance, best practices, and dependencies  
**Repository:** workplace_ops_agent

---

## Executive Summary

This repository is a **well-structured OpenEnv-compatible workplace operations environment** with deterministic grading and multi-scenario task support. Overall code quality is **good**, with clear separation of concerns and proper use of type hints.

**Critical Issues:** 1  
**High Priority Issues:** 4  
**Medium Priority Issues:** 8  
**Low Priority Issues:** 6  

**Recommendation:** Address critical/high items before production use; medium/low items can be addressed incrementally.

---

## 1. CRITICAL ISSUES (Security/Crash Risk)

### 1.1 **CRITICAL: Hardcoded API Base URL with Fallback to Localhost** 
**File:** [inference.py](inference.py#L24-L30)  
**Severity:** 🔴 CRITICAL  
**Category:** Security > Credential Management  

```python
def _env_base() -> str:
    return os.environ.get("OPENENV_BASE_URL") or os.environ.get("ENV_URL") or "http://127.0.0.1:7860"
```

**Issue:**
- Fallback to `http://127.0.0.1:7860` may cause silent failures in production
- Not explicit enough about expected configuration requirements
- Could lead to connecting to wrong environment in misconfigured deployments

**Recommendation:**
```python
def _env_base() -> str:
    base = os.environ.get("OPENENV_BASE_URL") or os.environ.get("ENV_URL")
    if not base:
        raise ValueError(
            "OPENENV_BASE_URL or ENV_URL environment variable is required. "
            "Set to the OpenEnv server URL (e.g., http://localhost:7860)"
        )
    return base
```

---

## 2. HIGH PRIORITY ISSUES

### 2.1 **Missing Exception Type Specification in Broad Except Clause**
**File:** [inference.py](inference.py#L29-L31)  
**Severity:** 🟠 HIGH  
**Category:** Code Quality > Error Handling  

```python
try:
    resp = requests.get(f"{base_url}/health", timeout=5)
except Exception:  # ← Too broad
    pass
```

**Issue:**
- Silently swallows all exceptions, including `SystemExit`, `KeyboardInterrupt`
- Masks URL/network configuration issues
- Difficult to debug failures

**Recommendation:**
```python
except (requests.ConnectionError, requests.Timeout, requests.RequestException):
    pass
```

---

### 2.2 **Multiple Broad Exception Handlers in Critical Path**
**File:** [inference.py](inference.py#L163-L166), [inference.py](inference.py#L191-L198), [server/app.py](server/app.py#L6-L10)  
**Severity:** 🟠 HIGH  
**Category:** Error Handling  

**Issue:**
- `except Exception` in `run_episode` masks failures (lines 163-166, 191-198)
- Same pattern in [server/app.py](server/app.py#L6-L10) with ImportError fallback
- Makes debugging in production difficult

**Files Affected:**
1. [inference.py](inference.py#L163) - env connection failures
2. [inference.py](inference.py#L191) - step execution failures
3. [server/app.py](server/app.py#L6) - import fallback pattern

**Recommendation:**
- Specific exception types: `requests.exceptions`, `RuntimeError`, `ValidationError`
- Log stack traces for debugging
- Consider structured logging

---

### 2.3 **Unsafe Import Fallback Pattern (Anti-pattern)**
**File:** [client.py](client.py#L10-L21), [models.py](models.py#L8-L19), [server/app.py](server/app.py#L23-L27)  
**Severity:** 🟠 HIGH  
**Category:** Code Quality > Maintainability  

```python
try:
    from workplace_ops_agent.models import (...)
except ImportError:
    from server.models import (...)  # ← Silently falls back
```

**Issue:**
- Hides import path configuration issues
- Different import paths work differently in different contexts
- Makes `PYTHONPATH` dependencies unclear
- Tests may pass but production fails (or vice versa)

**Recommendation:**
- Use consistent import paths (relative imports preferred for packages)
- Remove fallback; fix `PYTHONPATH`/`PYTHONUSERBASE` configuration
- Consider using `__init__.py` to centralize exports

---

### 2.4 **Missing Input Validation in Action Parsing**
**File:** [inference.py](inference.py#L127-L143)  
**Severity:** 🟠 HIGH  
**Category:** Security > Input Validation  

```python
def _parse_action(raw: str) -> Optional[WorkplaceAction]:
    raw = raw.strip()
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    try:
        return WorkplaceAction(
            type=data["type"],
            target_id=str(data.get("target_id", "")),  # ← No validation
            content=data.get("content"),  # ← No length limits
        )
    except Exception:
        return None
```

**Issues:**
- `target_id` cast to string without validation (could be malicious data)
- `content` field unbounded (could cause memory issues)
- Silent suppression of validation errors prevents debugging
- No rate limiting on action processing

**Recommendation:**
```python
def _parse_action(raw: str) -> Optional[WorkplaceAction]:
    raw = raw.strip()
    if not raw or len(raw) > 10000:  # Add length limit
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.warning(f"Invalid JSON action: {e}")
        return None
    if not isinstance(data, dict):
        return None
    try:
        target_id = data.get("target_id", "")
        if not isinstance(target_id, str) or not target_id:
            raise ValueError("target_id must be non-empty string")
        content = data.get("content")
        if content and len(str(content)) > 5000:
            raise ValueError("content exceeds max length")
        return WorkplaceAction(
            type=data["type"],
            target_id=target_id,
            content=content,
        )
    except (KeyError, ValueError) as e:
        logger.warning(f"Invalid action data: {e}")
        return None
```

---

## 3. MEDIUM PRIORITY ISSUES

### 3.1 **Unused Imports (Code Cleanliness)**
**File:** [server/app.py](server/app.py#L1-L18)  
**Severity:** 🟡 MEDIUM  
**Category:** Code Quality  

```python
try:
    from openenv.core.env_server.http_server import create_app
except Exception as e:  # pragma: no cover
    raise ImportError(...) from e  # ← 'e' is caught but already being used
```

**Issue:**
- Not actually unused, but the assignment is unnecessary if immediately reraised

---

### 3.2 **Complex Step Logic with Insufficient Comments**
**File:** [server/env.py](server/env.py#L200-L300)  
**Severity:** 🟡 MEDIUM  
**Category:** Maintainability  

```python
# ...40+ lines of conditional state management without inline comments
urgent_charge = self._urgent_violation(action) and not self._st.urgent_penalty_applied
# What does this compute?

delay_fire = False
if self._st.task_id == "hard":  # Why only for hard tasks?
    deadline = int(exp_hard.get("urgent_handle_deadline_step", 4))
    # ...
```

**Issue:**
- `step()` method is 150+ lines with complex reward logic
- Multiple interdependent state flags without clear documentation
- Hard to understand the reward shaping strategy

**Recommendation:**
- Add docstring explaining reward components
- Break into smaller helper methods
- Document state transition reasoning

**Example:**
```python
def step(self, action: WorkplaceAction, ...) -> WorkplaceObservation:
    """
    Execute action and return observation with reward.
    
    Reward shaping includes:
    - Duplicate action penalty
    - Urgent priority violation penalty
    - Priority order bonus (hard task)
    - Context switch penalty
    - Attention budget penalties
    """
```

---

### 3.3 **Missing Type Hints on Return Dict**
**File:** [server/env.py](server/env.py#L77-L93)  
**Severity:** 🟡 MEDIUM  
**Category:** Type Safety  

```python
def _state_as_dict(self) -> dict[str, Any]:  # ← Return type is too broad
    return {
        "email_classifications": dict(self._st.email_classifications),
        # ...
    }
```

**Issue:**
- `dict[str, Any]` loses type information
- Downstream code can't use type checkers to find errors
- Should be more specific TypedDict

**Recommendation:**
```python
class StateDict(TypedDict):
    email_classifications: dict[str, str]
    email_replies: dict[str, str]
    slack_replies: dict[str, str]
    calendar_events: list[dict[str, Any]]
    # ...

def _state_as_dict(self) -> StateDict:
    return {
        "email_classifications": dict(self._st.email_classifications),
        # ...
    }
```

---

### 3.4 **Unsafe Type Casting Without Validation**
**File:** [server/env.py](server/env.py#L41-L48)  
**Severity:** 🟡 MEDIUM  
**Category:** Type Safety  

```python
def _load_scenario(self, task_id: TaskName, seed: int) -> None:
    spec = TASKS[task_id]  # Could fail if task_id not in TASKS
    self._st.max_steps = int(spec.get("episode_max_steps", 50))  # Could fail if not int-like
```

**Issue:**
- No validation that `task_id` is in `TASKS` dict
- `.get()` default might not match expected type
- `int()` cast could fail on malformed data

**Recommendation:**
```python
def _load_scenario(self, task_id: TaskName, seed: int) -> None:
    if task_id not in TASKS:
        raise ValueError(f"Unknown task_id: {task_id}")
    spec = TASKS[task_id]
    episode_max_steps = spec.get("episode_max_steps", 50)
    if not isinstance(episode_max_steps, int) or episode_max_steps <= 0:
        raise ValueError(f"Invalid episode_max_steps: {episode_max_steps}")
    self._st.max_steps = episode_max_steps
```

---

### 3.5 **Missing Validation in JSON Parsing**
**File:** [server/env.py](server/env.py#L28-L48)  
**Severity:** 🟡 MEDIUM  
**Category:** Security & Correctness  

```python
def _parse_schedule_content(raw: Optional[str]) -> dict[str, str]:
    if not raw:
        return {}
    raw = raw.strip()
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items()}  # ← Could convert wrong things
    except json.JSONDecodeError:
        pass
    # Fallback regex parsing is fragile
    m = re.search(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})", raw)
    # ...
```

**Issues:**
- No validation of parsed ISO8601 strings
- Regex fallback is unreliable and could accept invalid formats
- Silent failure mode makes bugs hard to find

**Example Problem:**
- Input: `{"start_iso": "2024-13-45T99:99:99"}` would pass and cause issues downstream

---

### 3.6 **No Rate Limiting on Episode/Step Execution**
**File:** [server/env.py](server/env.py)  
**Severity:** 🟡 MEDIUM  
**Category:** Performance & Security  

**Issue:**
- No request rate limiting configured
- Could be vulnerable to DoS (rapid episode resets)
- Docker/FastAPI setup doesn't enforce concurrency limits properly

**Recommendation:**
```python
# In server/app.py or middleware
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
limiter.limit("10/minute")(app.post("/reset"))
limiter.limit("100/minute")(app.post("/step"))
```

---

### 3.7 **Hardcoded Port and Host Configuration**
**File:** [server/app.py](server/app.py#L35-L42)  
**Severity:** 🟡 MEDIUM  
**Category:** Configuration  

```python
def main(host: str = "0.0.0.0", port: Optional[int] = None) -> None:
    # ...
    if port is None:
        port = int(os.environ.get("PORT", 7860))  # ← Hardcoded default 7860
```

**Issue:**
- Host `0.0.0.0` exposes service to all interfaces (security risk in some contexts)
- Hardcoded `7860` conflicts with other services
- No validation that port is valid (1-65535)

**Recommendation:**
```python
def main(host: str = "127.0.0.1", port: Optional[int] = None) -> bool:
    """
    Args:
        host: Listening host (default: 127.0.0.1 for security)
        port: Listening port (default: from PORT env var, fallback 7860)
    """
    if port is None:
        port = int(os.environ.get("PORT", 7860))
    if not (1 <= port <= 65535):
        raise ValueError(f"Invalid port: {port}")
    print(f"Starting server on {host}:{port}")
    uvicorn.run(app, host=host, port=port)
```

---

### 3.8 **Custom Health Route Implementation Could Conflict**
**File:** [server/app.py](server/app.py#L28-L32)  
**Severity:** 🟡 MEDIUM  
**Category:** Maintainability  

```python
app = create_app(...)
# Remove existing /health route and add our custom one
app.routes[:] = [route for route in app.routes if not (hasattr(route, 'path') and route.path == '/health')]

@app.get("/health")
def health_check() -> dict:
    """Health check endpoint."""
    return {"status": "healthy"}
```

**Issue:**
- Modifying `app.routes` directly is fragile
- No error handling if expected routes don't exist
- Unclear why custom route is needed vs. using `create_app` parameter

**Recommendation:**
Check `openenv.core.env_server.http_server.create_app` signature to see if `health_check` parameter exists, or use dependency injection.

---

## 4. CODE QUALITY ISSUES (Medium/Low)

### 4.1 **Missing Docstrings**
**Files:**
- [client.py](client.py#L35) - `_parse_result()` - no docstring
- [models.py](models.py) - no file-level docstring
- [server/env.py](server/env.py#L27) - `_parse_schedule_content()` - no docstring
- [server/env.py](server/env.py#L77) - `_state_as_dict()` - no docstring
- [server/reward.py](server/reward.py#L31) - `_calendar_has_overlap()` - no docstring

**Severity:** 🟡 MEDIUM  
**Category:** Documentation  

**Example:**
```python
def _parse_result(self, payload: Dict[str, Any]) -> StepResult[WorkplaceObservation]:
    """
    Parse raw API response into typed StepResult.
    
    Handles missing/optional fields with sensible defaults.
    Converts plain dicts to typed observation objects.
    
    Args:
        payload: Raw response from environment server
        
    Returns:
        Typed StepResult with observation, reward, done flag
        
    Raises:
        KeyError: If required payload fields are missing
    """
```

---

### 4.2 **Inconsistent Error Messages**
**Files:**
- [server/env.py](server/env.py#L189) - `"unknown email id"` (lowercase)
- [server/env.py](server/env.py#L192) - `"label must be spam or important"` (lowercase)
- [server/env.py](server/env.py#L201) - `"unknown calendar id"` (lowercase)

**Severity:** 🟢 LOW  
**Category:** Code Consistency  

**Recommendation:**
Standardize error message format:
```python
"Email ID not found in inbox: {target_id}"
"Label must be 'spam' or 'important', got: {label}"
```

---

### 4.3 **Magic Numbers Without Explanation**
**File:** [server/reward.py](server/reward.py#L34-L45)  
**Severity:** 🟡 MEDIUM  
**Category:** Maintainability  

```python
R_CLASSIFY_OK = 0.2
R_CLASSIFY_BAD = -0.1
R_REPLY_OK = 0.4
R_REPLY_BAD = -0.3
R_SCHEDULE_OK = 0.5
R_TASK_DONE = 1.0
```

**Issue:**
- No explanation why these specific values
- Hard to tune without understanding intent
- No documentation of reward shaping strategy

**Recommendation:**
```python
# Reward shaping constants (empirically tuned for task complexity)
# Email classification is least valuable (task-dependent)
R_CLASSIFY_OK = 0.2      # Correct classification
R_CLASSIFY_BAD = -0.1    # Incorrect classification penalty

# Replies require contextual understanding
R_REPLY_OK = 0.4         # Substantive reply (email/Slack)
R_REPLY_BAD = -0.3       # Failed or empty reply attempt
```

---

### 4.4 **Repeated Logic for Event Overlap Detection**
**Files:**
- [server/env.py](server/env.py#L163-L169) - `_overlap_exists()`
- [server/reward.py](server/reward.py#L31-L40) - `_calendar_has_overlap()`

**Severity:** 🟡 MEDIUM  
**Category:** DRY Principle  

```python
# In env.py - almost identical
def _overlap_exists(self) -> bool:
    ev = self._st.calendar_events
    for i, a in enumerate(ev):
        for b in ev[i + 1 :]:
            if not (a["end_iso"] <= b["start_iso"] or b["end_iso"] <= a["start_iso"]):
                return True
    return False

# In reward.py - almost identical
def _calendar_has_overlap(events: list[dict[str, Any]]) -> bool:
    ev = list(events)
    for i, a in enumerate(ev):
        for b in ev[i + 1 :]:
            if a["id"] == b["id"]:
                continue
            if not (a["end_iso"] <= b["start_iso"] or b["end_iso"] <= a["start_iso"]):
                return True
    return False
```

**Recommendation:**
Extract to shared utility module [server/utils.py](server/utils.py):
```python
def calendar_events_overlap(events: list[dict[str, Any]]) -> bool:
    """Check if any two distinct calendar events overlap in time."""
    ev = list(events)
    for i, a in enumerate(ev):
        for b in ev[i + 1 :]:
            if a["id"] == b["id"]:
                continue
            if not (a["end_iso"] <= b["start_iso"] or b["end_iso"] <= a["start_iso"]):
                return True
    return False
```

---

### 4.5 **No Logging Infrastructure**
**Severity:** 🟡 MEDIUM  
**Category:** Observability  

**Issue:**
- No structured logging in any module
- Difficult to debug in production
- Only has print statements (inference.py)

**Recommendation:**
```python
import logging
logger = logging.getLogger(__name__)

# In inference.py
logger.info(f"Connecting to environment: {base}")
logger.error(f"Failed to connect: {e}", exc_info=True)
```

---

### 4.6 **Long Functions Need Refactoring**
**File:** [inference.py](inference.py#L150-L277)  
**Severity:** 🟡 MEDIUM  
**Category:** Maintainability  

**Issue:**
- `run_episode()` is 127 lines
- Nested conditions make it hard to follow
- Multiple responsibilities (LLM calling, oracle plan, env interaction)

**Recommendation:**
Extract helper functions:
```python
def _get_llm_action(llm_client, obs, hist, model_name, system_prompt):
    """Get action from LLM."""
    # ... 20 lines

def _execute_step(env, action, hist, task):
    """Execute single step and return results."""
    # ... 10 lines

def run_episode(...):
    """Main episode loop."""
    # Calls helpers above
```

---

### 4.7 **Incomplete Type Hints in Complex Functions**
**File:** [client.py](client.py#L35-L100)  
**Severity:** 🟡 MEDIUM  
**Category:** Type Safety  

```python
def _parse_result(self, payload: Dict[str, Any]) -> StepResult[WorkplaceObservation]:
    obs_data = payload.get("observation", {})
    
    emails = [
        EmailItem(
            id=e["id"],  # ← Assumes 'id' exists, no validation
            subject=e["subject"],
            # ...
        )
        for e in obs_data.get("emails") or []
    ]
```

**Issue:**
- Assumes dict keys exist without checking
- Could raise KeyError at runtime
- No error handling for malformed responses

**Recommendation:**
```python
def _parse_result(self, payload: Dict[str, Any]) -> StepResult[WorkplaceObservation]:
    obs_data = payload.get("observation", {})
    
    emails = []
    for e in obs_data.get("emails") or []:
        try:
            emails.append(EmailItem(
                id=e["id"],
                subject=e["subject"],
                from_address=e["from_address"],
                body_preview=e["body_preview"],
                priority_tier=e.get("priority_tier", "MEDIUM"),
            ))
        except (KeyError, ValueError) as ex:
            logger.warning(f"Malformed email item {e}: {ex}")
            continue
```

---

## 5. PERFORMANCE ISSUES

### 5.1 **N+1 Query-like Pattern in Step Execution**
**File:** [server/env.py](server/env.py#L204-L246)  
**Severity:** 🟡 MEDIUM  
**Category:** Performance  

```python
def _execute(self, action: WorkplaceAction) -> tuple[bool, str]:
    success = True
    detail = ""
    if action.type == "classify_email":
        ids = {e["id"] for e in self._st.emails}  # ← Linear scan
        if action.target_id not in ids:
            success = False
    # ... 40+ more lines with similar patterns
```

**Issue:**
- Building ID sets from lists on every execute call
- Should be cached/indexed

**Recommendation:**
```python
def _load_scenario(self, ...):
    # ... existing code ...
    self._email_ids = {e["id"] for e in self._st.emails}
    self._slack_ids = {s["id"] for s in self._st.slack_messages}
    self._calendar_ids = {c["id"] for c in self._st.calendar_events}
    self._task_ids = {t["id"] for t in self._st.tasks}

def _execute(self, action: WorkplaceAction) -> tuple[bool, str]:
    if action.type == "classify_email":
        if action.target_id not in self._email_ids:  # O(1) lookup
            return False, "unknown email id"
```

---

### 5.2 **Regular Expression Compilation at Runtime**
**File:** [server/env.py](server/env.py#L41-L48)  
**Severity:** 🟢 LOW  
**Category:** Performance  

```python
def _parse_schedule_content(raw: Optional[str]) -> dict[str, str]:
    # ...
    m = re.search(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})", raw)  # ← Compiled every call
    times = re.findall(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})", raw)  # ← Again
```

**Recommendation:**
```python
import re

_ISO8601_PATTERN = re.compile(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})")

def _parse_schedule_content(raw: Optional[str]) -> dict[str, str]:
    m = _ISO8601_PATTERN.search(raw)
    times = _ISO8601_PATTERN.findall(raw)
```

---

## 6. DEPENDENCIES & CONFIGURATION

### 6.1 **Missing `requests` Package in pyproject.toml**
**File:** [pyproject.toml](pyproject.toml#L11-L14)  
**Severity:** 🟠 HIGH  
**Category:** Dependencies  

**Issue:**
- [inference.py](inference.py#L10) imports `requests` but it's not listed in `dependencies`
- Only appears as transitive dependency of `openai`
- Could break if OpenAI changes dependencies

**Recommendation:**
```toml
[project]
dependencies = [
    "openenv-core[core]>=0.2.2",
    "openai>=1.40.0",
    "pydantic>=2.0",
    "requests>=2.31.0",  # ← Add explicit dependency
]
```

---

### 6.2 **Missing Development Dependencies**
**File:** [pyproject.toml](pyproject.toml#L17-L19)  
**Severity:** 🟡 MEDIUM  
**Category:** Development  

```toml
[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
]
```

**Missing:**
- `pytest-cov` - coverage reporting
- `mypy` - static type checking
- `black` / `ruff` - formatting and linting
- `types-requests` - type stubs

**Recommendation:**
```toml
[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-cov>=4.0.0",
    "mypy>=1.5.0",
    "types-requests>=2.31.0",
    "ruff>=0.1.0",
    "black>=23.0.0",
]
lint = [
    "ruff>=0.1.0",
    "mypy>=1.5.0",
    "black>=23.0.0",
]
test = [
    "pytest>=8.0.0",
    "pytest-cov>=4.0.0",
]
```

---

### 6.3 **Python Version Too Restrictive**
**File:** [pyproject.toml](pyproject.toml#L7)  
**Severity:** 🟢 LOW  
**Category:** Compatibility  

```toml
requires-python = ">=3.10"
```

**Issue:**
- Requirement for 3.10+ is not justified in code
- Most code is compatible with 3.9+
- Limits deployment options

**Recommendation:**
Check if any 3.10+ specific features are used. If not:
```toml
requires-python = ">=3.9"  # dict[str, Any] syntax available in 3.9+
```

---

### 6.4 **Dockerfile Uses Same Port as App Config**
**File:** [Dockerfile](Dockerfile#L19), [openenv.yaml](openenv.yaml#L10)  
**Severity:** 🟢 LOW  
**Category:** Configuration  

```dockerfile
EXPOSE 7860
```

```yaml
port: 8000
```

**Issue:**
- Conflict: Dockerfile exposes 7860, config says 8000
- Causes confusion during deployment

**Recommendation:**
```dockerfile
ARG PORT=7860
EXPOSE ${PORT}
```

And update `openenv.yaml` to match:
```yaml
port: 7860  # Must match Dockerfile EXPOSE
```

---

## 7. SECURITY ANALYSIS

### 7.1 **No Input Sanitization for Content Fields**
**Severity:** 🟠 HIGH  
**Files:** [inference.py](inference.py#L127-L143), [server/env.py](server/env.py#L231-L242)

**Issue:**
- User-supplied `content` field not validated
- Could contain malicious payloads (SQL, code, etc.)
- No length limits (memory exhaustion risk)

**Recommendation:**
```python
MAX_CONTENT_LENGTH = 5000

def _parse_action(raw: str) -> Optional[WorkplaceAction]:
    # ...
    content = data.get("content")
    if content and len(str(content)) > MAX_CONTENT_LENGTH:
        logger.warning(f"Content exceeds max length: {len(str(content))}")
        return None
```

---

### 7.2 **Server Exposes Sensitive State Information**
**File:** [server/env.py](server/env.py#L158-L161)  
**Severity:** 🟡 MEDIUM  
**Category:** Information Disclosure  

```python
metadata={
    "grader_score": grade(self._st.task_id, self._state_as_dict()),
    "episode_id": self._st.episode_id,
    "reward_breakdown": dict(self._st.last_reward_breakdown),  # ← Exposes algorithm details
}
```

**Issue:**
- `reward_breakdown` reveals reward shaping strategy
- Could be exploited to game the environment
- Consider removing or restricting access

**Recommendation:**
```python
# Option 1: Remove in production
if os.environ.get("EXPOSE_REWARD_BREAKDOWN") == "true":
    metadata["reward_breakdown"] = dict(self._st.last_reward_breakdown)

# Option 2: Only expose to authorized clients
# Implement API key authentication
```

---

### 7.3 **No HTTPS Configuration**
**File:** [server/app.py](server/app.py), [Dockerfile](Dockerfile)  
**Severity:** 🟡 MEDIUM  
**Category:** Transport Security  

**Issue:**
- No TLS/HTTPS support configured
- Communications vulnerable to MITM attacks
- WebSocket traffic unencrypted

**Recommendation:**
```python
# Use reverse proxy (nginx) with TLS
# Or configure Uvicorn with SSL:
uvicorn.run(
    app,
    host="0.0.0.0",
    port=8443,
    ssl_keyfile="/path/to/key.pem",
    ssl_certfile="/path/to/cert.pem",
)
```

---

## 8. TESTING & QUALITY METRICS

### 8.1 **No Unit Tests Found**
**Severity:** 🟠 HIGH  
**Category:** Testing  

**Issue:**
- `tests/` directory not in provided structure
- Critical logic (graders, reward, state transitions) untested
- Makes refactoring dangerous

**Recommendation:**
Create [tests/test_graders.py](tests/test_graders.py):
```python
import pytest
from server.graders import grade_easy, grade_medium, grade_hard

def test_grade_easy_full_match():
    state = {
        "email_classifications": {
            "em_001": "spam",
            "em_002": "important",
            "em_003": "spam",
        }
    }
    assert grade_easy(state) == 1.0

def test_grade_easy_partial():
    state = {"email_classifications": {"em_001": "spam"}}
    assert grade_easy(state) == pytest.approx(1/3)
```

---

### 8.2 **No Integration Tests**
**Severity:** 🟡 MEDIUM  
**Category:** Testing  

**Issue:**
- No end-to-end episode tests
- Reward computation not verified across boundary conditions
- State mutations not tested

---

## 9. BEST PRACTICES GAPS

### 9.1 **No Configuration Management**
**Severity:** 🟡 MEDIUM  

**Issue:**
- Magic numbers scattered throughout
- No centralized config file
- Environment variables inconsistently named

**Recommendation:**
Create [server/config.py](server/config.py):
```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    openenv_base_url: str = "http://127.0.0.1:7860"
    port: int = 7860
    host: str = "127.0.0.1"
    expose_reward_breakdown: bool = False
    max_content_length: int = 5000
    max_steps_default: int = 50
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

settings = Settings()
```

---

### 9.2 **No .gitignore**
**Severity:** 🟢 LOW  

**Issue:**
- No `.gitignore` file in repo structure
- Could accidentally commit `.venv`, `__pycache__`, `.env`

**Recommendation:**
Create [.gitignore](.gitignore):
```
__pycache__/
*.py[cod]
*$py.class
.venv/
venv/
.env
.env.local
*.egg-info/
dist/
build/
.pytest_cache/
.mypy_cache/
.coverage
htmlcov/
```

---

### 9.3 **Missing CHANGELOG/Version Management**
**Severity:** 🟢 LOW  

**Issue:**
- No CHANGELOG tracking changes
- Version hardcoded in [__init__.py](__init__.py#L4) and pyproject.toml

**Recommendation:**
Use `semantic-versioning` package or tool:
```toml
[tool.poetry]
version = "0.1.0"  # Source of truth

[build-system]
# Version read from pyproject.toml
```

---

## 10. SUMMARY TABLE

| Category | Critical | High | Medium | Low | Total |
|----------|----------|------|--------|-----|-------|
| Security | 1 | 3 | 2 | 1 | **7** |
| Code Quality | — | 1 | 5 | 3 | **9** |
| Performance | — | — | 2 | 1 | **3** |
| Dependencies | — | 1 | 1 | — | **2** |
| Testing | — | 1 | 1 | — | **2** |
| **TOTAL** | **1** | **6** | **11** | **5** | **23** |

---

## 11. RECOMMENDATIONS BY PRIORITY

### 🔴 CRITICAL (Fix Immediately)
1. ✅ [1.1] Make environment URL mandatory (don't fallback to localhost)
2. ✅ [2.1] Replace broad `except Exception` with specific types
3. ✅ [2.3] Fix import fallback anti-pattern
4. ✅ [2.4] Add input validation to action parsing
5. ✅ [6.1] Add `requests` to `pyproject.toml` dependencies

### 🟠 HIGH (Address Before Production)
1. [3.1-3.8] See "High Priority Issues" section
2. [6.3] Configure rate limiting
3. [7.1] Input sanitization and length limits
4. [8.1] Add unit tests for graders, rewards, state

### 🟡 MEDIUM (Address in Next Sprint)
1. Refactor long functions (`run_episode`, `step`)
2. Extract duplicate code (overlap detection)
3. Add comprehensive logging
4. Create centralized configuration
5. Add docstrings and type hints

### 🟢 LOW (Address as Opportunity)
1. Enhance error messages consistency
2. Fix Python version requirement (3.9 vs 3.10)
3. Add proper `.gitignore`
4. Add CHANGELOG

---

## 12. QUICK FIXES (Can be Done Immediately)

### Fix 12.1: Add Missing Requirements
```python
# pyproject.toml - add 'requests' to dependencies
dependencies = [
    "openenv-core[core]>=0.2.2",
    "openai>=1.40.0",
    "pydantic>=2.0",
    "requests>=2.31.0",  # ← ADD THIS
]
```

### Fix 12.2: Improve Exception Handling
```python
# inference.py - be specific about exceptions
except (requests.ConnectionError, requests.Timeout) as e:
    print(f"Failed to reach environment at {base_url}: {e}")
```

### Fix 12.3: Validate Environment URL
```python
# inference.py
def _env_base() -> str:
    base = os.environ.get("OPENENV_BASE_URL") or os.environ.get("ENV_URL")
    if not base:
        raise ValueError("Set OPENENV_BASE_URL or ENV_URL environment variable")
    return base
```

---

## 13. STATIC ANALYSIS RECOMMENDATIONS

Run these tools for automated checks:

```bash
# Type checking
mypy server/ --strict

# Code formatting
black server/

# Linting
ruff check server/

# Security scanning
bandit server/ -r

# Test coverage
pytest --cov=server/ tests/
```

---

## 14. CONCLUSION

The **workplace_ops_agent** repository demonstrates solid foundational design with:
- ✅ Clear type hints (mostly)
- ✅ Good separation of concerns (models, env, graders, rewards)
- ✅ Deterministic behavior (good for reproducibility)
- ✅ Well-documented task scenarios

**Key Improvements Needed:**
- Eliminate broad exception handlers and fallback imports
- Add input validation and length limits
- Implement comprehensive unit tests
- Add structured logging
- Refactor long functions
- Fix missing dependencies

**Estimated Effort:**
- Critical fixes: 2-4 hours
- High priority fixes: 1-2 days
- Medium priority refactoring: 3-5 days
- Full test suite: 5-7 days

**Not Recommended for Production Until:** Critical and High priority items are addressed.

---

**Report Generated:** April 8, 2026  
**Next Audit Recommended:** After critical fixes applied (1-2 weeks)

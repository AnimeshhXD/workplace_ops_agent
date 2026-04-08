# Action Plan: Quick Fixes & Priority Items

## Quick Wins (30 minutes)

### 1. Add Missing `requests` Dependency
**File:** [pyproject.toml](pyproject.toml)
```diff
dependencies = [
    "openenv-core[core]>=0.2.2",
    "openai>=1.40.0",
    "pydantic>=2.0",
+   "requests>=2.31.0",
]
```

### 2. Create .gitignore
**File:** `.gitignore` (new)
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
.DS_Store
```

---

## Critical Fixes (2-4 hours)

### 3. Fix Environment URL Configuration (inference.py)
```python
# BEFORE:
def _env_base() -> str:
    return os.environ.get("OPENENV_BASE_URL") or os.environ.get("ENV_URL") or "http://127.0.0.1:7860"

# AFTER:
def _env_base() -> str:
    """Get OpenEnv server base URL from environment.
    
    Raises:
        ValueError: If neither OPENENV_BASE_URL nor ENV_URL is set
    """
    base = os.environ.get("OPENENV_BASE_URL") or os.environ.get("ENV_URL")
    if not base:
        raise ValueError(
            "Environment variable not set: OPENENV_BASE_URL or ENV_URL required. "
            "Example: OPENENV_BASE_URL=http://localhost:7860"
        )
    return base
```

### 4. Specific Exception Handling (inference.py)
Replace all `except Exception:` blocks with specific types:
```python
# BEFORE:
except Exception:
    pass

# AFTER:
except (requests.ConnectionError, requests.Timeout, requests.RequestException) as e:
    logger.warning(f"Connection error: {e}")
```

### 5. Input Validation in Action Parsing (inference.py)
```python
def _parse_action(raw: str) -> Optional[WorkplaceAction]:
    """Parse JSON action from LLM output.
    
    Args:
        raw: JSON string with action definition
        
    Returns:
        Parsed WorkplaceAction or None if invalid
        
    Raises:
        No exceptions; returns None for invalid input
    """
    MAX_ACTION_SIZE = 10000
    
    raw = raw.strip()
    if not raw or len(raw) > MAX_ACTION_SIZE:
        return None
    
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    
    if not isinstance(data, dict):
        return None
    
    try:
        target_id = data.get("target_id", "")
        if not isinstance(target_id, str):
            target_id = str(target_id)
        if not target_id:
            return None
        
        content = data.get("content")
        if content and len(str(content)) > 5000:
            return None
        
        return WorkplaceAction(
            type=data["type"],
            target_id=target_id,
            content=content,
        )
    except (KeyError, ValueError, TypeError):
        return None
```

---

## High Priority (1-2 days)

### 6. Remove Unsafe Import Fallbacks
**Files:** client.py, models.py, server/app.py

Use consistent import paths instead:
```python
# BEFORE:
try:
    from workplace_ops_agent.models import WorkplaceAction
except ImportError:
    from server.models import WorkplaceAction

# AFTER:
# Set PYTHONPATH to repo root, then always use:
from server.models import WorkplaceAction
```

### 7. Add Rate Limiting (server/app.py)
```bash
pip install slowapi
```

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

app = create_app(...)

@app.post("/reset")
@limiter.limit("10/minute")
async def reset(...):
    ...
```

### 8. Port Configuration Fix (Dockerfile & openenv.yaml)
**Dockerfile:**
```dockerfile
EXPOSE 7860
```

**openenv.yaml:**
```yaml
port: 7860
```

### 9. Add Basic Logging
```bash
pip install python-json-logger
```

Create [server/logging.py](server/logging.py):
```python
import logging
import json
from pythonjsonlogger import jsonlogger

def setup_logging():
    logHandler = logging.StreamHandler()
    formatter = jsonlogger.JsonFormatter()
    logHandler.setFormatter(formatter)
    root_logger = logging.getLogger()
    root_logger.addHandler(logHandler)
    root_logger.setLevel(logging.INFO)

setup_logging()
```

---

## Test Coverage (3-5 days)

### 10. Create Basic Test Suite

**tests/test_graders.py:**
```python
import pytest
from server.graders import grade_easy, grade_medium, grade_hard, grade

def test_grade_easy_perfect():
    state = {
        "email_classifications": {
            "em_001": "spam",
            "em_002": "important",
            "em_003": "spam",
        }
    }
    assert grade("easy", state) == 1.0

def test_grade_easy_empty():
    state = {"email_classifications": {}}
    assert grade("easy", state) == 0.0

def test_grade_easy_partial():
    state = {
        "email_classifications": {
            "em_001": "spam",
            "em_002": "spam",  # Wrong, should be "important"
            "em_003": "spam",
        }
    }
    assert grade("easy", state) == pytest.approx(2/3)
```

**tests/test_models.py:**
```python
import pytest
from server.models import WorkplaceAction, EmailItem

def test_workplace_action_valid():
    action = WorkplaceAction(
        type="classify_email",
        target_id="em_001",
        content="spam"
    )
    assert action.type == "classify_email"

def test_workplace_action_invalid_type():
    with pytest.raises(ValueError):
        WorkplaceAction(
            type="invalid_type",
            target_id="em_001"
        )
```

### 11. Add Pre-commit Hooks
**Setup:**
```bash
pip install pre-commit
```

Create [.pre-commit-config.yaml](.pre-commit-config.yaml):
```yaml
repos:
  - repo: https://github.com/psf/black
    rev: 23.1.0
    hooks:
      - id: black

  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.1.0
    hooks:
      - id: ruff
        args: [--fix]

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.5.0
    hooks:
      - id: mypy
        args: [--strict]
        additional_dependencies: [types-requests]
```

---

## Refactoring (Next Sprint)

### 12. Extract Shared Utility Functions
Create [server/utils.py](server/utils.py):
```python
"""Shared utility functions."""
import re
from typing import Any

ISO8601_PATTERN = re.compile(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})")

def calendar_events_overlap(events: list[dict[str, Any]]) -> bool:
    """Check if any two calendar events overlap in time.
    
    Args:
        events: List of calendar event dicts with start_iso/end_iso
        
    Returns:
        True if any two distinct events overlap
    """
    for i, a in enumerate(events):
        for b in events[i + 1:]:
            if a["id"] == b["id"]:
                continue
            if not (a["end_iso"] <= b["start_iso"] or b["end_iso"] <= a["start_iso"]):
                return True
    return False

def parse_iso8601_timestamp(text: str) -> list[str]:
    """Extract ISO8601 timestamps from text."""
    return ISO8601_PATTERN.findall(text)
```

### 13. Refactor Long Functions
Split `run_episode()` in inference.py into:
- `_setup_environment()` - environment initialization
- `_get_next_action()` - decide action (LLM or oracle)
- `_execute_step()` - execute and update state
- `_format_output()` - print results

### 14. Add Docstrings to All Public Methods
Follow Google-style docstrings:
```python
def step(self, action: WorkplaceAction, ...) -> WorkplaceObservation:
    """Execute a single action in the environment.
    
    Applies reward shaping based on task difficulty and action type.
    Updates internal state and returns observation with reward signal.
    
    Args:
        action: The action to execute
        timeout_s: Optional timeout for the step
        **kwargs: Additional arguments (unused)
        
    Returns:
        WorkplaceObservation with updated state and reward
        
    Raises:
        ValueError: If action type is invalid
    """
```

---

## Deployment Checklist

- [ ] Add all missing dependencies
- [ ] Fix environment URL requirement  
- [ ] Add specific exception handling
- [ ] Input validation complete
- [ ] Rate limiting configured
- [ ] Logging implemented
- [ ] Unit tests added (>80% coverage)
- [ ] Security review completed
- [ ] Performance baseline established
- [ ] Documentation updated

---

## Verification Commands

```bash
# Type checking
mypy server/ --strict

# Linting
ruff check server/

# Code formatting check
black --check server/

# Security scan
bandit server/ -r

# Test execution
pytest tests/ -v --cov=server

# Coverage report
pytest tests/ --cov=server --cov-report=html
```

---

## Timeline Estimate

| Phase | Items | Effort | Timeline |
|-------|-------|--------|----------|
| Quick Wins | 1-2 | 30 min | Day 1 |
| Critical | 3-5 | 2-4 hrs | Day 1 |
| High Priority | 6-9 | 1-2 days | Days 2-3 |
| Testing | 10-11 | 3-5 days | Days 4-7 |
| Refactoring | 12-14 | 2-3 days | Days 5-7 |
| **Total** | — | **8-16 days** | **2 weeks** |

---

## Notes

- Start with **Quick Wins** + **Critical** to unblock deployment concerns
- Implement fixes in order of risk (security → crashes → quality)
- Add monitoring/logging early (helps catch new issues)
- Run pre-commit hooks on all commits post-fixes

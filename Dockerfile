# Copyright (c) Meta Platforms, Inc. and affiliates.
# Workplace-ops-agent — Hugging Face Spaces / local Docker (Python 3.10)
FROM python:3.10-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

WORKDIR /app/env

COPY pyproject.toml uv.lock README.md openenv.yaml inference.py ./
COPY models.py client.py __init__.py ./
COPY server ./server

RUN uv sync --frozen --no-editable

ENV PYTHONPATH="/app/env:${PYTHONPATH}"
ENV PATH="/app/env/.venv/bin:${PATH}"

EXPOSE 7860
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD sh -c 'curl -fsS "http://127.0.0.1:$${PORT:-8000}/health" || exit 1'

CMD ["sh", "-c", "cd /app/env && exec uv run uvicorn server.app:app --host 0.0.0.0 --port ${PORT:-8000}"]

# Copyright (c) Meta Platforms, Inc. and affiliates.
"""FastAPI / WebSocket server for workplace-ops-agent.

Local dev: ``uvicorn server.app:app --reload`` or call ``main()`` after ``python -m workplace_ops_agent.server.app``.
"""

try:
    from openenv.core.env_server.http_server import create_app
except Exception as e:  # pragma: no cover
    raise ImportError(
        "openenv-core is required. Install dependencies with: uv sync"
    ) from e

try:
    from workplace_ops_agent.models import WorkplaceAction, WorkplaceObservation
    from workplace_ops_agent.server.env import WorkplaceOpsEnvironment
except ImportError:
    from models import WorkplaceAction, WorkplaceObservation
    from server.env import WorkplaceOpsEnvironment

app = create_app(
    WorkplaceOpsEnvironment,
    WorkplaceAction,
    WorkplaceObservation,
    env_name="workplace_ops_agent",
    max_concurrent_envs=4,
)

# Remove existing /health route and add our custom one
app.routes[:] = [route for route in app.routes if not (hasattr(route, 'path') and route.path == '/health')]


@app.get("/health")
def health_check() -> dict:
    """Health check endpoint."""
    return {"status": "ok"}


def main(host: str = "0.0.0.0", port: int = 8000) -> None:
    import uvicorn

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    main(port=args.port)

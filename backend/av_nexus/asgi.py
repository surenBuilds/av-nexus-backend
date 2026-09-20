"""ASGI entrypoint: `uvicorn av_nexus.asgi:app`."""

from __future__ import annotations

from av_nexus.main import create_app

app = create_app()

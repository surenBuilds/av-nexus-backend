"""AV Nexus FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from av_nexus.agents import get_registry
from av_nexus.api import (
    activity,
    agents,
    approvals,
    auth,
    companies,
    dashboard,
    memory,
    orchestrator,
    tasks,
    workflows,
)
from av_nexus.config import settings
from av_nexus.db.session import create_session, init_db
from av_nexus.orchestrator.service import OrchestratorService
from av_nexus.seed.demo import seed_demo

ROUTERS = [
    auth.router,
    agents.router,
    tasks.router,
    companies.opportunity_router,
    companies.company_router,
    approvals.router,
    memory.router,
    dashboard.router,
    orchestrator.router,
    activity.router,
    workflows.router,
]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    init_db()
    session = create_session()
    try:
        from av_nexus.llm.factory import build_llm_client

        OrchestratorService(session, get_registry(), build_llm_client()).sync_agent_registry()
        if settings.seed_demo:
            seed_demo(session)
    finally:
        session.close()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="AI Business Operating System — multi-agent organization.",
        docs_url="/docs",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", tags=["system"])
    def health() -> dict[str, str]:
        return {"status": "ok", "app": settings.app_name, "env": settings.env}

    for router in ROUTERS:
        app.include_router(router, prefix=settings.api_prefix)

    @app.exception_handler(Exception)
    async def unhandled(_request: Request, exc: Exception) -> JSONResponse:
        # Generic 500 without leaking internal details.
        return JSONResponse(status_code=500, content={"ok": False, "error": "internal_error"})

    return app

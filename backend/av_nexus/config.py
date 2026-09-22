"""AV Nexus application configuration (env-driven; no secrets in source)."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AVNEXUS_", env_file=".env", extra="ignore")

    app_name: str = "AV Nexus"
    env: str = "development"
    api_prefix: str = "/api/v1"

    db_url: str = Field(default="sqlite:///./avnexus.db", description="Postgres in production")
    db_echo: bool = False

    # Auth
    jwt_secret: str = "dev-only-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expiry_minutes: int = 60 * 12

    # Execution mode: "mock" (deterministic, offline) | "live" (real provider).
    # Mock never fakes a provider; live never runs without explicit config.
    execution_mode: str = "mock"
    research_tool_enabled: bool = False

    # LLM provider: "off" | "openai" | "anthropic" | "google" | "openai_compatible"
    llm_provider: str = "off"
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_timeout_seconds: int = 60

    # Workflow execution
    workflow_poll_seconds: float = 0.25
    agent_step_timeout_seconds: int = 90

    seed_demo: bool = True
    demo_org_name: str = "AV Holding (Demo)"
    default_org_name: str = "Artiswon"

    # Security
    max_tasks_per_run: int = 20
    agent_retries: int = 2

    # Voxline AI Sales OS integration: real data source for the management
    # agents. Empty base_url means the integration is simply off — no default
    # or hardcoded URL, so a misconfigured deployment fails loudly (calling
    # the endpoint raises) instead of silently pointing at someone else's data.
    voxline_base_url: str = ""
    voxline_api_key: str = ""

    # Telegram integration: lets one bound AV Nexus account query the
    # management agents from Telegram. Empty token means the integration is
    # off. allowed_chat_id restricts replies to a single chat — without it
    # set, the webhook refuses to run agents for anyone (fails closed, not
    # open, since this endpoint is publicly reachable).
    telegram_bot_token: str = ""
    telegram_webhook_secret: str = ""
    telegram_allowed_chat_id: str = ""
    telegram_bound_user_email: str = ""

    # Coding agent: GitHub write access, scoped to an explicit repo
    # allowlist so a malformed input can never target an arbitrary repo.
    # Branch+PR only — nothing in this codebase ever pushes to a base
    # branch directly.
    github_token: str = ""
    github_allowed_repos: str = ""  # comma-separated "owner/repo" list


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

"""Shared schema helpers."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ApiEnvelope(BaseModel):
    ok: bool = True
    data: Any = None
    error: str | None = None


def env_ok(data: Any) -> ApiEnvelope:
    return ApiEnvelope(ok=True, data=data)


def env_err(message: str) -> ApiEnvelope:
    return ApiEnvelope(ok=False, data=None, error=message)


class Page(BaseModel):
    items: list[Any]
    total: int = 0
    limit: int = 50
    offset: int = 0

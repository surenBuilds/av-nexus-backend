"""Shared memory layers (global / company / agent / decision).

This is a documented addition to the brief's 22 tables: the brief requires a
shared memory system (§6) whose layers have no explicit table in the 22-table list.
We store memory rows here; decision memory also lives (durably enriched) in
`decisions`.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from av_nexus.models.base import Base, TimestampMixin, UuidPkMixin


class MemoryItem(UuidPkMixin, TimestampMixin, Base):
    __tablename__ = "memories"

    layer: Mapped[str] = mapped_column(String(32))  # global|company|agent|decision
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    company_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("companies.id"), nullable=True)
    agent_id: Mapped[str] = mapped_column(String(64), default="")
    key: Mapped[str] = mapped_column(String(255))
    value_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    note: Mapped[str] = mapped_column(Text, default="")

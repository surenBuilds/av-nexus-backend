"""Knowledge graph entities and relationships."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from av_nexus.models.base import Base, TimestampMixin, UuidPkMixin


class KnowledgeEntity(UuidPkMixin, TimestampMixin, Base):
    __tablename__ = "knowledge_entities"

    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    entity_type: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(255))
    properties_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class KnowledgeRelationship(UuidPkMixin, Base):
    __tablename__ = "knowledge_relationships"

    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    from_entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_entities.id"), index=True
    )
    to_entity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("knowledge_entities.id"), index=True)
    relationship_type: Mapped[str] = mapped_column(String(64))
    properties_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

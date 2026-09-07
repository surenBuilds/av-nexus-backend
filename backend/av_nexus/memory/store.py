"""Shared memory store (DB-backed; layer-aware)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from av_nexus.models.memory import MemoryItem


class MemoryStore:
    LAYERS = ("global", "company", "agent", "decision")

    def __init__(self, session: Session, org_id: uuid.UUID) -> None:
        self.session = session
        self.org_id = org_id

    def put(
        self,
        layer: str,
        key: str,
        value: dict[str, Any] | None,
        *,
        company_id: uuid.UUID | None = None,
        agent_id: str = "",
        note: str = "",
    ) -> MemoryItem:
        self._check_layer(layer)
        existing = self._find(layer, key, company_id, agent_id)
        if existing is not None:
            existing.value_json = value
            existing.note = note
            self.session.flush()
            return existing
        item = MemoryItem(
            layer=layer,
            org_id=self.org_id,
            company_id=company_id,
            agent_id=agent_id,
            key=key,
            value_json=value,
            note=note,
        )
        self.session.add(item)
        self.session.flush()
        return item

    def get(
        self,
        layer: str,
        key: str,
        *,
        company_id: uuid.UUID | None = None,
        agent_id: str = "",
    ) -> dict[str, Any] | None:
        item = self._find(layer, key, company_id, agent_id)
        return item.value_json if item is not None else None

    def list_layer(self, layer: str) -> list[MemoryItem]:
        self._check_layer(layer)
        stmt = (
            select(MemoryItem)
            .where(MemoryItem.layer == layer, MemoryItem.org_id == self.org_id)
            .order_by(MemoryItem.created_at.desc())
        )
        return list(self.session.scalars(stmt))

    def delete(
        self,
        layer: str,
        key: str,
        *,
        company_id: uuid.UUID | None = None,
        agent_id: str = "",
    ) -> bool:
        item = self._find(layer, key, company_id, agent_id)
        if item is None:
            return False
        self.session.delete(item)
        self.session.flush()
        return True

    def _find(
        self,
        layer: str,
        key: str,
        company_id: uuid.UUID | None,
        agent_id: str,
    ) -> MemoryItem | None:
        stmt = select(MemoryItem).where(
            MemoryItem.layer == layer,
            MemoryItem.org_id == self.org_id,
            MemoryItem.key == key,
            MemoryItem.company_id == company_id,
            MemoryItem.agent_id == agent_id,
        )
        return self.session.scalar(stmt)

    @staticmethod
    def _check_layer(layer: str) -> None:
        if layer not in MemoryStore.LAYERS:
            raise ValueError(f"Unknown memory layer: {layer}")

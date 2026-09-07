"""Knowledge graph store."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from av_nexus.models.knowledge import KnowledgeEntity, KnowledgeRelationship

RELATIONSHIP_TYPES = {
    "operates_in",
    "competes_with",
    "solves",
    "exists_in",
    "funds",
    "sells_to",
    "partners_with",
    "employs",
    "owns",
    "reports_to",
}


class KnowledgeGraphStore:
    def __init__(self, session: Session, org_id: uuid.UUID) -> None:
        self.session = session
        self.org_id = org_id

    def add_entity(
        self, entity_type: str, name: str, properties: dict[str, Any] | None = None
    ) -> KnowledgeEntity:
        ent = KnowledgeEntity(
            org_id=self.org_id, entity_type=entity_type, name=name, properties_json=properties
        )
        self.session.add(ent)
        self.session.flush()
        return ent

    def add_relationship(
        self,
        from_entity_id: uuid.UUID,
        to_entity_id: uuid.UUID,
        relationship_type: str,
        properties: dict[str, Any] | None = None,
    ) -> KnowledgeRelationship:
        if relationship_type not in RELATIONSHIP_TYPES:
            raise ValueError(f"Unknown relationship type: {relationship_type}")
        rel = KnowledgeRelationship(
            org_id=self.org_id,
            from_entity_id=from_entity_id,
            to_entity_id=to_entity_id,
            relationship_type=relationship_type,
            properties_json=properties,
        )
        self.session.add(rel)
        self.session.flush()
        return rel

    def entities(self, entity_type: str | None = None) -> list[KnowledgeEntity]:
        stmt = select(KnowledgeEntity).where(KnowledgeEntity.org_id == self.org_id)
        if entity_type:
            stmt = stmt.where(KnowledgeEntity.entity_type == entity_type)
        return list(self.session.scalars(stmt))

    def relationships(self) -> list[KnowledgeRelationship]:
        stmt = select(KnowledgeRelationship).where(KnowledgeRelationship.org_id == self.org_id)
        return list(self.session.scalars(stmt))

    def graph(self) -> dict[str, object]:
        entities = self.entities()
        rels = self.relationships()
        by_id = {str(e.id): e for e in entities}
        return {
            "entities": [
                {
                    "id": str(e.id),
                    "entity_type": e.entity_type,
                    "name": e.name,
                    "properties": e.properties_json or {},
                }
                for e in entities
            ],
            "relationships": [
                {
                    "id": str(r.id),
                    "from": str(r.from_entity_id),
                    "to": str(r.to_entity_id),
                    "type": r.relationship_type,
                    "from_name": (
                        by_id[str(r.from_entity_id)].name if str(r.from_entity_id) in by_id else ""
                    ),
                    "to_name": (
                        by_id[str(r.to_entity_id)].name if str(r.to_entity_id) in by_id else ""
                    ),
                }
                for r in rels
            ],
        }

"""Memory + knowledge graph routes."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from av_nexus.api.deps import get_org
from av_nexus.db.session import get_session
from av_nexus.knowledge.store import KnowledgeGraphStore
from av_nexus.memory.store import MemoryStore
from av_nexus.models.identity import Organization

router = APIRouter(tags=["memory"])


class MemoryPut(BaseModel):
    layer: str
    key: str
    value: dict[str, Any]
    note: str = ""


class RelationshipCreate(BaseModel):
    from_entity_id: uuid.UUID
    to_entity_id: uuid.UUID
    relationship_type: str
    properties: dict[str, Any] | None = None


@router.get("/memory/{layer}", response_model=list[dict[str, Any]])
def list_layer(
    layer: str,
    session: Session = Depends(get_session),
    org: Organization = Depends(get_org),
) -> list[dict[str, Any]]:
    store = MemoryStore(session, org.id)
    try:
        items = store.list_layer(layer)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return [
        {
            "id": str(i.id),
            "key": i.key,
            "value": i.value_json,
            "company_id": str(i.company_id) if i.company_id else None,
            "agent_id": i.agent_id,
            "note": i.note,
        }
        for i in items
    ]


@router.put("/memory/{layer}", response_model=dict[str, str])
def put(
    layer: str,
    payload: MemoryPut,
    session: Session = Depends(get_session),
    org: Organization = Depends(get_org),
) -> dict[str, str]:
    store = MemoryStore(session, org.id)
    try:
        item = store.put(payload.layer, payload.key, payload.value, note=payload.note)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    session.commit()
    return {"status": "stored", "key": item.key}


class KnowledgeEntityCreate(BaseModel):
    entity_type: str
    name: str
    properties: dict[str, Any] | None = None


@router.get("/knowledge-graph")
def knowledge_graph(
    session: Session = Depends(get_session),
    org: Organization = Depends(get_org),
) -> dict[str, Any]:
    return KnowledgeGraphStore(session, org.id).graph()


@router.post("/knowledge-graph/entities", status_code=status.HTTP_201_CREATED)
def add_entity(
    payload: KnowledgeEntityCreate,
    session: Session = Depends(get_session),
    org: Organization = Depends(get_org),
) -> dict[str, str]:
    entity = KnowledgeGraphStore(session, org.id).add_entity(
        payload.entity_type, payload.name, payload.properties
    )
    session.commit()
    return {"id": str(entity.id), "entity_type": entity.entity_type, "name": entity.name}


@router.post("/knowledge-graph/relationships", status_code=status.HTTP_201_CREATED)
def add_relationship(
    payload: RelationshipCreate,
    session: Session = Depends(get_session),
    org: Organization = Depends(get_org),
) -> dict[str, str]:
    try:
        rel = KnowledgeGraphStore(session, org.id).add_relationship(
            payload.from_entity_id,
            payload.to_entity_id,
            payload.relationship_type,
            payload.properties,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    session.commit()
    return {"id": str(rel.id), "type": rel.relationship_type}

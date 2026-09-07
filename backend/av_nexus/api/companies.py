"""Opportunity + company routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from av_nexus.api.deps import get_org
from av_nexus.core.security import get_current_user, write_audit
from av_nexus.db.session import get_session
from av_nexus.models.identity import Company, Organization, User
from av_nexus.models.opportunities import Opportunity
from av_nexus.schemas.domain import CompanyCreate, CompanyOut, OpportunityCreate, OpportunityOut

opportunity_router = APIRouter(prefix="/opportunities", tags=["opportunities"])
company_router = APIRouter(prefix="/companies", tags=["companies"])


@opportunity_router.post("", response_model=OpportunityOut, status_code=status.HTTP_201_CREATED)
def create_opportunity(
    payload: OpportunityCreate,
    session: Session = Depends(get_session),
    org: Organization = Depends(get_org),
    user: User = Depends(get_current_user),
) -> Opportunity:
    row = Opportunity(
        org_id=org.id,
        title=payload.title,
        description=payload.description,
        category=payload.category,
        opportunity_score=payload.opportunity_score,
        market_potential=payload.market_potential,
        growth_rate=payload.growth_rate,
        competition=payload.competition,
        entry_difficulty=payload.entry_difficulty,
        capital_requirements=payload.capital_requirements,
        risk_score=payload.risk_score,
        source=payload.source,
    )
    session.add(row)
    write_audit(
        session,
        user=user,
        org_id=org.id,
        action="opportunity.create",
        entity_type="opportunity",
        entity_id=str(row.id),
    )
    session.commit()
    session.refresh(row)
    return row


@opportunity_router.get("", response_model=list[OpportunityOut])
def list_opportunities(
    status_filter: str | None = None,
    session: Session = Depends(get_session),
    org: Organization = Depends(get_org),
) -> list[Opportunity]:
    stmt = select(Opportunity).where(Opportunity.org_id == org.id)
    if status_filter:
        stmt = stmt.where(Opportunity.status == status_filter)
    stmt = stmt.order_by(Opportunity.opportunity_score.desc())
    return list(session.scalars(stmt))


@opportunity_router.get("/{opportunity_id}", response_model=OpportunityOut)
def get_opportunity(
    opportunity_id: uuid.UUID,
    session: Session = Depends(get_session),
    org: Organization = Depends(get_org),
) -> Opportunity:
    row = session.get(Opportunity, opportunity_id)
    if row is None or row.org_id != org.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Opportunity not found")
    return row


@company_router.post("", response_model=CompanyOut, status_code=status.HTTP_201_CREATED)
def create_company(
    payload: CompanyCreate,
    session: Session = Depends(get_session),
    org: Organization = Depends(get_org),
    user: User = Depends(get_current_user),
) -> Company:
    slug = "".join(c if c.isalnum() else "-" for c in payload.name.lower()).strip("-") or "company"
    existing = session.scalar(select(Company).where(Company.org_id == org.id, Company.slug == slug))
    if existing is not None:
        slug = f"{slug}-{uuid.uuid4().hex[:4]}"
    row = Company(
        org_id=org.id,
        name=payload.name,
        slug=slug,
        industry=payload.industry,
        stage=payload.stage,
        mission=payload.mission,
        vision=payload.vision,
    )
    session.add(row)
    write_audit(
        session,
        user=user,
        org_id=org.id,
        action="company.create",
        entity_type="company",
        entity_id=str(row.id),
    )
    session.commit()
    session.refresh(row)
    return row


@company_router.get("", response_model=list[CompanyOut])
def list_companies(
    session: Session = Depends(get_session), org: Organization = Depends(get_org)
) -> list[Company]:
    return list(
        session.scalars(
            select(Company)
            .where(Company.org_id == org.id)
            .order_by(Company.business_health_score.desc())
        )
    )


@company_router.get("/{company_id}", response_model=CompanyOut)
def get_company(
    company_id: uuid.UUID,
    session: Session = Depends(get_session),
    org: Organization = Depends(get_org),
) -> Company:
    row = session.get(Company, company_id)
    if row is None or row.org_id != org.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Company not found")
    return row

"""Demo seed data — sample companies Voxline AI, KrtLab, Atlas.

Every demo row is flagged `is_demo=True`. Nothing here represents real business
metrics; the dashboard renders a DEMO DATA badge accordingly.
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from av_nexus.core.security import hash_password
from av_nexus.models.audit import AuditLog
from av_nexus.models.catalog import FinancialMetric, Kpi, Product, Project
from av_nexus.models.enums import (
    CompanyStage,
    OpportunityStatus,
    RiskCategory,
    RiskLevel,
    Role,
)
from av_nexus.models.identity import Company, Organization, User
from av_nexus.models.knowledge import KnowledgeEntity, KnowledgeRelationship
from av_nexus.models.memory import MemoryItem
from av_nexus.models.opportunities import Competitor, Market, Opportunity
from av_nexus.models.risks import Risk

# .local is reserved by RFC 6762 (multicast DNS) and rejected by pydantic's
# EmailStr validator. Use a real, registerable public TLD instead: .ai is a
# valid ccTLD and matches the product. Reserved TLDs (.local, .test, .invalid,
# .localhost, .onion) are exactly what the validator refuses.
DEMO_EMAIL = "chairman@avnexus.ai"
DEMO_PASSWORD = "demo-chairman-2026"
DEMO_ORG_SLUG = "av-holding-demo"


def seed_demo(session: Session) -> bool:
    """Idempotent demo seed. Returns True when it seeded fresh data."""
    existing = session.scalar(select(Organization).where(Organization.slug == DEMO_ORG_SLUG))
    if existing is not None:
        return False

    user = User(
        email=DEMO_EMAIL,
        password_hash=hash_password(DEMO_PASSWORD),
        full_name="Demo Chairman",
        role=Role.CHAIRMAN.value,
        can_authorize_level4=True,
    )
    session.add(user)
    session.flush()

    org = Organization(name="AV Holding (Demo)", slug=DEMO_ORG_SLUG, owner_id=user.id, is_demo=True)
    session.add(org)
    session.flush()

    _seed_companies(session, org.id)
    _seed_opportunities(session, org.id)
    _seed_markets(session)
    _seed_competitors(session, org.id)
    _seed_risks(session, org.id)
    _seed_knowledge(session, org.id)
    _seed_memory(session, org.id)
    _seed_audit(session, user.id, org.id)

    session.commit()
    return True


def _seed_companies(session: Session, org_id: uuid.UUID) -> None:
    vox = Company(
        org_id=org_id,
        name="Voxline AI",
        slug="voxline-ai",
        industry="ai_voice",
        stage=CompanyStage.ACTIVE.value,
        mission="Conversational AI for SMB customer service",
        vision="Every small business runs on friendly AI voice agents",
        business_health_score=76.0,
        is_demo=True,
    )
    krt = Company(
        org_id=org_id,
        name="KrtLab",
        slug="krtlab",
        industry="creative_media",
        stage=CompanyStage.GROWTH.value,
        mission="Creative tooling studios for digital media teams",
        vision="The creative lab that ships with partners",
        business_health_score=62.0,
        is_demo=True,
    )
    atlas = Company(
        org_id=org_id,
        name="Atlas",
        slug="atlas",
        industry="logistics_tech",
        stage=CompanyStage.MVP.value,
        mission="SME logistics orchestration",
        vision="Frictionless freight for regional operators",
        business_health_score=41.0,
        is_demo=True,
    )
    session.add_all([vox, krt, atlas])
    session.flush()

    session.add_all(
        [
            Product(
                company_id=vox.id,
                name="Voxline Voice Desk",
                pricing_model="per-minute",
                status="active",
                is_demo=True,
            ),
            Product(
                company_id=vox.id,
                name="Voxline Insight",
                pricing_model="seat",
                status="beta",
                is_demo=True,
            ),
            Product(
                company_id=krt.id,
                name="KrtLab Studio",
                pricing_model="project",
                status="active",
                is_demo=True,
            ),
            Product(
                company_id=atlas.id,
                name="Atlas Route",
                pricing_model="per-shipment",
                status="mvp",
                is_demo=True,
            ),
        ]
    )
    today = date.today()
    session.add_all(
        [
            Kpi(
                company_id=vox.id,
                name="MRR",
                value=18200,
                target=20000,
                unit="usd",
                period="month",
                recorded_at=today,
                is_demo=True,
            ),
            Kpi(
                company_id=vox.id,
                name="Churn",
                value=3.1,
                target=5.0,
                unit="pct",
                period="month",
                recorded_at=today,
                is_demo=True,
            ),
            Kpi(
                company_id=krt.id,
                name="Active Projects",
                value=14,
                target=16,
                unit="count",
                period="month",
                recorded_at=today,
                is_demo=True,
            ),
            Kpi(
                company_id=atlas.id,
                name="Tracked Shipments",
                value=820,
                target=1500,
                unit="count",
                period="month",
                recorded_at=today,
                is_demo=True,
            ),
        ]
    )
    session.add_all(
        [
            FinancialMetric(
                company_id=vox.id,
                metric="revenue",
                value=18200,
                currency="USD",
                period="month",
                is_demo=True,
            ),
            FinancialMetric(
                company_id=vox.id,
                metric="gross_margin",
                value=68.0,
                currency="USD",
                period="month",
                is_demo=True,
            ),
            FinancialMetric(
                company_id=vox.id,
                metric="cac",
                value=140.0,
                currency="USD",
                period="quarter",
                is_demo=True,
            ),
            FinancialMetric(
                company_id=vox.id,
                metric="ltv",
                value=420.0,
                currency="USD",
                period="quarter",
                is_demo=True,
            ),
            FinancialMetric(
                company_id=krt.id,
                metric="revenue",
                value=9100,
                currency="USD",
                period="month",
                is_demo=True,
            ),
            FinancialMetric(
                company_id=krt.id,
                metric="burn_rate",
                value=2600,
                currency="USD",
                period="month",
                is_demo=True,
            ),
            FinancialMetric(
                company_id=atlas.id,
                metric="revenue",
                value=2400,
                currency="USD",
                period="month",
                is_demo=True,
            ),
            FinancialMetric(
                company_id=atlas.id,
                metric="runway_months",
                value=5.0,
                currency="USD",
                period="month",
                is_demo=True,
            ),
        ]
    )
    session.add_all(
        [
            Project(
                company_id=vox.id,
                name="Voice Desk 2.0",
                description="Multilingual routing",
                status="on_track",
                is_demo=True,
            ),
            Project(
                company_id=atlas.id,
                name="Carrier API",
                description="Carrier integrations",
                status="delayed",
                is_demo=True,
            ),
        ]
    )


def _seed_opportunities(session: Session, org_id: uuid.UUID) -> None:
    session.add_all(
        [
            Opportunity(
                org_id=org_id,
                title="AI Study Companion for University Students",
                description=(
                    "Personalized LLM-based study planning and tutoring, "
                    "underserved in non-English markets."
                ),
                category="ai_education",
                opportunity_score=81.0,
                market_potential=84.0,
                growth_rate=78.0,
                competition=48.0,
                entry_difficulty=55.0,
                capital_requirements=45.0,
                risk_score=35.0,
                status=OpportunityStatus.VALIDATED.value,
                source="internal scan",
                is_demo=True,
            ),
            Opportunity(
                org_id=org_id,
                title="SME Compliance Automation",
                description="Automated regulatory document drafting for small firms.",
                category="ai_b2b_automation",
                opportunity_score=74.0,
                market_potential=80.0,
                growth_rate=64.0,
                competition=55.0,
                entry_difficulty=40.0,
                capital_requirements=30.0,
                risk_score=40.0,
                status=OpportunityStatus.DISCOVERED.value,
                source="internal scan",
                is_demo=True,
            ),
            Opportunity(
                org_id=org_id,
                title="Regional Cold-Chain Tracking for Wholesalers",
                description="IoT-lite tracking for regional fresh produce wholesalers.",
                category="logistics_tech",
                opportunity_score=58.0,
                market_potential=66.0,
                growth_rate=44.0,
                competition=62.0,
                entry_difficulty=70.0,
                capital_requirements=75.0,
                risk_score=55.0,
                status=OpportunityStatus.RESEARCHED.value,
                source="internal scan",
                is_demo=True,
            ),
        ]
    )


def _seed_markets(session: Session) -> None:
    session.add_all(
        [
            Market(
                name="AI education tools",
                industry="edtech",
                region="global",
                tam=250.0,
                sam=90.0,
                som=8.0,
                growth_rate_pct=22.0,
                notes="Estimate model; demo data.",
                is_demo=True,
            ),
            Market(
                name="SME back-office SaaS",
                industry="b2b_software",
                region="global",
                tam=400.0,
                sam=140.0,
                som=20.0,
                growth_rate_pct=14.0,
                notes="Estimate model; demo data.",
                is_demo=True,
            ),
        ]
    )


def _seed_competitors(session: Session, org_id: uuid.UUID) -> None:
    session.add_all(
        [
            Competitor(
                name="TutorAI",
                industry="edtech",
                company_id=None,
                products="tutoring bot",
                pricing="freemium",
                strengths_j=["brand", "content"],
                weaknesses_j=["not localized"],
                threat_score=72.0,
                recent_developments="raised series A",
                is_demo=True,
            ),
            Competitor(
                name="LegiDesk",
                industry="legaltech",
                company_id=None,
                products="document automation",
                pricing="seat",
                strengths_j=["legal partnerships"],
                weaknesses_j=["complex setup"],
                threat_score=55.0,
                recent_developments="released compliance pack",
                is_demo=True,
            ),
        ]
    )


def _seed_risks(session: Session, org_id: uuid.UUID) -> None:
    session.add_all(
        [
            Risk(
                org_id=org_id,
                title="Atlas carrier dependency",
                category=RiskCategory.OPERATIONAL.value,
                level=RiskLevel.HIGH.value,
                description="Reliance on two carriers",
                mitigation="Multi-carrier integration plan",
                status="open",
                owner_agent="operations",
                is_demo=True,
            ),
            Risk(
                org_id=org_id,
                title="Voxline retention",
                category=RiskCategory.MARKET.value,
                level=RiskLevel.MEDIUM.value,
                description="Churn above target in SMB segment",
                mitigation="SMB onboarding redesign",
                status="mitigating",
                owner_agent="ceo",
                is_demo=True,
            ),
            Risk(
                org_id=org_id,
                title="LLM cost exposure",
                category=RiskCategory.TECHNOLOGY.value,
                level=RiskLevel.MEDIUM.value,
                description="Token costs on usage pricing",
                mitigation="Usage guardrails + cheaper models",
                status="open",
                owner_agent="finance",
                is_demo=True,
            ),
        ]
    )


def _seed_knowledge(session: Session, org_id: uuid.UUID) -> None:
    community = session.scalar(select(KnowledgeEntity).where(KnowledgeEntity.org_id == org_id))
    if community is not None:
        return
    vox = KnowledgeEntity(org_id=org_id, entity_type="company", name="Voxline AI")
    edtech = KnowledgeEntity(org_id=org_id, entity_type="industry", name="AI Education")
    study = KnowledgeEntity(org_id=org_id, entity_type="opportunity", name="AI Study Companion")
    session.add_all([vox, edtech, study])
    session.flush()
    session.add_all(
        [
            KnowledgeRelationship(
                org_id=org_id,
                from_entity_id=vox.id,
                to_entity_id=edtech.id,
                relationship_type="operates_in",
            ),
            KnowledgeRelationship(
                org_id=org_id,
                from_entity_id=study.id,
                to_entity_id=edtech.id,
                relationship_type="exists_in",
            ),
        ]
    )


def _seed_memory(session: Session, org_id: uuid.UUID) -> None:
    session.add(
        MemoryItem(
            layer="global",
            org_id=org_id,
            key="chairman_goals",
            value_json={"positioning": "AI-enabled business group", "focus": "SME automation"},
            note="Demo guidance",
            agent_id="",
        )
    )


def _seed_audit(session: Session, user_id: uuid.UUID, org_id: uuid.UUID) -> None:
    session.add(
        AuditLog(
            user_id=user_id,
            org_id=org_id,
            action="seed.demo_created",
            entity_type="organization",
            details_json={"demo": True},
        )
    )

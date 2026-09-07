"""Model registry — import every model module so create_all sees all tables."""

from av_nexus.models.agents import (
    Agent,
    AgentCapability,
    AgentMessage,
    AgentRun,
    Task,
    TaskDependency,
)
from av_nexus.models.audit import AuditLog
from av_nexus.models.base import (
    Base as Base,
)  # noqa: F401
from av_nexus.models.base import (
    TimestampMixin as TimestampMixin,
)
from av_nexus.models.base import (
    UuidPkMixin as UuidPkMixin,
)
from av_nexus.models.base import (
    utcnow as utcnow,
)
from av_nexus.models.catalog import (
    FinancialMetric,
    Kpi,
    Product,
    Project,
)
from av_nexus.models.decisions import Approval, Decision
from av_nexus.models.identity import Company, Organization, User
from av_nexus.models.knowledge import KnowledgeEntity, KnowledgeRelationship
from av_nexus.models.memory import MemoryItem
from av_nexus.models.opportunities import Competitor, Market, Opportunity
from av_nexus.models.risks import Risk
from av_nexus.models.workflows import Workflow, WorkflowEvent, WorkflowResult, WorkflowStep

__all__ = [
    "Base",
    "User",
    "Organization",
    "Company",
    "Agent",
    "AgentCapability",
    "AgentMessage",
    "AgentRun",
    "Task",
    "TaskDependency",
    "Product",
    "Project",
    "Kpi",
    "FinancialMetric",
    "Decision",
    "Approval",
    "Opportunity",
    "Market",
    "Competitor",
    "Risk",
    "AuditLog",
    "KnowledgeEntity",
    "KnowledgeRelationship",
    "MemoryItem",
    "Workflow",
    "WorkflowStep",
    "WorkflowEvent",
    "WorkflowResult",
]

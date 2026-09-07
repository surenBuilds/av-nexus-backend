"""AV Nexus shared enums."""

from enum import IntEnum, StrEnum


class Role(StrEnum):
    CHAIRMAN = "chairman"
    ADMIN = "admin"
    ANALYST = "analyst"
    AGENT = "agent"


class TaskStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    WAITING = "WAITING"
    REVIEW = "REVIEW"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ApprovalStatus(StrEnum):
    NONE = "none"
    REQUIRED = "required"
    APPROVED = "approved"
    REJECTED = "rejected"


class Priority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AgentStatus(StrEnum):
    IDLE = "idle"
    THINKING = "thinking"
    RESEARCHING = "researching"
    WAITING = "waiting"
    BLOCKED = "blocked"
    REVIEWING = "reviewing"
    COMPLETED = "completed"
    FAILED = "failed"


class CompanyStage(StrEnum):
    IDEA = "idea"
    MVP = "mvp"
    ACTIVE = "active"
    GROWTH = "growth"
    PAUSED = "paused"


class OpportunityStatus(StrEnum):
    DISCOVERED = "discovered"
    RESEARCHED = "researched"
    VALIDATED = "validated"
    APPROVED = "approved"
    REJECTED = "rejected"
    PAUSED = "paused"


class DecisionType(StrEnum):
    CAPITAL_ALLOCATION = "capital_allocation"
    BUILD_COMPANY = "build_company"
    KILL_COMPANY = "kill_company"
    STRATEGY = "strategy"
    APPROVAL = "approval"
    OTHER = "other"


class DecisionStatus(StrEnum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"
    MODIFIED = "modified"


class ApprovalLevel(IntEnum):
    """Level 1-4 gates; stored as integer and compared numerically."""

    LEVEL1 = 1  # research / analyze — automatic
    LEVEL2 = 2  # plans / drafts — automatic
    LEVEL3 = 3  # external action — approval required
    LEVEL4 = 4  # Chairman only (money, contracts, hiring, legal, irreversible)

    def human_label(self) -> str:
        return {
            1: "Research & analysis (auto)",
            2: "Plans & drafts (auto)",
            3: "External action (approval required)",
            4: "Chairman approval required",
        }[self.value]

    def __str__(self) -> str:
        return str(self.value)


class RiskLevel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class RiskCategory(StrEnum):
    FINANCIAL = "financial"
    MARKET = "market"
    OPERATIONAL = "operational"
    TECHNOLOGY = "technology"
    REPUTATION = "reputation"
    STRATEGIC = "strategic"
    COMPLIANCE = "compliance"


class MessageType(StrEnum):
    TASK_ASSIGNMENT = "task_assignment"
    HANDOFF = "handoff"
    RESULT = "result"
    QUESTION = "question"
    DISAGREEMENT = "disagreement"
    CRITIQUE = "critique"
    ESCALATION = "escalation"
    APPROVAL_REQUEST = "approval_request"


class EntityType(StrEnum):
    COMPANY = "company"
    TASK = "task"
    OPPORTUNITY = "opportunity"
    DECISION = "decision"


class WorkflowStatus(StrEnum):
    """Workflow lifecycle (Phase 2A). Server restart must not destroy state."""

    CREATED = "CREATED"
    PLANNING = "PLANNING"
    RUNNING = "RUNNING"
    WAITING_FOR_DEPENDENCY = "WAITING_FOR_DEPENDENCY"
    WAITING_FOR_APPROVAL = "WAITING_FOR_APPROVAL"
    REVIEWING = "REVIEWING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class WorkflowEventType(StrEnum):
    CREATED = "created"
    PLANNED = "planned"
    STARTED = "started"
    STEP_STARTED = "step_started"
    STEP_COMPLETED = "step_completed"
    STEP_FAILED = "step_failed"
    STEP_CANCELLED = "step_cancelled"
    DISAGREEMENT_DETECTED = "disagreement_detected"
    CRITIQUE_REQUESTED = "critique_requested"
    CRITIQUE_COMPLETED = "critique_completed"
    APPROVAL_REQUIRED = "approval_required"
    APPROVAL_RESOLVED = "approval_resolved"
    APPROVAL_REJECTED = "approval_rejected"
    PAUSED = "paused"
    RESUMED = "resumed"
    SYNTHESIS_COMPLETED = "synthesis_completed"
    MEMORY_SAVED = "memory_saved"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    FAILED = "failed"


class HealthStatus(StrEnum):
    GREEN = "GREEN"
    YELLOW = "YELLOW"
    RED = "RED"

    @staticmethod
    def from_score(score: float) -> "HealthStatus":
        if score >= 70:
            return HealthStatus.GREEN
        if score >= 45:
            return HealthStatus.YELLOW
        return HealthStatus.RED

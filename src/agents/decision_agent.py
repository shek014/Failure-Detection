"""Decision Agent: determines auto-resolve vs human approval vs escalation."""

from __future__ import annotations

from config.settings import get_settings
from src.database.store import IncidentRepository
from src.models.incident import (
    AuditEntry,
    DecisionAction,
    DecisionResult,
    IncidentContext,
    RiskAssessment,
    RiskLevel,
)


class DecisionAgent:
    def __init__(self, repository: IncidentRepository | None = None) -> None:
        self.settings = get_settings()
        self.repository = repository or IncidentRepository()

    def decide(self, context: IncidentContext, assessment: RiskAssessment) -> DecisionResult:
        incident = context.incident
        risk = assessment.risk_level

        if risk == RiskLevel.LOW and self.settings.auto_resolve_low_risk:
            result = DecisionResult(
                action=DecisionAction.AUTO_RESOLVE,
                rationale="Low risk incident - auto-resolve enabled",
                auto_execute=True,
            )
        elif risk == RiskLevel.MEDIUM:
            result = DecisionResult(
                action=DecisionAction.AUTO_RESOLVE_WITH_VERIFICATION,
                rationale="Medium risk - auto-resolve with human verification",
                auto_execute=True,
            )
        elif risk == RiskLevel.HIGH and self.settings.require_approval_high_risk:
            result = DecisionResult(
                action=DecisionAction.REQUIRE_HUMAN_APPROVAL,
                rationale="High risk action requires human approval",
                auto_execute=False,
            )
        else:
            result = DecisionResult(
                action=DecisionAction.IMMEDIATE_ESCALATION,
                rationale="Critical risk - immediate escalation to on-call engineer",
                auto_execute=False,
            )

        incident.decision_action = result.action

        self.repository.log_audit(
            AuditEntry(
                incident_id=incident.id or "",
                agent_name="DecisionAgent",
                action="decision_made",
                input_data={"risk_level": risk.value},
                output_data=result.model_dump(mode="json"),
            )
        )
        return result

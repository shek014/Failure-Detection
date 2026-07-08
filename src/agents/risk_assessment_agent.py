"""Risk Assessment Agent: evaluates remediation safety."""

from __future__ import annotations

from src.database.store import IncidentRepository
from src.models.incident import (
    AuditEntry,
    IncidentContext,
    RemediationAction,
    RiskAssessment,
    RiskLevel,
    RootCauseAnalysis,
)


class RiskAssessmentAgent:
    RISK_MATRIX = {
        RemediationAction.RESTART_SERVICE: RiskLevel.LOW,
        RemediationAction.CLEAR_CACHE: RiskLevel.LOW,
        RemediationAction.SCALE_CONTAINERS: RiskLevel.MEDIUM,
        RemediationAction.ROLLBACK_DEPLOYMENT: RiskLevel.MEDIUM,
        RemediationAction.RECONNECT_DATABASE: RiskLevel.HIGH,
        RemediationAction.RESTART_PODS: RiskLevel.MEDIUM,
    }

    ROOT_CAUSE_ACTIONS = {
        "Memory Leak": RemediationAction.RESTART_SERVICE,
        "Connection Pool Exhaustion": RemediationAction.RECONNECT_DATABASE,
        "Service Crash": RemediationAction.RESTART_PODS,
        "CPU Bottleneck": RemediationAction.SCALE_CONTAINERS,
        "Downstream Dependency Failure": RemediationAction.RESTART_SERVICE,
        "Application Error Spike": RemediationAction.RESTART_SERVICE,
        "Database Failure": RemediationAction.RECONNECT_DATABASE,
        "Bad Deployment": RemediationAction.ROLLBACK_DEPLOYMENT,
    }

    CRITICAL_CAUSES = {"Security Incident", "Data Corruption", "Unknown - Requires Investigation"}

    def __init__(self, repository: IncidentRepository | None = None) -> None:
        self.repository = repository or IncidentRepository()

    def assess(self, context: IncidentContext, rca: RootCauseAnalysis) -> RiskAssessment:
        incident = context.incident

        if rca.root_cause in self.CRITICAL_CAUSES or rca.confidence < 50:
            assessment = RiskAssessment(
                risk_level=RiskLevel.CRITICAL,
                recommended_action=RemediationAction.NONE,
                rationale=f"Critical: {rca.root_cause} with {rca.confidence:.0f}% confidence",
                requires_human=True,
            )
        else:
            action = self.ROOT_CAUSE_ACTIONS.get(rca.root_cause, RemediationAction.RESTART_SERVICE)
            risk = self.RISK_MATRIX.get(action, RiskLevel.MEDIUM)

            if incident.severity.value == "critical":
                order = ["low", "medium", "high", "critical"]
                if order.index(risk.value) < order.index(RiskLevel.HIGH.value):
                    risk = RiskLevel.HIGH

            assessment = RiskAssessment(
                risk_level=risk,
                recommended_action=action,
                rationale=f"{rca.root_cause} -> {action.value} (risk: {risk.value})",
                requires_human=risk in (RiskLevel.HIGH, RiskLevel.CRITICAL),
            )

        incident.risk_level = assessment.risk_level
        incident.remediation_action = assessment.recommended_action

        self.repository.log_audit(
            AuditEntry(
                incident_id=incident.id or "",
                agent_name="RiskAssessmentAgent",
                action="risk_assessed",
                input_data={"root_cause": rca.root_cause, "confidence": rca.confidence},
                output_data=assessment.model_dump(mode="json"),
            )
        )
        return assessment

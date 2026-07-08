"""Resolution Agent: executes approved remediation via MCP."""

from __future__ import annotations

from src.database.store import IncidentRepository
from src.models.incident import (
    AuditEntry,
    Incident,
    RemediationAction,
    ResolutionResult,
)
from src.mcp.tools import MCPToolExecutor


class ResolutionAgent:
    def __init__(
        self,
        repository: IncidentRepository | None = None,
        executor: MCPToolExecutor | None = None,
    ) -> None:
        self.repository = repository or IncidentRepository()
        self.executor = executor or MCPToolExecutor()

    def resolve(self, incident: Incident, approved: bool = True) -> ResolutionResult:
        if not approved:
            return ResolutionResult(
                action=incident.remediation_action,
                success=False,
                message="Remediation not approved by human or decision agent",
            )

        if incident.remediation_action == RemediationAction.NONE:
            return ResolutionResult(
                action=RemediationAction.NONE,
                success=False,
                message="No remediation action recommended",
            )

        result = self.executor.execute(
            incident.remediation_action,
            incident.affected_service,
        )

        incident.resolution_success = result.success
        incident.remediation_action = result.action

        self.repository.log_audit(
            AuditEntry(
                incident_id=incident.id or "",
                agent_name="ResolutionAgent",
                action="remediation_executed",
                input_data={"action": result.action.value, "approved": approved},
                output_data=result.model_dump(mode="json"),
            )
        )
        return result

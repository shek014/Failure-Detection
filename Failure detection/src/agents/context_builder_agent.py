"""Context Builder Agent: structures raw data into actionable incident context."""

from __future__ import annotations

from src.database.store import IncidentRepository
from src.models.incident import AuditEntry, IncidentContext


class ContextBuilderAgent:
    def __init__(self, repository: IncidentRepository | None = None) -> None:
        self.repository = repository or IncidentRepository()

    def build(self, context: IncidentContext) -> IncidentContext:
        incident = context.incident
        similar_lines = (
            [f"  #{sid}" for sid in incident.similar_incidents]
            if incident.similar_incidents
            else ["  None found"]
        )
        runbook_lines = (
            [f"  {rb}" for rb in incident.runbook_refs]
            if incident.runbook_refs
            else ["  None matched"]
        )
        lines = [
            f"Incident: #{incident.id}",
            "",
            f"Service:\n{incident.affected_service}",
            "",
            "Symptoms:",
            *[f"  - {s}" for s in incident.symptoms],
            "",
            "Logs:",
            *[f"  {log}" for log in incident.logs[:5]],
            "",
            "Similar Incidents:",
            *similar_lines,
            "",
            "Runbooks:",
            *runbook_lines,
            "",
            "Dependencies:",
            *[f"  {k}: {v}" for k, v in incident.dependencies.items()],
        ]

        if incident.correlated_alert_count:
            lines.extend(
                [
                    "",
                    "Alert Correlation:",
                    f"  Root incident: {incident.affected_service}",
                    f"  Generated alerts: {incident.correlated_alert_count}",
                    f"  Correlation ID: {incident.correlation_id}",
                ]
            )

        if incident.dependency_graph:
            lines.extend(["", "Dependency Graph:"])
            for node in incident.dependency_graph:
                deps = ", ".join(node.get("depends_on", [])) or "none"
                lines.append(
                    f"  {node['name']}: {node['status']} "
                    f"({node.get('latency_ms', 0):.0f}ms) → depends on [{deps}]"
                )

        context.structured_summary = "\n".join(lines)

        self.repository.log_audit(
            AuditEntry(
                incident_id=incident.id or "",
                agent_name="ContextBuilderAgent",
                action="context_built",
                input_data={"symptoms_count": len(incident.symptoms)},
                output_data={"summary_length": len(context.structured_summary)},
            )
        )
        return context

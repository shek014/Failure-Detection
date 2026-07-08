"""Notification & Reporting Agent."""

from __future__ import annotations

import json
import re

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq

from config.settings import get_settings
from src.database.store import IncidentRepository
from src.models.incident import AuditEntry, Incident, NotificationReport


class NotificationAgent:
    SYSTEM_PROMPT = """You are an incident communication specialist.
Generate clear, professional incident reports for stakeholders.
Respond in JSON:
{"incident_summary": "...", "root_cause_report": "...", "resolution_report": "...", "stakeholder_message": "..."}
"""

    def __init__(self, repository: IncidentRepository | None = None) -> None:
        self.settings = get_settings()
        self.repository = repository or IncidentRepository()
        self._llm = None

    @property
    def llm(self) -> ChatGroq | None:
        if self._llm is None and self.settings.groq_api_key:
            self._llm = ChatGroq(
                model=self.settings.groq_model,
                api_key=self.settings.groq_api_key,
                temperature=0.3,
            )
        return self._llm

    def generate_report(self, incident: Incident) -> NotificationReport:
        if self.llm:
            report = self._generate_with_llm(incident)
        else:
            report = self._generate_template(incident)

        incident.summary = report.incident_summary
        incident.resolution_report = report.resolution_report

        self.repository.log_audit(
            AuditEntry(
                incident_id=incident.id or "",
                agent_name="NotificationAgent",
                action="report_generated",
                input_data={"status": incident.status.value},
                output_data=report.model_dump(mode="json"),
            )
        )
        return report

    def _generate_template(self, incident: Incident) -> NotificationReport:
        status = "resolved successfully" if incident.verification_passed else "requires attention"
        summary = (
            f"Incident {incident.id}: {incident.affected_service} experienced "
            f"{incident.anomaly_type} (severity: {incident.severity.value}). Status: {status}."
        )
        rca = (
            f"Root cause identified as '{incident.root_cause}' "
            f"with {incident.root_cause_confidence:.0f}% confidence. "
            f"Evidence: {'; '.join(incident.supporting_evidence[:3])}"
        )
        resolution = (
            f"Action taken: {incident.remediation_action.value}. "
            f"Result: {'Success' if incident.resolution_success else 'Failed/Pending'}. "
            f"Verification: {'Passed' if incident.verification_passed else 'Failed'}."
        )
        stakeholder = (
            f"{incident.affected_service} experienced {incident.anomaly_type.lower()} "
            f"due to {incident.root_cause.lower()}. "
            f"The system {'automatically resolved' if incident.resolution_success else 'attempted to resolve'} "
            f"the issue and {'verified successful recovery' if incident.verification_passed else 'could not verify recovery'}."
        )
        return NotificationReport(
            incident_summary=summary,
            root_cause_report=rca,
            resolution_report=resolution,
            stakeholder_message=stakeholder,
        )

    def _generate_with_llm(self, incident: Incident) -> NotificationReport:
        prompt = (
            f"Generate incident report for:\n"
            f"ID: {incident.id}\nService: {incident.affected_service}\n"
            f"Anomaly: {incident.anomaly_type}\nSeverity: {incident.severity.value}\n"
            f"Root Cause: {incident.root_cause} ({incident.root_cause_confidence}%)\n"
            f"Action: {incident.remediation_action.value}\n"
            f"Resolution: {'Success' if incident.resolution_success else 'Failed'}\n"
            f"Verification: {'Passed' if incident.verification_passed else 'Failed'}"
        )
        try:
            response = self.llm.invoke(
                [SystemMessage(content=self.SYSTEM_PROMPT), HumanMessage(content=prompt)]
            )
            match = re.search(r"\{.*\}", response.content, re.DOTALL)
            if match:
                data = json.loads(match.group())
                return NotificationReport(**data)
        except Exception:
            pass
        return self._generate_template(incident)

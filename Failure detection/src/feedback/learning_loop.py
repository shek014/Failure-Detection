"""Feedback & Learning Loop: stores outcomes for future RAG improvement."""

from __future__ import annotations

from src.database.store import IncidentRepository
from src.models.incident import AuditEntry, FeedbackRecord, Incident
from src.rag.knowledge_base import KnowledgeBase


class FeedbackLearningLoop:
    def __init__(
        self,
        repository: IncidentRepository | None = None,
        knowledge_base: KnowledgeBase | None = None,
    ) -> None:
        self.repository = repository or IncidentRepository()
        self.knowledge_base = knowledge_base or KnowledgeBase()

    def record_outcome(
        self,
        incident: Incident,
        human_override: bool = False,
        lessons_learned: str = "",
    ) -> FeedbackRecord:
        outcome = "success" if incident.verification_passed else "failure"
        if human_override:
            outcome = "human_override"

        feedback = FeedbackRecord(
            incident_id=incident.id or "",
            outcome=outcome,
            human_override=human_override,
            resolution_success=incident.resolution_success or False,
            verification_passed=incident.verification_passed or False,
            lessons_learned=lessons_learned or self._auto_lessons(incident),
        )

        self.repository.save_feedback(feedback)
        self.knowledge_base.add_resolved_incident(incident, feedback.lessons_learned)
        self.knowledge_base.add_feedback(
            incident.id or "", feedback.lessons_learned, outcome
        )

        self.repository.log_audit(
            AuditEntry(
                incident_id=incident.id or "",
                agent_name="FeedbackLearningLoop",
                action="feedback_recorded",
                input_data={"outcome": outcome, "human_override": human_override},
                output_data=feedback.model_dump(mode="json"),
            )
        )
        return feedback

    def _auto_lessons(self, incident: Incident) -> str:
        if incident.verification_passed:
            return (
                f"{incident.root_cause} on {incident.affected_service} resolved via "
                f"{incident.remediation_action.value}. Auto-resolution effective."
            )
        return (
            f"{incident.root_cause} on {incident.affected_service} could not be auto-resolved. "
            f"Manual intervention required."
        )

"""Knowledge base management and RAG retrieval."""

from typing import Any

from src.models.incident import Incident
from src.rag.vector_store import VectorStore


class KnowledgeBase:
    def __init__(self) -> None:
        self.vector_store = VectorStore()

    def retrieve_for_incident(self, incident: Incident) -> dict[str, Any]:
        query = self._build_query(incident)
        results = self.vector_store.search_all(query, n_results=3)
        return {
            "runbooks": results.get("runbooks", []),
            "historical_incidents": results.get("historical_incidents", []),
            "sops": results.get("sops", []),
            "feedback": results.get("feedback", []),
            "query": query,
        }

    def add_resolved_incident(self, incident: Incident, lessons: str = "") -> None:
        doc = (
            f"Incident {incident.id}: Service {incident.affected_service} "
            f"experienced {incident.anomaly_type}. "
            f"Root cause: {incident.root_cause}. "
            f"Resolution: {incident.remediation_action.value}. "
            f"Outcome: {'success' if incident.resolution_success else 'failure'}. "
            f"Lessons: {lessons}"
        )
        self.vector_store.add_documents(
            "historical_incidents",
            [doc],
            metadatas=[
                {
                    "incident_id": incident.id or "",
                    "service": incident.affected_service,
                    "anomaly_type": incident.anomaly_type,
                    "root_cause": incident.root_cause,
                }
            ],
            ids=[f"hist-{incident.id}"],
        )

    def add_feedback(self, incident_id: str, lessons: str, outcome: str) -> None:
        doc = f"Feedback for {incident_id}: {outcome}. Lessons: {lessons}"
        self.vector_store.add_documents(
            "feedback",
            [doc],
            metadatas={"incident_id": incident_id, "outcome": outcome},
            ids=[f"fb-{incident_id}"],
        )

    def _build_query(self, incident: Incident) -> str:
        parts = [
            incident.affected_service,
            incident.anomaly_type,
            *incident.symptoms,
            *incident.logs[:3],
        ]
        return " ".join(p for p in parts if p)

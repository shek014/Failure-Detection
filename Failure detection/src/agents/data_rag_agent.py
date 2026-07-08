"""Data/RAG Agent: collects telemetry and retrieves knowledge."""

from __future__ import annotations

from src.database.store import IncidentRepository
from src.models.dependency_graph import build_graph_for_scenario
from src.models.incident import AuditEntry, Incident, IncidentContext
from src.monitoring.incident_simulator import ScenarioType
from src.monitoring.prometheus_client import MetricsCollector
from src.rag.knowledge_base import KnowledgeBase


class DataRAGAgent:
    def __init__(
        self,
        repository: IncidentRepository | None = None,
        knowledge_base: KnowledgeBase | None = None,
    ) -> None:
        self.repository = repository or IncidentRepository()
        self.knowledge_base = knowledge_base or KnowledgeBase()
        from config.settings import get_settings

        settings = get_settings()
        self.metrics_collector = MetricsCollector(simulate=settings.simulate_metrics)

    def investigate(self, incident: Incident) -> IncidentContext:
        fresh_metrics = self.metrics_collector.collect(incident.affected_service)
        incident.metrics = fresh_metrics

        rag_results = self.knowledge_base.retrieve_for_incident(incident)

        similar = [
            r["metadata"].get("incident_id", r["id"])
            for r in rag_results.get("historical_incidents", [])
            if r.get("metadata")
        ]
        runbooks = [
            r["metadata"].get("id", r["metadata"].get("title", ""))
            for r in rag_results.get("runbooks", [])
            if r.get("metadata")
        ]

        incident.similar_incidents = similar
        incident.runbook_refs = runbooks
        incident.dependency_graph, incident.dependencies = self._build_dependencies(incident)

        all_docs = []
        for category, docs in rag_results.items():
            if category == "query":
                continue
            for doc in docs:
                all_docs.append({"category": category, **doc})

        context = IncidentContext(
            incident=incident,
            retrieved_documents=all_docs,
            historical_matches=rag_results.get("historical_incidents", []),
        )

        self.repository.log_audit(
            AuditEntry(
                incident_id=incident.id or "",
                agent_name="DataRAGAgent",
                action="investigation_complete",
                input_data={"service": incident.affected_service, "scenario": incident.scenario},
                output_data={
                    "similar_incidents": similar,
                    "runbooks": runbooks,
                    "documents_retrieved": len(all_docs),
                    "dependency_graph": incident.dependency_graph,
                },
            )
        )
        return context

    def _build_dependencies(self, incident: Incident) -> tuple[list[dict], dict[str, str]]:
        scenario = incident.scenario or ScenarioType.RANDOM
        if scenario in (
            ScenarioType.DEPENDENCY_CASCADE,
            ScenarioType.ALERT_STORM,
            ScenarioType.GRAY_FAILURE,
        ):
            graph = build_graph_for_scenario(scenario, incident.affected_service)
            return graph.to_dict_list(), graph.format_summary()

        deps = {
            "database": "Healthy" if incident.metrics.database_healthy else "Unhealthy",
            "container": incident.metrics.container_status,
            "network": f"{incident.metrics.network_latency_ms:.0f}ms latency",
        }
        return [], deps

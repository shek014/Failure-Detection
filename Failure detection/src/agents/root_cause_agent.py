"""Root Cause Analysis Agent."""

from __future__ import annotations

import json
import re

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq

from config.settings import get_settings
from src.database.store import IncidentRepository
from src.models.dependency_graph import DependencyGraph
from src.models.incident import AuditEntry, IncidentContext, RootCauseAnalysis
from src.monitoring.incident_simulator import SCENARIO_ROOT_CAUSES, ScenarioType


class RootCauseAgent:
    SYSTEM_PROMPT = """You are an expert Site Reliability Engineer performing root cause analysis.
Given incident context, determine the most likely root cause with confidence score (0-100).
Respond in JSON format:
{"root_cause": "...", "confidence": 85, "supporting_evidence": ["..."], "reasoning": "..."}
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
                temperature=0.1,
            )
        return self._llm

    def analyze(self, context: IncidentContext) -> RootCauseAnalysis:
        if self.llm:
            result = self._analyze_with_llm(context)
        else:
            result = self._analyze_rule_based(context)

        incident = context.incident
        incident.root_cause = result.root_cause
        incident.root_cause_confidence = result.confidence
        incident.supporting_evidence = result.supporting_evidence

        self.repository.log_audit(
            AuditEntry(
                incident_id=incident.id or "",
                agent_name="RootCauseAgent",
                action="rca_complete",
                input_data={"anomaly_type": incident.anomaly_type},
                output_data=result.model_dump(mode="json"),
            )
        )
        return result

    def _analyze_with_llm(self, context: IncidentContext) -> RootCauseAnalysis:
        try:
            response = self.llm.invoke(
                [
                    SystemMessage(content=self.SYSTEM_PROMPT),
                    HumanMessage(content=context.structured_summary),
                ]
            )
            return self._parse_llm_response(response.content)
        except Exception:
            return self._analyze_rule_based(context)

    def _analyze_rule_based(self, context: IncidentContext) -> RootCauseAnalysis:
        incident = context.incident
        evidence = list(incident.symptoms) + incident.logs[:3]

        if incident.scenario and incident.scenario in SCENARIO_ROOT_CAUSES:
            root = SCENARIO_ROOT_CAUSES[incident.scenario]
            if incident.dependency_graph and incident.scenario != ScenarioType.GRAY_FAILURE:
                graph = DependencyGraph.from_dict_list(incident.dependency_graph)
                leaf = graph.get_unhealthy_leaf()
                if leaf:
                    root = f"{leaf} Failure"
            elif incident.dependency_graph:
                graph = DependencyGraph.from_dict_list(incident.dependency_graph)
                leaf = graph.get_unhealthy_leaf()
                if leaf and leaf == "Network Switch":
                    root = SCENARIO_ROOT_CAUSES[ScenarioType.GRAY_FAILURE]
            return RootCauseAnalysis(
                root_cause=root,
                confidence=92.0,
                supporting_evidence=evidence,
                reasoning=f"Scenario-based RCA: {incident.scenario} -> {root}",
            )

        if incident.dependency_graph:
            graph = DependencyGraph.from_dict_list(incident.dependency_graph)
            leaf = graph.get_unhealthy_leaf()
            if leaf:
                return RootCauseAnalysis(
                    root_cause=f"{leaf} Failure",
                    confidence=88.0,
                    supporting_evidence=evidence,
                    reasoning=f"Dependency graph analysis: leaf unhealthy node = {leaf}",
                )

        rules = [
            ("Gray Failure" in incident.anomaly_type, "Packet Loss on Network Switch", 90),
            ("OutOfMemoryError" in " ".join(incident.logs), "Memory Leak", 91),
            ("connection pool" in " ".join(incident.logs).lower(), "Connection Pool Exhaustion", 88),
            ("redis" in " ".join(incident.logs).lower(), "Redis Cache Unavailable", 92),
            ("Alert Storm" in incident.anomaly_type, "Database Replica 3 Latency", 93),
            ("Dependency Cascade" in incident.anomaly_type, "Redis Cache Unavailable", 90),
            ("Service Down" in incident.anomaly_type, "Service Crash", 85),
            ("High CPU" in incident.anomaly_type, "CPU Bottleneck", 82),
            ("Latency" in incident.anomaly_type, "Downstream Dependency Failure", 78),
            ("Error Rate" in incident.anomaly_type, "Application Error Spike", 75),
            ("Database" in incident.anomaly_type, "Database Failure", 90),
        ]

        for condition, cause, confidence in rules:
            if condition:
                return RootCauseAnalysis(
                    root_cause=cause,
                    confidence=confidence,
                    supporting_evidence=evidence,
                    reasoning=f"Rule-based match: {incident.anomaly_type} -> {cause}",
                )

        return RootCauseAnalysis(
            root_cause="Unknown - Requires Investigation",
            confidence=30.0,
            supporting_evidence=evidence,
            reasoning="No clear pattern matched; manual investigation recommended",
        )

    def _parse_llm_response(self, content: str) -> RootCauseAnalysis:
        try:
            match = re.search(r"\{.*\}", content, re.DOTALL)
            if match:
                data = json.loads(match.group())
                return RootCauseAnalysis(**data)
        except (json.JSONDecodeError, ValueError):
            pass
        return RootCauseAnalysis(
            root_cause=content[:200],
            confidence=50.0,
            supporting_evidence=[],
            reasoning="LLM response could not be parsed as JSON",
        )

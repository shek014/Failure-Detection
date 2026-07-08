"""LangGraph orchestrator for the incident resolution workflow."""

from __future__ import annotations

from typing import Annotated, Literal, Optional, TypedDict

from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages

from src.agents.context_builder_agent import ContextBuilderAgent
from src.agents.data_rag_agent import DataRAGAgent
from src.agents.decision_agent import DecisionAgent
from src.agents.notification_agent import NotificationAgent
from src.agents.resolution_agent import ResolutionAgent
from src.agents.risk_assessment_agent import RiskAssessmentAgent
from src.agents.root_cause_agent import RootCauseAgent
from src.agents.verification_agent import VerificationAgent
from src.database.store import IncidentRepository
from src.feedback.learning_loop import FeedbackLearningLoop
from src.models.incident import (
    DecisionAction,
    Incident,
    IncidentContext,
    IncidentStatus,
    RootCauseAnalysis,
)


class WorkflowState(TypedDict):
    incident: Incident
    context: Optional[IncidentContext]
    rca: Optional[RootCauseAnalysis]
    human_approved: Optional[bool]
    retry_count: int
    messages: Annotated[list, add_messages]
    error: Optional[str]


class IncidentOrchestrator:
    MAX_RETRIES = 2

    def __init__(self, repository: IncidentRepository | None = None) -> None:
        self.repository = repository or IncidentRepository()
        self.data_rag = DataRAGAgent(self.repository)
        self.context_builder = ContextBuilderAgent(self.repository)
        self.root_cause = RootCauseAgent(self.repository)
        self.risk_assessment = RiskAssessmentAgent(self.repository)
        self.decision = DecisionAgent(self.repository)
        self.resolution = ResolutionAgent(self.repository)
        self.verification = VerificationAgent(self.repository)
        self.notification = NotificationAgent(self.repository)
        self.feedback = FeedbackLearningLoop(self.repository)
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        workflow = StateGraph(WorkflowState)

        workflow.add_node("investigate", self._investigate)
        workflow.add_node("build_context", self._build_context)
        workflow.add_node("analyze_root_cause", self._analyze_root_cause)
        workflow.add_node("assess_risk", self._assess_risk)
        workflow.add_node("make_decision", self._make_decision)
        workflow.add_node("await_approval", self._await_approval)
        workflow.add_node("resolve", self._resolve)
        workflow.add_node("verify", self._verify)
        workflow.add_node("notify", self._notify)
        workflow.add_node("feedback", self._feedback)
        workflow.add_node("escalate", self._escalate)

        workflow.set_entry_point("investigate")
        workflow.add_edge("investigate", "build_context")
        workflow.add_edge("build_context", "analyze_root_cause")
        workflow.add_edge("analyze_root_cause", "assess_risk")
        workflow.add_edge("assess_risk", "make_decision")

        workflow.add_conditional_edges(
            "make_decision",
            self._route_after_decision,
            {
                "auto": "resolve",
                "approval": "await_approval",
                "escalate": "escalate",
            },
        )

        workflow.add_conditional_edges(
            "await_approval",
            self._route_after_approval,
            {"approved": "resolve", "rejected": "escalate", "pending": END},
        )

        workflow.add_edge("resolve", "verify")

        workflow.add_conditional_edges(
            "verify",
            self._route_after_verification,
            {"pass": "notify", "retry": "resolve", "escalate": "escalate"},
        )

        workflow.add_edge("notify", "feedback")
        workflow.add_edge("feedback", END)
        workflow.add_edge("escalate", "notify")

        return workflow.compile()

    def run(self, incident: Incident, human_approved: Optional[bool] = None) -> Incident:
        incident.status = IncidentStatus.INVESTIGATING
        self.repository.update_incident(incident)

        initial_state: WorkflowState = {
            "incident": incident,
            "context": None,
            "rca": None,
            "human_approved": human_approved,
            "retry_count": 0,
            "messages": [],
            "error": None,
        }

        final_state = self.graph.invoke(initial_state)
        return final_state["incident"]

    def approve(self, incident_id: str, approved: bool = True) -> Incident:
        incident = self.repository.get_incident(incident_id)
        if not incident:
            raise ValueError(f"Incident {incident_id} not found")

        incident.human_approved = approved
        incident.status = IncidentStatus.RESOLVING if approved else IncidentStatus.ESCALATED
        self.repository.update_incident(incident)

        if approved:
            return self.run(incident, human_approved=True)
        return incident

    def _investigate(self, state: WorkflowState) -> dict:
        incident = state["incident"]
        context = self.data_rag.investigate(incident)
        return {"context": context, "incident": context.incident}

    def _build_context(self, state: WorkflowState) -> dict:
        context = self.context_builder.build(state["context"])
        return {"context": context, "incident": context.incident}

    def _analyze_root_cause(self, state: WorkflowState) -> dict:
        incident = state["incident"]
        incident.status = IncidentStatus.RCA_COMPLETE
        rca = self.root_cause.analyze(state["context"])
        self.repository.update_incident(incident)
        return {"rca": rca, "incident": incident}

    def _assess_risk(self, state: WorkflowState) -> dict:
        self.risk_assessment.assess(state["context"], state["rca"])
        return {"incident": state["incident"]}

    def _make_decision(self, state: WorkflowState) -> dict:
        from src.models.incident import RiskAssessment

        assessment_obj = RiskAssessment(
            risk_level=state["incident"].risk_level,
            recommended_action=state["incident"].remediation_action,
        )
        result = self.decision.decide(state["context"], assessment_obj)
        incident = state["incident"]

        if result.action == DecisionAction.REQUIRE_HUMAN_APPROVAL:
            incident.status = IncidentStatus.AWAITING_APPROVAL
        elif result.action == DecisionAction.IMMEDIATE_ESCALATION:
            incident.status = IncidentStatus.ESCALATED

        self.repository.update_incident(incident)
        return {"incident": incident}

    def _await_approval(self, state: WorkflowState) -> dict:
        approved = state.get("human_approved")
        incident = state["incident"]
        if approved is not None:
            incident.human_approved = approved
            self.repository.update_incident(incident)
        return {"incident": incident}

    def _resolve(self, state: WorkflowState) -> dict:
        incident = state["incident"]
        incident.status = IncidentStatus.RESOLVING
        approved = state.get("human_approved", True)
        if incident.decision_action == DecisionAction.AUTO_RESOLVE:
            approved = True
        elif incident.decision_action == DecisionAction.AUTO_RESOLVE_WITH_VERIFICATION:
            approved = True

        self.resolution.resolve(incident, approved=approved)
        self.repository.update_incident(incident)
        return {"incident": incident}

    def _verify(self, state: WorkflowState) -> dict:
        incident = state["incident"]
        incident.status = IncidentStatus.VERIFYING
        result = self.verification.verify(incident)
        if result.passed:
            incident.status = IncidentStatus.RESOLVED
        self.repository.update_incident(incident)
        retry = state.get("retry_count", 0)
        if not result.passed and result.should_retry and retry < self.MAX_RETRIES:
            return {"incident": incident, "retry_count": retry + 1}
        return {"incident": incident}

    def _notify(self, state: WorkflowState) -> dict:
        self.notification.generate_report(state["incident"])
        self.repository.update_incident(state["incident"])
        return {"incident": state["incident"]}

    def _feedback(self, state: WorkflowState) -> dict:
        self.feedback.record_outcome(
            state["incident"],
            human_override=state.get("human_approved") is not None,
        )
        return {"incident": state["incident"]}

    def _escalate(self, state: WorkflowState) -> dict:
        incident = state["incident"]
        incident.status = IncidentStatus.ESCALATED
        self.repository.update_incident(incident)
        return {"incident": incident}

    def _route_after_decision(self, state: WorkflowState) -> Literal["auto", "approval", "escalate"]:
        action = state["incident"].decision_action
        if action == DecisionAction.IMMEDIATE_ESCALATION:
            return "escalate"
        if action == DecisionAction.REQUIRE_HUMAN_APPROVAL:
            if state.get("human_approved") is True:
                return "auto"
            if state.get("human_approved") is False:
                return "escalate"
            return "approval"
        return "auto"

    def _route_after_approval(self, state: WorkflowState) -> Literal["approved", "rejected", "pending"]:
        approved = state.get("human_approved")
        if approved is True:
            return "approved"
        if approved is False:
            return "rejected"
        return "pending"

    def _route_after_verification(self, state: WorkflowState) -> Literal["pass", "retry", "escalate"]:
        incident = state["incident"]
        if incident.verification_passed:
            return "pass"
        if state.get("retry_count", 0) < self.MAX_RETRIES:
            return "retry"
        incident.status = IncidentStatus.ESCALATED
        self.repository.update_incident(incident)
        return "escalate"

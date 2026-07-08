"""Domain models for incident resolution workflow."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class IncidentStatus(str, Enum):
    DETECTED = "detected"
    INVESTIGATING = "investigating"
    RCA_COMPLETE = "rca_complete"
    AWAITING_APPROVAL = "awaiting_approval"
    RESOLVING = "resolving"
    VERIFYING = "verifying"
    RESOLVED = "resolved"
    ESCALATED = "escalated"
    FAILED = "failed"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class DecisionAction(str, Enum):
    AUTO_RESOLVE = "auto_resolve"
    AUTO_RESOLVE_WITH_VERIFICATION = "auto_resolve_with_verification"
    REQUIRE_HUMAN_APPROVAL = "require_human_approval"
    IMMEDIATE_ESCALATION = "immediate_escalation"


class RemediationAction(str, Enum):
    RESTART_SERVICE = "restart_service"
    CLEAR_CACHE = "clear_cache"
    SCALE_CONTAINERS = "scale_containers"
    ROLLBACK_DEPLOYMENT = "rollback_deployment"
    RECONNECT_DATABASE = "reconnect_database"
    RESTART_PODS = "restart_pods"
    NONE = "none"


class MetricSnapshot(BaseModel):
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    disk_percent: float = 0.0
    network_latency_ms: float = 0.0
    api_response_time_ms: float = 0.0
    error_rate_percent: float = 0.0
    service_healthy: bool = True
    container_status: str = "running"
    database_healthy: bool = True
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class DetectionResult(BaseModel):
    is_anomaly: bool
    anomaly_type: str = ""
    severity: Severity = Severity.LOW
    affected_service: str = ""
    metrics: MetricSnapshot = Field(default_factory=MetricSnapshot)
    deduplicated: bool = False
    message: str = ""
    scenario: str = ""
    is_gray_failure: bool = False
    degradation_signals: list[str] = Field(default_factory=list)


class Incident(BaseModel):
    id: Optional[str] = None
    severity: Severity
    affected_service: str
    anomaly_type: str
    status: IncidentStatus = IncidentStatus.DETECTED
    detection_timestamp: datetime = Field(default_factory=datetime.utcnow)
    metrics: MetricSnapshot = Field(default_factory=MetricSnapshot)
    symptoms: list[str] = Field(default_factory=list)
    logs: list[str] = Field(default_factory=list)
    similar_incidents: list[str] = Field(default_factory=list)
    runbook_refs: list[str] = Field(default_factory=list)
    dependencies: dict[str, str] = Field(default_factory=dict)
    dependency_graph: list[dict[str, Any]] = Field(default_factory=list)
    scenario: str = ""
    correlation_id: str = ""
    correlated_alert_count: int = 0
    root_cause: str = ""
    root_cause_confidence: float = 0.0
    supporting_evidence: list[str] = Field(default_factory=list)
    risk_level: RiskLevel = RiskLevel.MEDIUM
    decision_action: DecisionAction = DecisionAction.REQUIRE_HUMAN_APPROVAL
    remediation_action: RemediationAction = RemediationAction.NONE
    human_approved: Optional[bool] = None
    resolution_success: Optional[bool] = None
    verification_passed: Optional[bool] = None
    summary: str = ""
    resolution_report: str = ""


class IncidentContext(BaseModel):
    incident: Incident
    structured_summary: str = ""
    retrieved_documents: list[dict[str, Any]] = Field(default_factory=list)
    historical_matches: list[dict[str, Any]] = Field(default_factory=list)


class RootCauseAnalysis(BaseModel):
    root_cause: str
    confidence: float
    supporting_evidence: list[str] = Field(default_factory=list)
    reasoning: str = ""


class RiskAssessment(BaseModel):
    risk_level: RiskLevel
    recommended_action: RemediationAction
    rationale: str = ""
    requires_human: bool = False


class DecisionResult(BaseModel):
    action: DecisionAction
    rationale: str = ""
    auto_execute: bool = False


class ResolutionResult(BaseModel):
    action: RemediationAction
    success: bool
    message: str = ""
    execution_details: dict[str, Any] = Field(default_factory=dict)


class VerificationResult(BaseModel):
    passed: bool
    checks: dict[str, bool] = Field(default_factory=dict)
    message: str = ""
    should_retry: bool = False
    should_escalate: bool = False


class NotificationReport(BaseModel):
    incident_summary: str
    root_cause_report: str
    resolution_report: str
    stakeholder_message: str


class FeedbackRecord(BaseModel):
    incident_id: str
    outcome: str
    human_override: bool = False
    resolution_success: bool = False
    verification_passed: bool = False
    lessons_learned: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)


class AuditEntry(BaseModel):
    incident_id: str
    agent_name: str
    action: str
    input_data: dict[str, Any] = Field(default_factory=dict)
    output_data: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)

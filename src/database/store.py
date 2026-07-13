"""Repository layer for incidents, audit, and feedback."""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy.orm import Session

from src.database.repository import (
    AlertDedupRecord,
    AuditRecord,
    FeedbackRecordORM,
    IncidentRecord,
    get_session_factory,
    init_db,
)
from src.models.incident import (
    AuditEntry,
    FeedbackRecord,
    Incident,
    IncidentStatus,
    MetricSnapshot,
)


class IncidentRepository:
    def __init__(self) -> None:
        init_db()
        self._session_factory = get_session_factory()

    def _session(self) -> Session:
        return self._session_factory()

    def create_incident(self, incident: Incident) -> Incident:
        incident_id = incident.id or f"INC-{uuid.uuid4().hex[:8].upper()}"
        incident.id = incident_id
        extra_state = {
            "scenario": incident.scenario,
            "correlation_id": incident.correlation_id,
            "correlated_alert_count": incident.correlated_alert_count,
            "dependency_graph": incident.dependency_graph,
        }

        with self._session() as session:
            record = IncidentRecord(
                id=incident_id,
                severity=incident.severity.value,
                affected_service=incident.affected_service,
                anomaly_type=incident.anomaly_type,
                status=incident.status.value,
                detection_timestamp=incident.detection_timestamp,
                metrics=incident.metrics.model_dump(mode="json"),
                symptoms=incident.symptoms,
                logs=incident.logs,
                similar_incidents=incident.similar_incidents,
                runbook_refs=incident.runbook_refs,
                dependencies=incident.dependencies,
                root_cause=incident.root_cause,
                root_cause_confidence=incident.root_cause_confidence,
                supporting_evidence=incident.supporting_evidence,
                risk_level=incident.risk_level.value,
                decision_action=incident.decision_action.value,
                remediation_action=incident.remediation_action.value,
                human_approved=incident.human_approved,
                resolution_success=incident.resolution_success,
                verification_passed=incident.verification_passed,
                summary=incident.summary,
                resolution_report=incident.resolution_report,
                workflow_state=extra_state,
            )
            session.add(record)
            session.commit()
        return incident

    def update_incident(self, incident: Incident, workflow_state: Optional[dict] = None) -> Incident:
        with self._session() as session:
            record = session.get(IncidentRecord, incident.id)
            if not record:
                raise ValueError(f"Incident {incident.id} not found")

            record.status = incident.status.value
            record.symptoms = incident.symptoms
            record.logs = incident.logs
            record.similar_incidents = incident.similar_incidents
            record.runbook_refs = incident.runbook_refs
            record.dependencies = incident.dependencies
            record.root_cause = incident.root_cause
            record.root_cause_confidence = incident.root_cause_confidence
            record.supporting_evidence = incident.supporting_evidence
            record.risk_level = incident.risk_level.value
            record.decision_action = incident.decision_action.value
            record.remediation_action = incident.remediation_action.value
            record.human_approved = incident.human_approved
            record.resolution_success = incident.resolution_success
            record.verification_passed = incident.verification_passed
            record.summary = incident.summary
            record.resolution_report = incident.resolution_report
            record.metrics = incident.metrics.model_dump(mode="json")
            record.workflow_state = {
                **(record.workflow_state or {}),
                "scenario": incident.scenario,
                "correlation_id": incident.correlation_id,
                "correlated_alert_count": incident.correlated_alert_count,
                "dependency_graph": incident.dependency_graph,
            }
            if workflow_state is not None:
                record.workflow_state.update(workflow_state)
            record.updated_at = datetime.utcnow()
            session.commit()
        return incident

    def get_incident(self, incident_id: str) -> Optional[Incident]:
        with self._session() as session:
            record = session.get(IncidentRecord, incident_id)
            if not record:
                return None
            return self._to_incident(record)

    def list_incidents(self, limit: int = 50) -> list[Incident]:
        with self._session() as session:
            records = (
                session.query(IncidentRecord)
                .order_by(IncidentRecord.detection_timestamp.desc())
                .limit(limit)
                .all()
            )
            return [self._to_incident(r) for r in records]

    def _to_incident(self, record: IncidentRecord) -> Incident:
        from src.models.incident import (
            DecisionAction,
            RemediationAction,
            RiskLevel,
            Severity,
        )

        return Incident(
            id=record.id,
            severity=Severity(record.severity),
            affected_service=record.affected_service,
            anomaly_type=record.anomaly_type,
            status=IncidentStatus(record.status),
            detection_timestamp=record.detection_timestamp,
            metrics=MetricSnapshot(**record.metrics) if record.metrics else MetricSnapshot(),
            symptoms=record.symptoms or [],
            logs=record.logs or [],
            similar_incidents=record.similar_incidents or [],
            runbook_refs=record.runbook_refs or [],
            dependencies=record.dependencies or {},
            dependency_graph=(record.workflow_state or {}).get("dependency_graph", []),
            scenario=(record.workflow_state or {}).get("scenario", ""),
            correlation_id=(record.workflow_state or {}).get("correlation_id", ""),
            correlated_alert_count=(record.workflow_state or {}).get("correlated_alert_count", 0),
            root_cause=record.root_cause or "",
            root_cause_confidence=record.root_cause_confidence or 0.0,
            supporting_evidence=record.supporting_evidence or [],
            risk_level=RiskLevel(record.risk_level),
            decision_action=DecisionAction(record.decision_action),
            remediation_action=RemediationAction(record.remediation_action),
            human_approved=record.human_approved,
            resolution_success=record.resolution_success,
            verification_passed=record.verification_passed,
            summary=record.summary or "",
            resolution_report=record.resolution_report or "",
        )

    def log_audit(self, entry: AuditEntry) -> None:
        with self._session() as session:
            session.add(
                AuditRecord(
                    incident_id=entry.incident_id,
                    agent_name=entry.agent_name,
                    action=entry.action,
                    input_data=entry.input_data,
                    output_data=entry.output_data,
                    timestamp=entry.timestamp,
                )
            )
            session.commit()

    def get_audit_trail(self, incident_id: str) -> list[AuditEntry]:
        with self._session() as session:
            records = (
                session.query(AuditRecord)
                .filter(AuditRecord.incident_id == incident_id)
                .order_by(AuditRecord.timestamp.asc())
                .all()
            )
            return [
                AuditEntry(
                    incident_id=r.incident_id,
                    agent_name=r.agent_name,
                    action=r.action,
                    input_data=r.input_data or {},
                    output_data=r.output_data or {},
                    timestamp=r.timestamp,
                )
                for r in records
            ]

    def save_feedback(self, feedback: FeedbackRecord) -> None:
        with self._session() as session:
            session.add(
                FeedbackRecordORM(
                    incident_id=feedback.incident_id,
                    outcome=feedback.outcome,
                    human_override=feedback.human_override,
                    resolution_success=feedback.resolution_success,
                    verification_passed=feedback.verification_passed,
                    lessons_learned=feedback.lessons_learned,
                    created_at=feedback.created_at,
                )
            )
            session.commit()

    def get_feedback_history(self, limit: int = 100) -> list[FeedbackRecord]:
        with self._session() as session:
            records = (
                session.query(FeedbackRecordORM)
                .order_by(FeedbackRecordORM.created_at.desc())
                .limit(limit)
                .all()
            )
            return [
                FeedbackRecord(
                    incident_id=r.incident_id,
                    outcome=r.outcome,
                    human_override=r.human_override,
                    resolution_success=r.resolution_success,
                    verification_passed=r.verification_passed,
                    lessons_learned=r.lessons_learned or "",
                    created_at=r.created_at,
                )
                for r in records
            ]

    def check_dedup(self, service: str, anomaly_type: str, window_minutes: int = 15) -> Optional[str]:
        fingerprint = hashlib.sha256(f"{service}:{anomaly_type}".encode()).hexdigest()
        cutoff = datetime.utcnow() - timedelta(minutes=window_minutes)

        with self._session() as session:
            record = (
                session.query(AlertDedupRecord)
                .filter(
                    AlertDedupRecord.fingerprint == fingerprint,
                    AlertDedupRecord.last_seen >= cutoff,
                )
                .first()
            )
            if record:
                record.count += 1
                record.last_seen = datetime.utcnow()
                session.commit()
                return record.incident_id
        return None

    def register_dedup(self, service: str, anomaly_type: str, incident_id: str) -> None:
        fingerprint = hashlib.sha256(f"{service}:{anomaly_type}".encode()).hexdigest()
        with self._session() as session:
            existing = (
                session.query(AlertDedupRecord)
                .filter(AlertDedupRecord.fingerprint == fingerprint)
                .first()
            )
            if existing:
                existing.incident_id = incident_id
                existing.last_seen = datetime.utcnow()
                existing.count = 1
            else:
                session.add(
                    AlertDedupRecord(
                        fingerprint=fingerprint,
                        incident_id=incident_id,
                        last_seen=datetime.utcnow(),
                        count=1,
                    )
                )
            session.commit()

    def search_incidents(self, query: str, limit: int = 10) -> list[Incident]:
        with self._session() as session:
            pattern = f"%{query.lower()}%"
            records = (
                session.query(IncidentRecord)
                .filter(
                    (IncidentRecord.id.ilike(pattern))
                    | (IncidentRecord.affected_service.ilike(pattern))
                    | (IncidentRecord.anomaly_type.ilike(pattern))
                    | (IncidentRecord.root_cause.ilike(pattern))
                    | (IncidentRecord.summary.ilike(pattern))
                )
                .order_by(IncidentRecord.detection_timestamp.desc())
                .limit(limit)
                .all()
            )
            return [self._to_incident(r) for r in records]

    def get_workflow_state(self, incident_id: str) -> dict[str, Any]:
        with self._session() as session:
            record = session.get(IncidentRecord, incident_id)
            return record.workflow_state if record else {}

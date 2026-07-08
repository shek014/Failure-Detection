"""SQLAlchemy ORM models for persistence."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import JSON, Boolean, DateTime, Float, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from config.settings import get_settings


class Base(DeclarativeBase):
    pass


class IncidentRecord(Base):
    __tablename__ = "incidents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    severity: Mapped[str] = mapped_column(String(32))
    affected_service: Mapped[str] = mapped_column(String(128))
    anomaly_type: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(64), default="detected")
    detection_timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    symptoms: Mapped[list] = mapped_column(JSON, default=list)
    logs: Mapped[list] = mapped_column(JSON, default=list)
    similar_incidents: Mapped[list] = mapped_column(JSON, default=list)
    runbook_refs: Mapped[list] = mapped_column(JSON, default=list)
    dependencies: Mapped[dict] = mapped_column(JSON, default=dict)
    root_cause: Mapped[str] = mapped_column(Text, default="")
    root_cause_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    supporting_evidence: Mapped[list] = mapped_column(JSON, default=list)
    risk_level: Mapped[str] = mapped_column(String(32), default="medium")
    decision_action: Mapped[str] = mapped_column(String(64), default="require_human_approval")
    remediation_action: Mapped[str] = mapped_column(String(64), default="none")
    human_approved: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    resolution_success: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    verification_passed: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    resolution_report: Mapped[str] = mapped_column(Text, default="")
    workflow_state: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class AuditRecord(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    incident_id: Mapped[str] = mapped_column(String(64), index=True)
    agent_name: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(128))
    input_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    output_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class FeedbackRecordORM(Base):
    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    incident_id: Mapped[str] = mapped_column(String(64), index=True)
    outcome: Mapped[str] = mapped_column(String(64))
    human_override: Mapped[bool] = mapped_column(Boolean, default=False)
    resolution_success: Mapped[bool] = mapped_column(Boolean, default=False)
    verification_passed: Mapped[bool] = mapped_column(Boolean, default=False)
    lessons_learned: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AlertDedupRecord(Base):
    __tablename__ = "alert_dedup"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    fingerprint: Mapped[str] = mapped_column(String(256), unique=True, index=True)
    incident_id: Mapped[str] = mapped_column(String(64))
    last_seen: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    count: Mapped[int] = mapped_column(default=1)


_engine = None
_SessionLocal = None


def get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        db_path = settings.data_dir / "incidents.db"
        url = f"sqlite:///{db_path}"
        _engine = create_engine(url, echo=False)
    return _engine


def get_session_factory():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), autoflush=False, autocommit=False)
    return _SessionLocal


def init_db() -> None:
    engine = get_engine()
    Base.metadata.create_all(engine)

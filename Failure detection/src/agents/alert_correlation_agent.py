"""Alert correlation agent: groups alert storms into root incidents."""

from __future__ import annotations

from src.database.store import IncidentRepository
from src.models.incident import AuditEntry, DetectionResult, Incident, Severity
from src.monitoring.incident_simulator import ScenarioType, get_simulator


class AlertCorrelationAgent:
    """Correlates burst alerts into a single root incident."""

    def __init__(self, repository: IncidentRepository | None = None) -> None:
        self.repository = repository or IncidentRepository()
        self.simulator = get_simulator()

    def correlate(self, detection: DetectionResult, incident: Incident | None = None) -> Incident:
        """Attach correlation metadata and collapse alert storm into root incident."""
        scenario = self.simulator.get_scenario()
        alerts = self.simulator.generate_alert_burst(detection.affected_service)

        if scenario != ScenarioType.ALERT_STORM or not alerts:
            if incident:
                incident.scenario = scenario
            return incident or Incident(
                severity=detection.severity,
                affected_service=detection.affected_service,
                anomaly_type=detection.anomaly_type,
                scenario=scenario,
            )

        correlation_id = alerts[0]["correlation_id"]
        root_hint = alerts[0]["root_cause_hint"]
        alert_count = len(alerts)

        if incident is None:
            incident = Incident(
                severity=Severity.HIGH,
                affected_service=detection.affected_service or "PostgreSQL",
                anomaly_type="Alert Storm — Database Replica Latency",
                scenario=ScenarioType.ALERT_STORM,
            )
        else:
            incident.anomaly_type = "Alert Storm — Database Replica Latency"
            incident.severity = Severity.HIGH

        incident.correlation_id = correlation_id
        incident.correlated_alert_count = alert_count
        incident.scenario = ScenarioType.ALERT_STORM
        incident.symptoms.append(f"Correlated alerts: {alert_count}")
        incident.symptoms.append(f"Root cause hint: {root_hint}")
        incident.logs.append(
            f"[CRITICAL] AlertCorrelation: {alert_count} alerts grouped under {correlation_id}"
        )
        incident.logs.append(
            f"[INFO] AlertCorrelation: Root incident — {root_hint}"
        )

        self.repository.log_audit(
            AuditEntry(
                incident_id=incident.id or "",
                agent_name="AlertCorrelationAgent",
                action="alerts_correlated",
                input_data={"alert_count": alert_count, "correlation_id": correlation_id},
                output_data={
                    "root_incident": incident.affected_service,
                    "generated_alerts": alert_count,
                    "real_root_cause": root_hint,
                    "sample_alerts": alerts[:5],
                },
            )
        )
        return incident

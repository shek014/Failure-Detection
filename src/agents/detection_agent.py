"""Detection Agent: anomaly detection, deduplication, and incident creation."""

from __future__ import annotations

from config.settings import get_settings
from src.agents.alert_correlation_agent import AlertCorrelationAgent
from src.database.store import IncidentRepository
from src.models.incident import (
    AuditEntry,
    DetectionResult,
    Incident,
    IncidentStatus,
    MetricSnapshot,
    Severity,
)
from src.monitoring.incident_simulator import ScenarioType, get_simulator
from src.monitoring.prometheus_client import MetricsCollector


class DetectionAgent:
    GRAY_LATENCY_MS = 200.0
    GRAY_ERROR_RATE = 1.0

    def __init__(
        self,
        repository: IncidentRepository | None = None,
        scenario: str | None = None,
    ) -> None:
        self.settings = get_settings()
        self.repository = repository or IncidentRepository()
        self.scenario = scenario or self.settings.active_scenario
        self.metrics_collector = MetricsCollector(
            simulate=self.settings.simulate_metrics,
            scenario=self.scenario if self.scenario != "random" else None,
        )
        self.correlation_agent = AlertCorrelationAgent(self.repository)
        self.simulator = get_simulator()

    def evaluate(self, service: str | None = None) -> DetectionResult:
        if self.scenario and self.scenario != "random":
            self.metrics_collector.set_scenario(self.scenario, service or "")
        else:
            self.simulator.state.remediated = False
            self.simulator.state._metrics_override = None

        metrics = self.metrics_collector.collect(service)
        anomalies = self._detect_anomalies(metrics)
        gray_signals = self._detect_gray_failure(metrics)
        scenario = self.simulator.get_scenario()

        if gray_signals and not anomalies:
            anomalies.append(
                {
                    "type": "Gray Failure — Intermittent Degradation",
                    "severity": Severity.MEDIUM,
                    "value": metrics.api_response_time_ms,
                }
            )

        if not anomalies:
            return DetectionResult(
                is_anomaly=False,
                metrics=metrics,
                scenario=scenario,
                message="All metrics within thresholds",
            )

        primary = max(anomalies, key=lambda a: self._severity_weight(a["severity"]))
        affected = service or self._default_service_for_scenario(scenario)

        existing_id = self.repository.check_dedup(affected, primary["type"])
        if existing_id:
            return DetectionResult(
                is_anomaly=True,
                anomaly_type=primary["type"],
                severity=primary["severity"],
                affected_service=affected,
                metrics=metrics,
                deduplicated=True,
                scenario=scenario,
                is_gray_failure=bool(gray_signals),
                degradation_signals=gray_signals,
                message=f"Deduplicated to existing incident {existing_id}",
            )

        return DetectionResult(
            is_anomaly=True,
            anomaly_type=primary["type"],
            severity=primary["severity"],
            affected_service=affected,
            metrics=metrics,
            scenario=scenario,
            is_gray_failure=bool(gray_signals) or scenario == ScenarioType.GRAY_FAILURE,
            degradation_signals=gray_signals,
            message=f"Anomaly detected: {primary['type']}",
        )

    def create_incident(self, detection: DetectionResult) -> Incident | None:
        if not detection.is_anomaly or detection.deduplicated:
            return None

        symptoms = self._build_symptoms(detection.metrics, detection.degradation_signals)
        logs = self.metrics_collector.get_service_logs(
            detection.affected_service, detection.anomaly_type
        )

        incident = Incident(
            severity=detection.severity,
            affected_service=detection.affected_service,
            anomaly_type=detection.anomaly_type,
            status=IncidentStatus.DETECTED,
            metrics=detection.metrics,
            symptoms=symptoms,
            logs=logs,
            scenario=detection.scenario,
        )

        incident = self.correlation_agent.correlate(detection, incident)
        incident = self.repository.create_incident(incident)
        self.repository.register_dedup(
            detection.affected_service, detection.anomaly_type, incident.id or ""
        )

        self.repository.log_audit(
            AuditEntry(
                incident_id=incident.id or "",
                agent_name="DetectionAgent",
                action="incident_created",
                input_data=detection.model_dump(mode="json"),
                output_data={
                    "incident_id": incident.id,
                    "is_gray_failure": detection.is_gray_failure,
                    "correlated_alerts": incident.correlated_alert_count,
                },
            )
        )
        return incident

    def _detect_anomalies(self, metrics: MetricSnapshot) -> list[dict]:
        anomalies = []
        s = self.settings

        if metrics.cpu_percent > s.cpu_threshold:
            anomalies.append({"type": "High CPU Usage", "severity": Severity.HIGH, "value": metrics.cpu_percent})
        if metrics.memory_percent > s.memory_threshold:
            anomalies.append({"type": "Memory Leak", "severity": Severity.HIGH, "value": metrics.memory_percent})
        if metrics.error_rate_percent > s.error_rate_threshold:
            anomalies.append({"type": "High Error Rate", "severity": Severity.MEDIUM, "value": metrics.error_rate_percent})
        if metrics.api_response_time_ms > s.latency_threshold_ms:
            anomalies.append({"type": "API Latency Spike", "severity": Severity.MEDIUM, "value": metrics.api_response_time_ms})
        if not metrics.service_healthy:
            anomalies.append({"type": "Service Down", "severity": Severity.CRITICAL, "value": 0})
        if not metrics.database_healthy:
            anomalies.append({"type": "Database Unhealthy", "severity": Severity.CRITICAL, "value": 0})

        scenario = self.simulator.get_scenario()
        if scenario == ScenarioType.DEPENDENCY_CASCADE:
            anomalies.append(
                {
                    "type": "Dependency Cascade — Upstream Failure",
                    "severity": Severity.HIGH,
                    "value": metrics.api_response_time_ms,
                }
            )
        if scenario == ScenarioType.ALERT_STORM:
            anomalies.append(
                {
                    "type": "Alert Storm — Database Replica Latency",
                    "severity": Severity.HIGH,
                    "value": metrics.api_response_time_ms,
                }
            )

        return anomalies

    def _detect_gray_failure(self, metrics: MetricSnapshot) -> list[str]:
        """Detect hidden degradation when health checks still pass."""
        signals = []
        if metrics.service_healthy and metrics.container_status == "running":
            if metrics.api_response_time_ms >= self.GRAY_LATENCY_MS:
                signals.append(f"Latency creep: {metrics.api_response_time_ms:.0f}ms (health check PASS)")
            if metrics.network_latency_ms >= 100:
                signals.append(f"Network latency elevated: {metrics.network_latency_ms:.0f}ms")
            if metrics.error_rate_percent >= self.GRAY_ERROR_RATE:
                signals.append(f"Error rate creeping: {metrics.error_rate_percent:.1f}%")
            if (
                metrics.cpu_percent < self.settings.cpu_threshold
                and metrics.memory_percent < self.settings.memory_threshold
                and signals
            ):
                signals.append("CPU/memory normal — hidden degradation pattern")
        return signals

    def _build_symptoms(
        self, metrics: MetricSnapshot, degradation_signals: list[str] | None = None
    ) -> list[str]:
        symptoms = []
        if metrics.cpu_percent > self.settings.cpu_threshold:
            symptoms.append(f"CPU: {metrics.cpu_percent:.1f}%")
        if metrics.memory_percent > self.settings.memory_threshold:
            symptoms.append(f"Memory: {metrics.memory_percent:.1f}%")
        if metrics.error_rate_percent > self.settings.error_rate_threshold:
            symptoms.append(f"Error Rate: {metrics.error_rate_percent:.1f}%")
        if metrics.api_response_time_ms > self.settings.latency_threshold_ms:
            symptoms.append(f"API Latency: {metrics.api_response_time_ms:.0f}ms")
        if not metrics.service_healthy:
            symptoms.append("Service: DOWN")
        if not metrics.database_healthy:
            symptoms.append("Database: UNHEALTHY")
        if degradation_signals:
            symptoms.extend(degradation_signals)
        return symptoms

    @staticmethod
    def _default_service_for_scenario(scenario: str) -> str:
        defaults = {
            ScenarioType.GRAY_FAILURE: "User API",
            ScenarioType.DEPENDENCY_CASCADE: "Frontend",
            ScenarioType.ALERT_STORM: "Frontend",
        }
        return defaults.get(scenario, MetricsCollector.SERVICES[0])

    @staticmethod
    def _severity_weight(severity: Severity) -> int:
        weights = {Severity.CRITICAL: 4, Severity.HIGH: 3, Severity.MEDIUM: 2, Severity.LOW: 1, Severity.INFO: 0}
        return weights.get(severity, 0)

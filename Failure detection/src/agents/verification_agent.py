"""Verification Agent: confirms recovery after remediation."""

from __future__ import annotations

from config.settings import get_settings
from src.database.store import IncidentRepository
from src.models.incident import AuditEntry, Incident, VerificationResult
from src.monitoring.prometheus_client import MetricsCollector


class VerificationAgent:
    def __init__(self, repository: IncidentRepository | None = None) -> None:
        self.settings = get_settings()
        self.repository = repository or IncidentRepository()
        self.metrics_collector = MetricsCollector(simulate=self.settings.simulate_metrics)

    def verify(self, incident: Incident, post_remediation: bool = True) -> VerificationResult:
        metrics = self.metrics_collector.collect(incident.affected_service)

        checks = {
            "service_healthy": metrics.service_healthy,
            "cpu_normalized": metrics.cpu_percent < self.settings.cpu_threshold,
            "memory_stable": metrics.memory_percent < self.settings.memory_threshold,
            "error_rate_reduced": metrics.error_rate_percent < self.settings.error_rate_threshold,
            "latency_recovered": metrics.api_response_time_ms < self.settings.latency_threshold_ms,
        }

        if post_remediation and incident.scenario in ("gray_failure", "dependency_cascade", "alert_storm"):
            checks["latency_recovered"] = metrics.api_response_time_ms < 500

        passed = all(checks.values())
        incident.verification_passed = passed
        incident.metrics = metrics

        result = VerificationResult(
            passed=passed,
            checks=checks,
            message=(
                f"All verification checks passed — latency recovered to {metrics.api_response_time_ms:.0f}ms"
                if passed
                else f"Verification failed — latency still {metrics.api_response_time_ms:.0f}ms"
            ),
            should_retry=not passed and incident.remediation_action.value != "none",
            should_escalate=not passed,
        )

        self.repository.log_audit(
            AuditEntry(
                incident_id=incident.id or "",
                agent_name="VerificationAgent",
                action="verification_complete",
                input_data={"post_remediation": post_remediation, "scenario": incident.scenario},
                output_data={
                    **result.model_dump(mode="json"),
                    "metrics_after": metrics.model_dump(mode="json"),
                },
            )
        )
        return result

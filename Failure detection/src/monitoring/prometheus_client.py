"""Prometheus metrics collection and simulated monitoring."""

from __future__ import annotations

from typing import Optional

import requests

from config.settings import get_settings
from src.models.incident import MetricSnapshot
from src.monitoring.incident_simulator import IncidentSimulator, ScenarioType, get_simulator


class MetricsCollector:
    """Collects metrics from Prometheus or simulates them for demo."""

    SERVICES = [
        "User API",
        "Payment API",
        "Order Service",
        "Auth Service",
        "Notification Service",
        "Frontend",
        "Inventory Service",
    ]

    def __init__(self, simulate: bool | None = None, scenario: str | None = None) -> None:
        self.settings = get_settings()
        if simulate is None:
            simulate = self.settings.simulate_metrics
        self.simulate = simulate
        self.simulator: IncidentSimulator = get_simulator()
        if scenario:
            self.simulator.set_scenario(scenario)

    def set_scenario(self, scenario: str, service: str = "") -> None:
        self.simulator.set_scenario(scenario, service)

    def collect(self, service: Optional[str] = None) -> MetricSnapshot:
        if self.simulate or not self._prometheus_available():
            return self.simulator.generate_metrics(service)
        return self._fetch_from_prometheus(service)

    def _prometheus_available(self) -> bool:
        try:
            resp = requests.get(f"{self.settings.prometheus_url}/-/healthy", timeout=2)
            return resp.status_code == 200
        except requests.RequestException:
            return False

    def _fetch_from_prometheus(self, service: Optional[str] = None) -> MetricSnapshot:
        base_url = self.settings.prometheus_url
        service_filter = f'{{service="{service}"}}' if service else ""

        def query(metric: str, default: float = 0.0) -> float:
            try:
                resp = requests.get(
                    f"{base_url}/api/v1/query",
                    params={"query": f"{metric}{service_filter}"},
                    timeout=5,
                )
                data = resp.json()
                if data.get("status") == "success" and data["data"]["result"]:
                    return float(data["data"]["result"][0]["value"][1])
            except (requests.RequestException, KeyError, ValueError, IndexError):
                pass
            return default

        return MetricSnapshot(
            cpu_percent=query("cpu_usage_percent", 0),
            memory_percent=query("memory_usage_percent", 0),
            disk_percent=query("disk_usage_percent", 0),
            network_latency_ms=query("network_latency_ms", 0),
            api_response_time_ms=query("http_request_duration_ms", 0),
            error_rate_percent=query("error_rate_percent", 0),
            service_healthy=query("up", 1) == 1,
            container_status="running" if query("up", 1) == 1 else "down",
            database_healthy=query("db_up", 1) == 1,
        )

    def get_service_logs(self, service: str, anomaly_hint: str = "") -> list[str]:
        return self.simulator.get_logs(service, anomaly_hint)

    @staticmethod
    def available_scenarios() -> list[str]:
        return [s.value for s in ScenarioType]

"""Deterministic incident simulator for demo and scenario-based testing."""

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from src.models.dependency_graph import build_graph_for_scenario
from src.models.incident import MetricSnapshot, RemediationAction


class ScenarioType(str, Enum):
    RANDOM = "random"
    NORMAL = "normal"
    CPU_SPIKE = "cpu_spike"
    MEMORY_LEAK = "memory_leak"
    LATENCY = "latency"
    SERVICE_DOWN = "service_down"
    GRAY_FAILURE = "gray_failure"
    DEPENDENCY_CASCADE = "dependency_cascade"
    ALERT_STORM = "alert_storm"

    @classmethod
    def deterministic(cls) -> list[str]:
        return [cls.GRAY_FAILURE, cls.DEPENDENCY_CASCADE, cls.ALERT_STORM]


DETERMINISTIC_SCENARIOS = ScenarioType.deterministic()

SCENARIO_ROOT_CAUSES: dict[str, str] = {
    ScenarioType.GRAY_FAILURE: "Packet Loss on Network Switch",
    ScenarioType.DEPENDENCY_CASCADE: "Redis Cache Unavailable",
    ScenarioType.ALERT_STORM: "Database Replica 3 Latency",
}

ALERT_STORM_SERVICES = [
    "Frontend",
    "User API",
    "Payment API",
    "Order Service",
    "Inventory Service",
    "Auth Service",
    "Notification Service",
    "API Gateway",
    "PostgreSQL",
    "Redis",
    "Kafka",
]

ALERT_STORM_ANOMALIES = [
    "API Latency Spike",
    "High Error Rate",
    "Database Slow",
    "Queue Backlog",
    "Redis Timeout",
    "Connection Timeout",
    "High CPU Usage",
]


@dataclass
class SimulatorState:
    active_scenario: str = ScenarioType.RANDOM
    remediated: bool = False
    correlation_id: str = ""
    alert_count: int = 0
    affected_service: str = ""
    _metrics_override: Optional[dict] = field(default=None, repr=False)

    def reset(self, scenario: str = ScenarioType.RANDOM, service: str = "") -> None:
        self.active_scenario = scenario
        self.remediated = False
        self.correlation_id = ""
        self.alert_count = 0
        self.affected_service = service
        self._metrics_override = None


class IncidentSimulator:
    """Singleton simulator managing scenario state and metric generation."""

    _instance: Optional[IncidentSimulator] = None

    def __new__(cls) -> IncidentSimulator:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.state = SimulatorState()
        return cls._instance

    def set_scenario(self, scenario: str, service: str = "") -> None:
        self.state.reset(scenario, service)
        if scenario == ScenarioType.ALERT_STORM:
            self.state.correlation_id = f"CORR-{uuid.uuid4().hex[:8].upper()}"
            self.state.alert_count = 47

    def get_scenario(self) -> str:
        return self.state.active_scenario

    def apply_remediation(self, action: RemediationAction, service: str) -> None:
        self.state.remediated = True
        self.state._metrics_override = {
            "cpu_percent": 42.0,
            "memory_percent": 55.0,
            "disk_percent": 60.0,
            "network_latency_ms": 25.0,
            "api_response_time_ms": 35.0,
            "error_rate_percent": 0.3,
            "service_healthy": True,
            "container_status": "running",
            "database_healthy": True,
        }
        if self.state.active_scenario == ScenarioType.ALERT_STORM:
            self.state.alert_count = 0

    def generate_metrics(self, service: Optional[str] = None) -> MetricSnapshot:
        if self.state.remediated and self.state._metrics_override:
            return MetricSnapshot(**self.state._metrics_override)

        scenario = self._resolve_scenario()
        svc = service or self.state.affected_service or "User API"
        self.state.affected_service = svc

        generators = {
            ScenarioType.NORMAL: self._metrics_normal,
            ScenarioType.CPU_SPIKE: self._metrics_cpu_spike,
            ScenarioType.MEMORY_LEAK: self._metrics_memory_leak,
            ScenarioType.LATENCY: self._metrics_latency,
            ScenarioType.SERVICE_DOWN: self._metrics_service_down,
            ScenarioType.GRAY_FAILURE: self._metrics_gray_failure,
            ScenarioType.DEPENDENCY_CASCADE: self._metrics_dependency_cascade,
            ScenarioType.ALERT_STORM: self._metrics_alert_storm,
        }

        generator = generators.get(scenario, self._metrics_random)
        return generator(svc)

    def generate_alert_burst(self, service: Optional[str] = None) -> list[dict]:
        """Generate correlated alerts for alert_storm scenario."""
        if self.state.active_scenario != ScenarioType.ALERT_STORM:
            return []

        if not self.state.correlation_id:
            self.state.correlation_id = f"CORR-{uuid.uuid4().hex[:8].upper()}"

        svc = service or "Frontend"
        self.state.affected_service = svc
        count = self.state.alert_count or 47
        alerts = []

        for i in range(count):
            target = ALERT_STORM_SERVICES[i % len(ALERT_STORM_SERVICES)]
            anomaly = ALERT_STORM_ANOMALIES[i % len(ALERT_STORM_ANOMALIES)]
            alerts.append(
                {
                    "alert_id": f"ALT-{i + 1:04d}",
                    "service": target,
                    "anomaly_type": anomaly,
                    "correlation_id": self.state.correlation_id,
                    "root_cause_hint": SCENARIO_ROOT_CAUSES[ScenarioType.ALERT_STORM],
                    "severity": "high" if i < 5 else "medium",
                }
            )
        return alerts

    def get_logs(self, service: str, anomaly_hint: str = "") -> list[str]:
        scenario = self._resolve_scenario()
        templates = {
            ScenarioType.CPU_SPIKE: [
                f"[ERROR] {service}: Thread pool exhausted, rejecting tasks",
                f"[WARN] {service}: CPU throttling active",
            ],
            ScenarioType.MEMORY_LEAK: [
                f"[ERROR] {service}: java.lang.OutOfMemoryError: Java heap space",
                f"[WARN] {service}: GC overhead limit exceeded",
            ],
            ScenarioType.LATENCY: [
                f"[WARN] {service}: Database connection pool exhausted (max=50, active=50)",
                f"[ERROR] {service}: Request timeout after 5000ms",
            ],
            ScenarioType.SERVICE_DOWN: [
                f"[FATAL] {service}: Health check failed - process not responding",
                f"[ERROR] {service}: Container exited with code 137 (OOMKilled)",
            ],
            ScenarioType.GRAY_FAILURE: [
                f"[WARN] {service}: Intermittent request timeout (250ms p99, health check PASS)",
                f"[WARN] {service}: Packet loss detected on upstream network path (0.8%)",
                f"[INFO] {service}: Health check endpoint responding 200 OK",
                f"[WARN] {service}: Database replica 3 latency elevated (220ms)",
            ],
            ScenarioType.DEPENDENCY_CASCADE: [
                f"[ERROR] {service}: Upstream Redis timeout after 3000ms",
                f"[WARN] {service}: Auth Service degraded — cache miss rate 94%",
                f"[ERROR] {service}: Login request timeout — Redis connection refused",
                f"[INFO] {service}: Frontend health check PASS (symptom service healthy)",
            ],
            ScenarioType.ALERT_STORM: [
                f"[ERROR] {service}: Database replica 3 read latency 4200ms",
                f"[WARN] {service}: Connection pool wait time exceeded threshold",
                f"[ERROR] {service}: Cascading timeout to dependent services",
                f"[WARN] {service}: {self.state.alert_count} correlated alerts in burst",
            ],
        }

        if scenario in templates:
            return templates[scenario]

        for key, logs in templates.items():
            if key in anomaly_hint.lower() or key.replace("_", " ") in anomaly_hint.lower():
                return logs
        return [f"[INFO] {service}: Normal operation", f"[DEBUG] {service}: Request processed in 45ms"]

    def get_expected_root_cause(self) -> str:
        return SCENARIO_ROOT_CAUSES.get(self.state.active_scenario, "")

    def _resolve_scenario(self) -> str:
        if self.state.active_scenario != ScenarioType.RANDOM:
            return self.state.active_scenario
        return random.choice(
            ["normal", "normal", "normal", "cpu_spike", "memory_leak", "latency", "service_down"]
        )

    def _metrics_normal(self, service: str) -> MetricSnapshot:
        return MetricSnapshot(
            cpu_percent=random.uniform(20, 60),
            memory_percent=random.uniform(30, 70),
            disk_percent=random.uniform(40, 75),
            network_latency_ms=random.uniform(10, 80),
            api_response_time_ms=random.uniform(50, 150),
            error_rate_percent=random.uniform(0, 0.5),
            service_healthy=True,
            container_status="running",
            database_healthy=True,
        )

    def _metrics_random(self, service: str) -> MetricSnapshot:
        scenario = random.choice(
            ["cpu_spike", "memory_leak", "latency", "service_down", "normal", "normal"]
        )
        return getattr(self, f"_metrics_{scenario}")(service)

    def _metrics_cpu_spike(self, service: str) -> MetricSnapshot:
        return MetricSnapshot(
            cpu_percent=random.uniform(96, 99),
            memory_percent=random.uniform(40, 70),
            disk_percent=random.uniform(40, 75),
            network_latency_ms=random.uniform(10, 100),
            api_response_time_ms=random.uniform(200, 800),
            error_rate_percent=random.uniform(2, 8),
            service_healthy=True,
            container_status="running",
            database_healthy=True,
        )

    def _metrics_memory_leak(self, service: str) -> MetricSnapshot:
        return MetricSnapshot(
            cpu_percent=random.uniform(30, 60),
            memory_percent=random.uniform(91, 98),
            disk_percent=random.uniform(40, 75),
            network_latency_ms=random.uniform(10, 100),
            api_response_time_ms=random.uniform(100, 500),
            error_rate_percent=random.uniform(3, 10),
            service_healthy=True,
            container_status="running",
            database_healthy=True,
        )

    def _metrics_latency(self, service: str) -> MetricSnapshot:
        return MetricSnapshot(
            cpu_percent=random.uniform(30, 60),
            memory_percent=random.uniform(30, 70),
            disk_percent=random.uniform(40, 75),
            network_latency_ms=random.uniform(200, 800),
            api_response_time_ms=random.uniform(2500, 5000),
            error_rate_percent=random.uniform(1, 4),
            service_healthy=True,
            container_status="running",
            database_healthy=True,
        )

    def _metrics_service_down(self, service: str) -> MetricSnapshot:
        return MetricSnapshot(
            cpu_percent=0,
            memory_percent=0,
            disk_percent=random.uniform(40, 75),
            network_latency_ms=0,
            api_response_time_ms=0,
            error_rate_percent=random.uniform(50, 100),
            service_healthy=False,
            container_status="crashed",
            database_healthy=True,
        )

    def _metrics_gray_failure(self, service: str) -> MetricSnapshot:
        """Service appears healthy but performance is degraded."""
        return MetricSnapshot(
            cpu_percent=random.uniform(40, 55),
            memory_percent=random.uniform(48, 58),
            disk_percent=random.uniform(50, 70),
            network_latency_ms=random.uniform(150, 280),
            api_response_time_ms=random.uniform(220, 350),
            error_rate_percent=random.uniform(1.5, 3.5),
            service_healthy=True,
            container_status="running",
            database_healthy=True,
        )

    def _metrics_dependency_cascade(self, service: str) -> MetricSnapshot:
        graph = build_graph_for_scenario(ScenarioType.DEPENDENCY_CASCADE, service)
        node = next((n for n in graph.nodes if n.name == service), None)
        if not node:
            node = next((n for n in graph.nodes if n.name == "User API"), graph.nodes[0])

        return MetricSnapshot(
            cpu_percent=random.uniform(35, 55),
            memory_percent=random.uniform(40, 60),
            disk_percent=random.uniform(45, 70),
            network_latency_ms=node.latency_ms * 0.3,
            api_response_time_ms=node.latency_ms,
            error_rate_percent=node.error_rate_percent,
            service_healthy=node.status != "unhealthy",
            container_status="running",
            database_healthy=True,
        )

    def _metrics_alert_storm(self, service: str) -> MetricSnapshot:
        return MetricSnapshot(
            cpu_percent=random.uniform(55, 75),
            memory_percent=random.uniform(60, 80),
            disk_percent=random.uniform(50, 75),
            network_latency_ms=random.uniform(100, 300),
            api_response_time_ms=random.uniform(2800, 4200),
            error_rate_percent=random.uniform(6, 12),
            service_healthy=True,
            container_status="running",
            database_healthy=False,
        )


def get_simulator() -> IncidentSimulator:
    return IncidentSimulator()

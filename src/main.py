"""Main entry point for the incident resolution platform."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.agents.detection_agent import DetectionAgent
from src.database.repository import init_db
from src.monitoring.incident_simulator import DETERMINISTIC_SCENARIOS, ScenarioType
from src.monitoring.prometheus_client import MetricsCollector
from src.orchestration.langgraph_orchestrator import IncidentOrchestrator
from scripts.seed_knowledge_base import seed_knowledge_base


def run_detection_pipeline(service: str | None = None, scenario: str = "random") -> None:
    init_db()
    seed_knowledge_base()

    detection_agent = DetectionAgent(scenario=scenario)
    detection = detection_agent.evaluate(service)

    if not detection.is_anomaly:
        print(f"No anomaly detected. {detection.message}")
        if scenario != "random":
            print(f"  Scenario: {scenario}")
        return

    if detection.deduplicated:
        print(f"Deduplicated: {detection.message}")
        return

    incident = detection_agent.create_incident(detection)
    if not incident:
        print("Failed to create incident.")
        return

    print(f"Incident created: {incident.id}")
    print(f"  Service: {incident.affected_service}")
    print(f"  Anomaly: {incident.anomaly_type}")
    print(f"  Severity: {incident.severity.value}")
    if incident.scenario:
        print(f"  Scenario: {incident.scenario}")
    if detection.is_gray_failure:
        print(f"  Gray failure signals: {', '.join(detection.degradation_signals)}")
    if incident.correlated_alert_count:
        print(f"  Correlated alerts: {incident.correlated_alert_count} -> 1 root incident")

    orchestrator = IncidentOrchestrator()
    result = orchestrator.run(incident)

    print(f"\nWorkflow complete:")
    print(f"  Status: {result.status.value}")
    print(f"  Root Cause: {result.root_cause} ({result.root_cause_confidence:.0f}%)")
    print(f"  Risk: {result.risk_level.value}")
    print(f"  Action: {result.remediation_action.value}")
    print(f"  Verified: {result.verification_passed}")
    if result.metrics:
        print(f"  Latency after fix: {result.metrics.api_response_time_ms:.0f}ms")
    if result.summary:
        print(f"\n  Summary: {result.summary}")


def main():
    parser = argparse.ArgumentParser(description="Intelligent Incident Resolution Agent")
    parser.add_argument("--detect", action="store_true", help="Run detection and full workflow")
    parser.add_argument("--service", type=str, default=None, help="Target service name")
    parser.add_argument(
        "--scenario",
        type=str,
        default="random",
        choices=MetricsCollector.available_scenarios(),
        help="Simulation scenario (gray_failure, dependency_cascade, alert_storm, etc.)",
    )
    parser.add_argument("--seed", action="store_true", help="Seed knowledge base only")
    parser.add_argument("--init-db", action="store_true", help="Initialize database")
    args = parser.parse_args()

    if args.init_db:
        init_db()
        print("Database initialized.")
        return

    if args.seed:
        init_db()
        seed_knowledge_base()
        return

    if args.detect:
        run_detection_pipeline(args.service, args.scenario)
        return

    parser.print_help()
    print("\nFlagship scenarios:")
    for s in DETERMINISTIC_SCENARIOS:
        print(f"  --scenario {s}")


if __name__ == "__main__":
    main()

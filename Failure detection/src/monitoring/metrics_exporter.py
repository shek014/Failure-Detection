"""Prometheus exporter that publishes real host telemetry.

Runs standalone (`python -m src.monitoring.metrics_exporter`) and serves
/metrics on EXPORT_PORT. Prometheus scrapes this; MetricsCollector then reads
it back via prometheus_client.py when SIMULATE_METRICS=false. Metric names
match exactly what prometheus_client.py._fetch_from_prometheus() queries.
"""

from __future__ import annotations

import socket
import sqlite3
import time
from collections import deque
from pathlib import Path

import psutil
import requests
from prometheus_client import Gauge, start_http_server

from config.settings import get_settings
from src.monitoring.prometheus_client import MetricsCollector

EXPORT_PORT = 9200
DNS_PROBE = ("8.8.8.8", 53)
FAILURE_WINDOW = 20

cpu_usage_percent = Gauge("cpu_usage_percent", "Real host CPU usage percent", ["service"])
memory_usage_percent = Gauge("memory_usage_percent", "Real host memory usage percent", ["service"])
disk_usage_percent = Gauge("disk_usage_percent", "Real host disk usage percent", ["service"])
network_latency_ms = Gauge("network_latency_ms", "Real TCP round-trip latency to 8.8.8.8:53", ["service"])
http_request_duration_ms = Gauge("http_request_duration_ms", "Real HTTP round-trip time to the local app", ["service"])
error_rate_percent = Gauge("error_rate_percent", "Real reachability failure rate over the last N checks", ["service"])
up = Gauge("up", "Whether the local app responded to an HTTP check", ["service"])
db_up = Gauge("db_up", "Whether the SQLite incidents database is reachable")

_recent_failures: deque[bool] = deque(maxlen=FAILURE_WINDOW)


def _tcp_latency_ms(host: str, port: int, timeout: float = 1.5) -> float | None:
    start = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return (time.perf_counter() - start) * 1000
    except OSError:
        return None


def _http_latency_ms(url: str, timeout: float = 2.0) -> float | None:
    start = time.perf_counter()
    try:
        requests.get(url, timeout=timeout)
        return (time.perf_counter() - start) * 1000
    except requests.RequestException:
        return None


def _database_healthy(database_url: str) -> bool:
    db_path = database_url.replace("sqlite:///", "")
    try:
        conn = sqlite3.connect(db_path, timeout=1.0)
        conn.execute("SELECT 1")
        conn.close()
        return True
    except sqlite3.Error:
        return False


def sample_once(settings) -> None:
    drive_root = Path.cwd().anchor or "/"

    cpu = psutil.cpu_percent(interval=1.0)
    mem = psutil.virtual_memory().percent
    disk = psutil.disk_usage(drive_root).percent

    net_latency = _tcp_latency_ms(*DNS_PROBE)
    http_latency = _http_latency_ms(f"http://localhost:{settings.streamlit_port}")

    app_reachable = http_latency is not None
    _recent_failures.append(not app_reachable)
    failure_rate = 100 * sum(_recent_failures) / len(_recent_failures)

    db_healthy = _database_healthy(settings.database_url)

    for service in MetricsCollector.SERVICES:
        cpu_usage_percent.labels(service=service).set(cpu)
        memory_usage_percent.labels(service=service).set(mem)
        disk_usage_percent.labels(service=service).set(disk)
        network_latency_ms.labels(service=service).set(net_latency if net_latency is not None else 5000.0)
        http_request_duration_ms.labels(service=service).set(http_latency if http_latency is not None else 5000.0)
        error_rate_percent.labels(service=service).set(failure_rate)
        up.labels(service=service).set(1 if app_reachable else 0)

    db_up.set(1 if db_healthy else 0)


def main() -> None:
    settings = get_settings()
    # Bind to loopback only: these are real host metrics and shouldn't be
    # visible to other devices on the network. Use --expose to bind 0.0.0.0
    # (required only if a Dockerized Prometheus needs to reach this via
    # host.docker.internal, since that hostname can't route to 127.0.0.1).
    import sys

    bind_addr = "0.0.0.0" if "--expose" in sys.argv else "127.0.0.1"
    start_http_server(EXPORT_PORT, addr=bind_addr)
    print(f"Metrics exporter serving real host telemetry on http://{bind_addr}:{EXPORT_PORT}/metrics")
    if bind_addr == "0.0.0.0":
        print("WARNING: exposed on all network interfaces — visible to other devices on your network.")
    interval = max(settings.metrics_poll_interval_seconds, 5)
    while True:
        sample_once(settings)
        time.sleep(interval)


if __name__ == "__main__":
    main()

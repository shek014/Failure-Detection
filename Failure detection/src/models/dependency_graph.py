"""Service dependency graph for root cause analysis."""

from __future__ import annotations

from pydantic import BaseModel, Field


class DependencyNode(BaseModel):
    name: str
    status: str = "healthy"
    latency_ms: float = 0.0
    error_rate_percent: float = 0.0
    depends_on: list[str] = Field(default_factory=list)


class DependencyGraph(BaseModel):
    nodes: list[DependencyNode] = Field(default_factory=list)
    root_cause_service: str = ""

    def to_dict_list(self) -> list[dict]:
        return [n.model_dump() for n in self.nodes]

    @classmethod
    def from_dict_list(cls, data: list[dict]) -> DependencyGraph:
        return cls(nodes=[DependencyNode(**d) for d in data])

    def get_unhealthy_leaf(self) -> str | None:
        """Return the root-cause service: unhealthy node whose dependencies are healthy."""
        node_map = {n.name: n for n in self.nodes}
        unhealthy = [n for n in self.nodes if n.status != "healthy"]

        if not unhealthy:
            return None

        for node in unhealthy:
            deps_healthy = all(
                node_map.get(dep, DependencyNode(name=dep, status="healthy")).status == "healthy"
                for dep in node.depends_on
            )
            if deps_healthy:
                return node.name

        return min(unhealthy, key=lambda n: (len(n.depends_on), -n.latency_ms)).name

    def format_summary(self) -> dict[str, str]:
        return {n.name: f"{n.status} ({n.latency_ms:.0f}ms)" for n in self.nodes}


DEFAULT_GRAPH_EDGES: dict[str, list[str]] = {
    "Frontend": ["User API"],
    "User API": ["Auth Service"],
    "Auth Service": ["Redis", "PostgreSQL"],
    "Payment API": ["Auth Service", "PostgreSQL"],
    "Order Service": ["Inventory Service", "PostgreSQL"],
    "Inventory Service": ["PostgreSQL", "Redis"],
    "Notification Service": ["Kafka"],
}

SCENARIO_GRAPHS: dict[str, dict[str, dict]] = {
    "dependency_cascade": {
        "Frontend": {"status": "degraded", "latency_ms": 2800, "error_rate_percent": 4.0},
        "User API": {"status": "degraded", "latency_ms": 2200, "error_rate_percent": 3.5},
        "Auth Service": {"status": "degraded", "latency_ms": 1800, "error_rate_percent": 2.8},
        "Redis": {"status": "unhealthy", "latency_ms": 4500, "error_rate_percent": 12.0},
        "PostgreSQL": {"status": "healthy", "latency_ms": 45, "error_rate_percent": 0.1},
    },
    "alert_storm": {
        "Frontend": {"status": "degraded", "latency_ms": 3200, "error_rate_percent": 8.0},
        "User API": {"status": "degraded", "latency_ms": 2900, "error_rate_percent": 7.0},
        "Payment API": {"status": "degraded", "latency_ms": 3100, "error_rate_percent": 9.0},
        "Order Service": {"status": "degraded", "latency_ms": 2800, "error_rate_percent": 6.5},
        "Inventory Service": {"status": "degraded", "latency_ms": 3500, "error_rate_percent": 10.0},
        "Auth Service": {"status": "degraded", "latency_ms": 2600, "error_rate_percent": 5.0},
        "Notification Service": {"status": "degraded", "latency_ms": 2400, "error_rate_percent": 4.0},
        "PostgreSQL": {"status": "unhealthy", "latency_ms": 4200, "error_rate_percent": 15.0},
        "Redis": {"status": "healthy", "latency_ms": 30, "error_rate_percent": 0.2},
    },
    "gray_failure": {
        "Frontend": {"status": "healthy", "latency_ms": 250, "error_rate_percent": 1.2},
        "User API": {"status": "healthy", "latency_ms": 240, "error_rate_percent": 1.0},
        "Inventory Service": {"status": "healthy", "latency_ms": 230, "error_rate_percent": 0.8},
        "PostgreSQL": {"status": "degraded", "latency_ms": 220, "error_rate_percent": 0.5},
        "Network Switch": {"status": "degraded", "latency_ms": 180, "error_rate_percent": 2.0},
    },
}


def build_graph_for_scenario(scenario: str, affected_service: str) -> DependencyGraph:
    """Build a dependency graph for a given scenario."""
    overrides = SCENARIO_GRAPHS.get(scenario, {})

    if scenario == "dependency_cascade":
        edges = {
            "Frontend": ["User API"],
            "User API": ["Auth Service"],
            "Auth Service": ["Redis"],
            "Redis": [],
        }
    elif scenario == "alert_storm":
        edges = {
            "Frontend": ["User API"],
            "User API": ["Auth Service"],
            "Payment API": ["Auth Service", "PostgreSQL"],
            "Order Service": ["Inventory Service"],
            "Inventory Service": ["PostgreSQL"],
            "Auth Service": ["PostgreSQL"],
            "Notification Service": ["Order Service"],
            "PostgreSQL": [],
        }
    else:
        edges = {
            "Frontend": ["User API"],
            "User API": ["Inventory Service"],
            "Inventory Service": ["PostgreSQL"],
            "PostgreSQL": ["Network Switch"],
            "Network Switch": [],
        }

    nodes = []
    for name, deps in edges.items():
        meta = overrides.get(name, {"status": "healthy", "latency_ms": 50, "error_rate_percent": 0.1})
        nodes.append(
            DependencyNode(
                name=name,
                status=meta["status"],
                latency_ms=meta["latency_ms"],
                error_rate_percent=meta["error_rate_percent"],
                depends_on=deps,
            )
        )

    graph = DependencyGraph(nodes=nodes)
    graph.root_cause_service = graph.get_unhealthy_leaf() or ""
    return graph

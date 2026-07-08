"""Seed knowledge base with runbooks and sample historical incidents."""

from pathlib import Path

from src.rag.vector_store import VectorStore


RUNBOOKS = [
    {
        "id": "RB-01",
        "title": "High CPU Recovery",
        "content": (
            "Runbook RB-01: High CPU Recovery. "
            "When CPU exceeds 95%, check for runaway processes, "
            "review recent deployments, scale horizontally if needed, "
            "or restart the affected service after capturing heap dumps."
        ),
    },
    {
        "id": "RB-12",
        "title": "Memory Leak Recovery",
        "content": (
            "Runbook RB-12: Memory Leak Recovery. "
            "When memory exceeds 90% with OutOfMemoryError in logs, "
            "capture heap dump, restart service to restore capacity, "
            "investigate connection pool leaks and unclosed resources."
        ),
    },
    {
        "id": "RB-05",
        "title": "API Latency Spike",
        "content": (
            "Runbook RB-05: API Latency Spike. "
            "When API response times exceed 2000ms, check database connection pool, "
            "review slow query logs, verify downstream dependencies, "
            "restart database proxy if connection pool is exhausted."
        ),
    },
    {
        "id": "RB-08",
        "title": "Service Down Recovery",
        "content": (
            "Runbook RB-08: Service Down Recovery. "
            "When service health check fails, verify container status, "
            "check recent deployment changes, restart pods, "
            "rollback deployment if restart fails."
        ),
    },
    {
        "id": "RB-15",
        "title": "Database Connection Recovery",
        "content": (
            "Runbook RB-15: Database Connection Recovery. "
            "When database connection errors occur, verify database health, "
            "check connection pool settings, reconnect database proxy, "
            "scale connection pool if under heavy load."
        ),
    },
]

HISTORICAL_INCIDENTS = [
    {
        "id": "INC-1024",
        "content": (
            "Incident INC-1024: User API memory leak. "
            "Memory reached 94%, OutOfMemoryError in logs. "
            "Root cause: unclosed database connections in connection pool. "
            "Resolution: restart service and fix connection leak. Success."
        ),
        "metadata": {"incident_id": "INC-1024", "service": "User API", "root_cause": "Memory Leak"},
    },
    {
        "id": "INC-1843",
        "content": (
            "Incident INC-1843: Payment API latency spike. "
            "API response time 3500ms. Database connection pool exhausted. "
            "Root cause: connection pool exhaustion. "
            "Resolution: restart database proxy. Success."
        ),
        "metadata": {"incident_id": "INC-1843", "service": "Payment API", "root_cause": "Connection Pool Exhaustion"},
    },
    {
        "id": "INC-2105",
        "content": (
            "Incident INC-2105: Order Service CPU spike. "
            "CPU at 98% after deployment. "
            "Root cause: infinite loop in new release. "
            "Resolution: rollback deployment. Success."
        ),
        "metadata": {"incident_id": "INC-2105", "service": "Order Service", "root_cause": "Bad Deployment"},
    },
]

SOPS = [
    {
        "id": "SOP-01",
        "content": (
            "SOP-01: Incident Escalation Procedure. "
            "Critical risk incidents require immediate escalation to on-call engineer. "
            "Security incidents escalate to security team. "
            "Data corruption requires DBA approval before any action."
        ),
    },
    {
        "id": "SOP-02",
        "content": (
            "SOP-02: Automated Remediation Approval Matrix. "
            "Low risk: auto-resolve. Medium: auto-resolve with verification. "
            "High: human approval required. Critical: immediate escalation."
        ),
    },
]


def seed_knowledge_base() -> None:
    store = VectorStore()

    store.add_documents(
        "runbooks",
        [r["content"] for r in RUNBOOKS],
        metadatas=[{"id": r["id"], "title": r["title"]} for r in RUNBOOKS],
        ids=[r["id"] for r in RUNBOOKS],
    )

    store.add_documents(
        "historical_incidents",
        [h["content"] for h in HISTORICAL_INCIDENTS],
        metadatas=[h["metadata"] for h in HISTORICAL_INCIDENTS],
        ids=[h["id"] for h in HISTORICAL_INCIDENTS],
    )

    store.add_documents(
        "sops",
        [s["content"] for s in SOPS],
        metadatas=[{"id": s["id"]} for s in SOPS],
        ids=[s["id"] for s in SOPS],
    )

    print("Knowledge base seeded successfully.")


if __name__ == "__main__":
    seed_knowledge_base()

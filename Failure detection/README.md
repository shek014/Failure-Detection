# Intelligent Incident Resolution Agent

An AI-powered self-healing incident management platform that detects anomalies, gathers evidence through RAG, builds incident context, identifies root causes, assesses risk, autonomously resolves low-risk incidents via MCP-connected tools, verifies recovery, maintains a complete audit trail, and escalates only when human intervention is necessary.

## Architecture

```
Detection Agent
        ↓
LangGraph Orchestrator
        ↓
Data/RAG Agent → Context Builder → Root Cause Agent
        ↓
Risk Assessment → Decision Agent
        ↓
Resolution Agent (MCP) → Verification Agent
        ↓
Notification Agent → Audit Storage → Feedback Loop
```

## Features

- **Continuous Monitoring** — CPU, memory, disk, latency, error rates, service health
- **Detection Agent** — Anomaly detection, false-positive filtering, deduplication, incident creation
- **LangGraph Orchestration** — Stateful multi-agent workflow with retries and escalation
- **RAG** — Runbooks, SOPs, and historical incidents via FAISS vector store
- **Root Cause Analysis** — LLM-powered or rule-based RCA with confidence scores
- **Risk Assessment** — Low/Medium/High/Critical risk matrix
- **Human-in-the-Loop** — Approval workflows for high-risk actions
- **MCP Execution** — Restart services, scale containers, rollback deployments
- **Verification** — Post-remediation health checks with retry/escalate logic
- **Feedback Loop** — Resolved incidents feed back into RAG for continuous improvement
- **AI Ops Assistant** — Natural language queries over incidents and audit logs

## Quick Start

### 1. Setup

```bash
cd "Failure detection"
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt
copy .env.example .env       # Add GROQ_API_KEY (optional, free at console.groq.com — works without LLM too)
```

### 2. Initialize

```bash
python src/main.py --init-db
python src/main.py --seed
```

### 3. Run CLI Demo

```bash
python src/main.py --detect
python src/main.py --detect --service "User API"
```

### 4. Launch Dashboard

```bash
streamlit run src/ui/streamlit_app.py
```

Open http://localhost:8501

### 5. Docker

```bash
docker-compose up --build
```

## Project Structure

```
├── config/settings.py          # Environment configuration
├── src/
│   ├── agents/                 # All workflow agents
│   ├── orchestration/          # LangGraph orchestrator
│   ├── rag/                    # Vector store & knowledge base
│   ├── mcp/                    # MCP tool execution
│   ├── monitoring/             # Prometheus metrics collector
│   ├── feedback/               # Learning loop
│   ├── assistant/              # AI Ops Assistant
│   ├── database/               # SQLite persistence & audit
│   ├── models/                 # Pydantic domain models
│   └── ui/                     # Streamlit dashboard
├── scripts/seed_knowledge_base.py
├── data/                       # SQLite DB & vector store files
└── monitoring/prometheus.yml
```

## Technology Stack

| Technology | Purpose |
|---|---|
| LangChain / LangGraph | Agent creation & orchestration |
| FAISS + Embeddings | Vector storage for RAG |
| Groq | LLM for RCA, reports, assistant |
| Streamlit | Dashboard & AI assistant UI |
| SQLite | Incident & audit persistence |
| MCP | Tool execution layer |
| Prometheus | Metric collection (optional) |
| Docker | Deployment |

## Workflow Example

1. **Detect** — CPU > 95% on User API → Incident INC-A1B2C3D4 created
2. **Investigate** — RAG retrieves Runbook RB-12, similar incident INC-1024
3. **RCA** — Root cause: Memory Leak (91% confidence)
4. **Risk** — Low risk → auto-resolve
5. **Resolve** — MCP restarts service
6. **Verify** — CPU 45%, memory 55% → passed
7. **Notify** — Stakeholder report generated
8. **Feedback** — Outcome stored in RAG for future incidents

## Human-in-the-Loop

High/Critical risk incidents pause at **Awaiting Approval** in the dashboard. Engineers approve or reject remediation before execution.

## License

Academic project — MIT

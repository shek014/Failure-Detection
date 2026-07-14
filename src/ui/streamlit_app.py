"""Streamlit dashboard and AI Operations Assistant."""

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from src.agents.detection_agent import DetectionAgent
from src.assistant.ai_ops_assistant import AIOpsAssistant
from src.database.store import IncidentRepository
from src.models.incident import IncidentStatus
from src.monitoring.prometheus_client import MetricsCollector
from src.orchestration.langgraph_orchestrator import IncidentOrchestrator
from scripts.seed_knowledge_base import seed_knowledge_base
from src.database.repository import init_db

st.set_page_config(
    page_title="Incident Resolution Agent",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

CUSTOM_CSS = """
<style>
.block-container { padding-top: 1.75rem; padding-bottom: 3rem; max-width: 1600px; }

/* Narrower sidebar, more room for content */
[data-testid="stSidebar"] { min-width: 230px !important; max-width: 230px !important; }

/* Native sidebar nav (st.navigation) */
[data-testid="stSidebarNav"] { padding-top: 0.5rem; }
[data-testid="stSidebarNavLink"] {
    border-radius: 8px !important;
    margin: 0.1rem 0 !important;
    font-weight: 500;
    font-size: 1rem;
}
[data-testid="stSidebarNavLink"]:hover { background-color: rgba(99, 102, 241, 0.10) !important; }
[data-testid="stSidebarNavLink"][aria-current="page"] {
    background-color: rgba(99, 102, 241, 0.16) !important;
    font-weight: 700;
}

/* Main content polish */
.app-header h1 { font-size: 2.4rem; margin-bottom: 0; }
.app-header p { opacity: 0.65; margin-top: 0.15rem; font-size: 1.05rem; }

[data-testid="stMetric"] {
    background: rgba(127, 127, 127, 0.06);
    border-radius: 12px;
    padding: 1.1rem 1.3rem 0.9rem 1.3rem;
}
[data-testid="stMetricValue"] { font-size: 2.4rem; }
[data-testid="stMetricLabel"] { font-size: 1rem; }

h3 { font-size: 1.6rem !important; }

.stButton > button {
    border-radius: 8px;
    padding: 0.65rem 1.4rem;
    font-size: 1.05rem;
    font-weight: 600;
}
</style>
"""

STATUS_BADGE = {
    "resolved": ("green", "✅"),
    "escalated": ("red", "🚨"),
    "awaiting_approval": ("orange", "⏳"),
    "investigating": ("blue", "🔎"),
    "detected": ("gray", "📡"),
}

SEVERITY_BADGE = {
    "critical": "red",
    "high": "orange",
    "medium": "yellow",
    "low": "blue",
    "info": "gray",
}

RISK_BADGE = {
    "critical": "red",
    "high": "orange",
    "medium": "yellow",
    "low": "green",
}


def status_badge(status: str) -> None:
    color, icon = STATUS_BADGE.get(status, ("gray", "⚪"))
    st.badge(status.replace("_", " ").title(), color=color, icon=icon)


def severity_badge(severity: str) -> None:
    st.badge(severity.title(), color=SEVERITY_BADGE.get(severity, "gray"))


def risk_badge(risk: str) -> None:
    st.badge(risk.title(), color=RISK_BADGE.get(risk, "gray"))


@st.cache_resource
def get_repository():
    init_db()
    return IncidentRepository()


@st.cache_resource
def get_orchestrator():
    return IncidentOrchestrator(get_repository())


@st.cache_resource
def get_detection_agent(scenario: str = "random"):
    return DetectionAgent(get_repository(), scenario=scenario)


@st.cache_resource
def get_assistant():
    return AIOpsAssistant(get_repository())


def init_session():
    if "kb_seeded" not in st.session_state:
        try:
            seed_knowledge_base()
        except Exception:
            pass
        st.session_state.kb_seeded = True


def render_dashboard():
    repo = get_repository()
    incidents = repo.list_incidents(limit=20)

    total = len(incidents)
    resolved = sum(1 for i in incidents if i.status == IncidentStatus.RESOLVED)
    escalated = sum(1 for i in incidents if i.status == IncidentStatus.ESCALATED)
    pending = sum(1 for i in incidents if i.status == IncidentStatus.AWAITING_APPROVAL)

    col1, col2, col3, col4 = st.columns(4)
    with col1, st.container(border=True):
        st.metric("📋 Total Incidents", total)
    with col2, st.container(border=True):
        st.metric("✅ Resolved", resolved)
    with col3, st.container(border=True):
        st.metric("🚨 Escalated", escalated)
    with col4, st.container(border=True):
        st.metric("⏳ Awaiting Approval", pending)

    st.markdown("### Recent Incidents")
    if not incidents:
        st.info("No incidents yet. Head to **Detect Anomaly** to simulate monitoring and create one.")
        return

    for inc in incidents:
        with st.container(border=True):
            header_col, badge_col = st.columns([4, 1])
            with header_col:
                st.markdown(f"**{inc.id}** — {inc.affected_service}")
                st.caption(inc.anomaly_type)
            with badge_col:
                status_badge(inc.status.value)

            c1, c2, c3 = st.columns(3)
            with c1:
                st.caption("Severity")
                severity_badge(inc.severity.value)
            with c2:
                st.caption("Risk")
                risk_badge(inc.risk_level.value)
            with c3:
                st.caption("Verified")
                st.badge("Yes" if inc.verification_passed else "No", color="green" if inc.verification_passed else "gray")

            if inc.root_cause:
                confidence = f" ({inc.root_cause_confidence:.0f}% confidence)" if inc.root_cause_confidence else ""
                st.markdown(f"**Root Cause:** {inc.root_cause}{confidence}")

            if inc.remediation_action:
                st.markdown(f"**Action:** `{inc.remediation_action.value}`")

            if inc.correlated_alert_count:
                st.info(f"🔗 {inc.correlated_alert_count} correlated alerts grouped into this incident (`{inc.correlation_id}`)")

            if inc.scenario:
                st.caption(f"Scenario: {inc.scenario}")

            if inc.symptoms:
                st.markdown("**Symptoms:** " + ", ".join(f"`{s}`" for s in inc.symptoms))

            if inc.summary:
                with st.expander("Summary"):
                    st.write(inc.summary)

            if inc.status == IncidentStatus.AWAITING_APPROVAL:
                st.divider()
                ac1, ac2 = st.columns(2)
                with ac1:
                    if st.button("✅ Approve", key=f"approve_{inc.id}", width="stretch"):
                        get_orchestrator().approve(inc.id, approved=True)
                        st.rerun()
                with ac2:
                    if st.button("❌ Reject", key=f"reject_{inc.id}", width="stretch"):
                        get_orchestrator().approve(inc.id, approved=False)
                        st.rerun()


def render_detect():
    st.markdown("### Continuous Monitoring & Detection")
    st.caption("Simulates metrics collection and anomaly detection. Use flagship scenarios for a full demo.")

    with st.container(border=True):
        col1, col2 = st.columns(2)
        with col1:
            service = st.selectbox(
                "Target Service",
                ["Auto-detect"] + MetricsCollector.SERVICES,
            )
        with col2:
            scenarios = MetricsCollector.available_scenarios()
            scenario = st.selectbox(
                "Scenario",
                scenarios,
                index=scenarios.index("gray_failure") if "gray_failure" in scenarios else 0,
                help="Flagship: gray_failure, dependency_cascade, alert_storm",
            )
        st.caption("🌟 Flagship demos: `gray_failure` · `dependency_cascade` · `alert_storm`")
        detect_clicked = st.button("🔍 Detect Anomaly", type="primary", width="stretch")

    if detect_clicked:
        agent = get_detection_agent(scenario)
        svc = None if service == "Auto-detect" else service
        detection = agent.evaluate(svc)

        if not detection.is_anomaly:
            st.session_state.detect_result = {"kind": "normal", "detection": detection}
        elif detection.deduplicated:
            st.session_state.detect_result = {"kind": "dedup", "detection": detection}
        else:
            incident = agent.create_incident(detection)
            workflow_result = None
            if incident:
                with st.spinner("Running agent pipeline..."):
                    workflow_result = get_orchestrator().run(incident)
            st.session_state.detect_result = {
                "kind": "anomaly",
                "detection": detection,
                "incident": incident,
                "workflow_result": workflow_result,
            }

    result = st.session_state.get("detect_result")
    if not result:
        return

    detection = result["detection"]

    if result["kind"] == "normal":
        st.success(f"✅ All metrics normal. {detection.message}")
        m = detection.metrics
        mc1, mc2, mc3, mc4 = st.columns(4)
        mc1.metric("CPU", f"{m.cpu_percent:.1f}%")
        mc2.metric("Memory", f"{m.memory_percent:.1f}%")
        mc3.metric("Latency", f"{m.api_response_time_ms:.0f}ms")
        mc4.metric("Error Rate", f"{m.error_rate_percent:.1f}%")
        return

    if result["kind"] == "dedup":
        st.warning(f"⚠️ Deduplicated: {detection.message}")
        return

    st.error(f"🚨 Anomaly: {detection.anomaly_type} on {detection.affected_service}")
    if detection.is_gray_failure:
        st.warning(f"👻 Gray failure detected: {', '.join(detection.degradation_signals)}")

    incident = result["incident"]
    if not incident:
        return

    if incident.correlated_alert_count:
        st.info(
            f"🔗 Alert correlation: **{incident.correlated_alert_count}** alerts "
            f"grouped into root incident **{incident.id}**"
        )
    st.info(f"Created incident **{incident.id}**")

    workflow_result = result["workflow_result"]
    if not workflow_result:
        return

    with st.container(border=True):
        st.markdown("#### Workflow Complete")
        r1, r2, r3 = st.columns(3)
        with r1:
            status_badge(workflow_result.status.value)
        with r2:
            risk_badge(workflow_result.risk_level.value)
        with r3:
            st.badge("Verified" if workflow_result.verification_passed else "Not Verified",
                     color="green" if workflow_result.verification_passed else "red")
        st.markdown(f"**Root cause:** {workflow_result.root_cause} ({workflow_result.root_cause_confidence:.0f}% confidence)")
        if workflow_result.metrics:
            st.markdown(f"**Latency after remediation:** {workflow_result.metrics.api_response_time_ms:.0f}ms")
        if workflow_result.summary:
            st.write(workflow_result.summary)


def render_incident_detail():
    st.markdown("### Incident Detail & Audit Trail")
    repo = get_repository()
    incidents = repo.list_incidents(limit=50)
    if not incidents:
        st.info("No incidents to display.")
        return

    selected = st.selectbox("Select Incident", [i.id for i in incidents])
    if not selected:
        return

    incident = repo.get_incident(selected)
    audit = repo.get_audit_trail(selected)

    if incident:
        with st.container(border=True):
            h1, h2 = st.columns([3, 1])
            with h1:
                st.markdown(f"#### {incident.id} — {incident.affected_service}")
            with h2:
                status_badge(incident.status.value)

            c1, c2, c3 = st.columns(3)
            with c1:
                st.caption("Severity")
                severity_badge(incident.severity.value)
            with c2:
                st.caption("Risk")
                risk_badge(incident.risk_level.value)
            with c3:
                st.caption("Action")
                st.markdown(f"`{incident.remediation_action.value}`")

            if incident.root_cause:
                st.markdown(f"**Root Cause:** {incident.root_cause} ({incident.root_cause_confidence:.0f}%)")
            if incident.summary:
                st.markdown(f"**Summary:** {incident.summary}")

        with st.expander("Raw incident JSON"):
            st.json(incident.model_dump(mode="json"))

    st.markdown("#### Audit Trail")
    if not audit:
        st.caption("No audit entries recorded.")
    for entry in audit:
        with st.container(border=True):
            st.markdown(f"🕒 `{entry.timestamp}` — **{entry.agent_name}** → {entry.action}")


def render_assistant():
    st.markdown("### AI Operations Assistant")
    st.caption("Ask questions about incidents, root causes, escalations, and history.")

    examples = [
        "Explain the most recent incident",
        "What caused today's outage?",
        "Has this happened before?",
        "Why was this escalated?",
        "Show similar incidents",
        "What actions were executed?",
    ]

    question = st.text_input("Your question", placeholder=examples[0])
    ex_cols = st.columns(len(examples))
    for i, ex in enumerate(examples):
        with ex_cols[i]:
            if st.button(ex, key=f"ex_{i}"):
                st.session_state.assistant_q = ex

    q = st.session_state.get("assistant_q", question)
    if q:
        with st.spinner("Searching incidents and knowledge base..."):
            answer = get_assistant().ask(q)
        with st.container(border=True):
            st.markdown("#### Answer")
            st.markdown(answer)


def main():
    init_session()
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

    pages = [
        st.Page(render_dashboard, title="Dashboard", icon="📊", default=True),
        st.Page(render_detect, title="Detect Anomaly", icon="🔍"),
        st.Page(render_incident_detail, title="Incident Detail", icon="📄"),
        st.Page(render_assistant, title="AI Assistant", icon="💬"),
    ]
    pg = st.navigation(pages)

    st.markdown(
        """
        <div class="app-header">
            <h1 style="margin-bottom:0;">🛡️ Intelligent Incident Resolution Agent</h1>
            <p>Agentic AI • LangGraph • RAG • MCP • Human-in-the-Loop</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    pg.run()


if __name__ == "__main__":
    main()

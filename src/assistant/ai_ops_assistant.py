"""AI Operations Assistant for interactive incident queries."""

from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq

from config.settings import get_settings
from src.database.store import IncidentRepository
from src.rag.knowledge_base import KnowledgeBase


INCIDENT_ID_RE = re.compile(r"INC-[A-Za-z0-9]{4,}")


class AIOpsAssistant:
    SYSTEM_PROMPT = """You are an AI Operations Assistant for an incident management platform.
Answer questions about incidents using the provided context from audit logs, historical data, and runbooks.
Be accurate and reference specific incident IDs when relevant.

Format every response in Markdown as follows:
- Use a short bold header per incident or topic, e.g. **INC-1234 — Auth Service**.
- Under each header, use bullet points for facts (root cause, action taken, verification).
- Use nested sub-bullets (indented `-`) for supporting detail, e.g. prevention steps or runbook references.
- End with a **Prevention** section summarizing concrete, actionable steps.
- Never truncate mid-sentence; keep the full answer within the response.
"""

    def __init__(
        self,
        repository: IncidentRepository | None = None,
        knowledge_base: KnowledgeBase | None = None,
    ) -> None:
        self.settings = get_settings()
        self.repository = repository or IncidentRepository()
        self.knowledge_base = knowledge_base or KnowledgeBase()
        self._llm = None

    @property
    def llm(self) -> ChatGroq | None:
        if self._llm is None and self.settings.groq_api_key:
            self._llm = ChatGroq(
                model=self.settings.groq_model,
                api_key=self.settings.groq_api_key,
                temperature=0.2,
                max_tokens=1536,
            )
        return self._llm

    def ask(self, question: str) -> str:
        parts = self._build_context(question)
        context = "\n".join(parts) if parts else "No incident data available."

        if self.llm:
            try:
                response = self.llm.invoke(
                    [
                        SystemMessage(content=self.SYSTEM_PROMPT),
                        HumanMessage(content=f"Context:\n{context}\n\nQuestion: {question}"),
                    ]
                )
                return response.content
            except Exception as e:
                return f"**LLM error:** {e}\n\n{self._rule_based_answer(question, parts)}"

        return self._rule_based_answer(question, parts)

    def _build_context(self, question: str) -> list[str]:
        parts = []

        requested_ids = {m.upper() for m in INCIDENT_ID_RE.findall(question)}
        incidents = [
            inc
            for inc in (self.repository.get_incident(iid) for iid in requested_ids)
            if inc is not None
        ]

        if not incidents and not requested_ids:
            incidents = self.repository.search_incidents(question, limit=5)
        if not incidents and not requested_ids:
            incidents = self.repository.list_incidents(limit=5)

        for inc in incidents:
            parts.append(
                f"Incident {inc.id}: {inc.affected_service} - {inc.anomaly_type} "
                f"[{inc.status.value}] Root cause: {inc.root_cause}. "
                f"Action: {inc.remediation_action.value}. "
                f"Verified: {inc.verification_passed}"
            )

        rag_query = incidents[0].root_cause if incidents else question
        rag = self.knowledge_base.vector_store.search_all(rag_query, n_results=2)
        for category, docs in rag.items():
            for doc in docs:
                parts.append(f"[{category}] {doc.get('document', '')[:500]}")

        if not requested_ids:
            feedback = self.repository.get_feedback_history(limit=3)
            for fb in feedback:
                parts.append(f"Feedback {fb.incident_id}: {fb.outcome} - {fb.lessons_learned[:100]}")

        return list(dict.fromkeys(parts))

    def _rule_based_answer(self, question: str, parts: list[str]) -> str:
        if not parts:
            return "No incident data available yet."

        q = question.lower()

        if "similar" in q:
            header = "**Based on RAG search:**"
        elif "escalat" in q:
            header = (
                "**Escalation criteria:**\n"
                "- Risk is High/Critical\n"
                "- Confidence is below 50%\n"
                "- Verification fails repeatedly\n"
                "- Conflicting evidence exists\n\n"
                "**Related incidents:**"
            )
        elif "action" in q and "execut" in q:
            header = "**Executed actions from recent incidents:**"
        elif "cause" in q or "outage" in q:
            header = "**Recent root causes:**"
        else:
            header = "**Here's what I found:**"

        bullets = "\n".join(f"- {p}" for p in parts[:8])
        return f"{header}\n{bullets}"

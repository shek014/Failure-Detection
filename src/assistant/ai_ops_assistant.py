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


class AIOpsAssistant:
    SYSTEM_PROMPT = """You are an AI Operations Assistant for an incident management platform.
Answer questions about incidents using the provided context from audit logs, historical data, and runbooks.
Be concise, accurate, and reference specific incident IDs when relevant.
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
            )
        return self._llm

    def ask(self, question: str) -> str:
        context = self._build_context(question)

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
                return f"LLM error: {e}\n\nFallback answer:\n{self._rule_based_answer(question, context)}"

        return self._rule_based_answer(question, context)

    def _build_context(self, question: str) -> str:
        parts = []

        incidents = self.repository.search_incidents(question, limit=5)
        if not incidents:
            incidents = self.repository.list_incidents(limit=5)

        for inc in incidents:
            parts.append(
                f"Incident {inc.id}: {inc.affected_service} - {inc.anomaly_type} "
                f"[{inc.status.value}] Root cause: {inc.root_cause}. "
                f"Action: {inc.remediation_action.value}. "
                f"Verified: {inc.verification_passed}"
            )

        rag = self.knowledge_base.vector_store.search_all(question, n_results=2)
        for category, docs in rag.items():
            for doc in docs:
                parts.append(f"[{category}] {doc.get('document', '')[:200]}")

        feedback = self.repository.get_feedback_history(limit=3)
        for fb in feedback:
            parts.append(f"Feedback {fb.incident_id}: {fb.outcome} - {fb.lessons_learned[:100]}")

        return "\n".join(parts) if parts else "No incident data available."

    def _rule_based_answer(self, question: str, context: str) -> str:
        q = question.lower()

        if "similar" in q:
            return f"Based on RAG search:\n{context[:1000]}"
        if "escalat" in q:
            return (
                "Incidents are escalated when risk is High/Critical, confidence is below 50%, "
                "verification fails repeatedly, or conflicting evidence exists.\n\n" + context[:500]
            )
        if "action" in q and "execut" in q:
            return f"Executed actions from recent incidents:\n{context[:800]}"
        if "cause" in q or "outage" in q:
            return f"Recent root causes:\n{context[:800]}"

        return f"Here's what I found:\n{context[:1200]}"

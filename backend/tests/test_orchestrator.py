# =============================================================================
# tests/test_orchestrator.py — Orchestrator Decision Matrix Tests
# =============================================================================
# Verifies the decision engine correctly routes to auto_reply, clarify,
# or escalate based on similarity scores and intent.
# =============================================================================

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from services.orchestrator import process, compute_weighted_score, OrchestratorResult


class TestWeightedScoring:
    """Test the weighted composite score computation."""

    def test_perfect_score(self):
        """Perfect similarity + intent match + recent + reliable = ~1.0."""
        score = compute_weighted_score(
            similarity=1.0, intent_match=True,
            recency_factor=1.0, source_reliability=1.0,
        )
        assert score == pytest.approx(1.0, abs=0.01)

    def test_zero_similarity(self):
        """Zero similarity should produce a low score."""
        score = compute_weighted_score(
            similarity=0.0, intent_match=True,
            recency_factor=1.0, source_reliability=1.0,
        )
        assert score <= 0.5

    def test_intent_mismatch_reduces_score(self):
        """Intent mismatch should reduce the weighted score."""
        score_match = compute_weighted_score(1.0, intent_match=True)
        score_no_match = compute_weighted_score(1.0, intent_match=False)
        assert score_match > score_no_match

    def test_high_similarity_threshold(self):
        """Similarity of 0.90 with matching intent should exceed auto-resolve threshold."""
        score = compute_weighted_score(
            similarity=0.90, intent_match=True,
            recency_factor=0.8, source_reliability=1.0,
        )
        assert score >= 0.82, f"Score {score} should be >= 0.82 for auto-resolve"

    def test_medium_similarity(self):
        """Similarity of 0.65 should fall in the clarify range."""
        score = compute_weighted_score(
            similarity=0.65, intent_match=True,
            recency_factor=0.5, source_reliability=0.8,
        )
        assert 0.50 <= score < 0.82


class TestOrchestrator:
    """Test the full orchestrator decision flow."""

    @pytest.mark.asyncio
    @patch("services.orchestrator.llm_service")
    @patch("services.orchestrator.embedding_service")
    @patch("services.orchestrator.endee_client")
    @patch("services.orchestrator.log_chat_session", new_callable=AsyncMock, return_value="session_123")
    @patch("services.orchestrator.create_ticket", new_callable=AsyncMock, return_value="ticket_123")
    @patch("services.orchestrator.log_audit", new_callable=AsyncMock)
    async def test_human_escalation_intent(
        self, mock_audit, mock_ticket, mock_session,
        mock_endee, mock_emb, mock_llm,
    ):
        """'human_escalation' intent should immediately escalate."""
        mock_llm.classify_intent = AsyncMock(return_value="human_escalation")

        result = await process("I want to speak to a human", "company_123")

        assert result.action == "escalate"
        assert result.intent == "human_escalation"
        mock_ticket.assert_called_once()

    @pytest.mark.asyncio
    @patch("services.orchestrator.llm_service")
    @patch("services.orchestrator.embedding_service")
    @patch("services.orchestrator.endee_client")
    @patch("services.orchestrator.log_chat_session", new_callable=AsyncMock, return_value="session_123")
    @patch("services.orchestrator.create_ticket", new_callable=AsyncMock, return_value="ticket_123")
    @patch("services.orchestrator.log_audit", new_callable=AsyncMock)
    async def test_no_search_results_escalates(
        self, mock_audit, mock_ticket, mock_session,
        mock_endee, mock_emb, mock_llm,
    ):
        """No Endee results should trigger escalation."""
        mock_llm.classify_intent = AsyncMock(return_value="general")
        mock_emb.encode = MagicMock(return_value=[0.1] * 384)
        mock_endee.search = MagicMock(return_value=[])

        result = await process("some obscure question", "company_123")

        assert result.action == "escalate"

    @pytest.mark.asyncio
    @patch("services.orchestrator.llm_service")
    @patch("services.orchestrator.embedding_service")
    @patch("services.orchestrator.endee_client")
    @patch("services.orchestrator.log_chat_session", new_callable=AsyncMock, return_value="session_123")
    @patch("services.orchestrator.log_audit", new_callable=AsyncMock)
    async def test_high_score_auto_replies(
        self, mock_audit, mock_session,
        mock_endee, mock_emb, mock_llm,
    ):
        """High similarity score should auto-reply with RAG."""
        mock_llm.classify_intent = AsyncMock(return_value="billing")
        mock_llm.generate_rag_response = AsyncMock(
            return_value="Your invoice is available in your account. Source: [TICKET-001]"
        )
        mock_emb.encode = MagicMock(return_value=[0.1] * 384)
        mock_endee.search = MagicMock(return_value=[
            {
                "id": "vec_1",
                "similarity": 0.95,
                "meta": {
                    "company_id": "company_123",
                    "ticket_id": "TICKET-001",
                    "raw_text": "Invoice can be found in account settings.",
                    "category": "billing",
                    "is_resolved": "true",
                },
            },
        ])

        result = await process("Where is my invoice?", "company_123")

        assert result.action == "auto_reply"
        assert "TICKET-001" in result.sources

    @pytest.mark.asyncio
    @patch("services.orchestrator.llm_service")
    @patch("services.orchestrator.embedding_service")
    @patch("services.orchestrator.endee_client")
    @patch("services.orchestrator.log_chat_session", new_callable=AsyncMock, return_value="session_123")
    @patch("services.orchestrator.create_ticket", new_callable=AsyncMock, return_value="ticket_123")
    @patch("services.orchestrator.log_audit", new_callable=AsyncMock)
    async def test_low_score_escalates(
        self, mock_audit, mock_ticket, mock_session,
        mock_endee, mock_emb, mock_llm,
    ):
        """Low similarity score should escalate to human."""
        mock_llm.classify_intent = AsyncMock(return_value="technical")
        mock_emb.encode = MagicMock(return_value=[0.1] * 384)
        mock_endee.search = MagicMock(return_value=[
            {
                "id": "vec_1",
                "similarity": 0.30,
                "meta": {
                    "company_id": "company_123",
                    "raw_text": "Unrelated content",
                    "category": "general",
                },
            },
        ])

        result = await process("My quantum flux capacitor is broken", "company_123")

        assert result.action == "escalate"
        assert result.context_passed_to_agent is True

    @pytest.mark.asyncio
    @patch("services.orchestrator.llm_service")
    @patch("services.orchestrator.embedding_service")
    @patch("services.orchestrator.endee_client")
    @patch("services.orchestrator.log_chat_session", new_callable=AsyncMock, return_value="session_123")
    @patch("services.orchestrator.log_audit", new_callable=AsyncMock)
    async def test_medium_score_clarifies(
        self, mock_audit, mock_session,
        mock_endee, mock_emb, mock_llm,
    ):
        """Medium similarity score should ask for clarification."""
        mock_llm.classify_intent = AsyncMock(return_value="general")
        mock_llm.generate_clarifying_question = AsyncMock(
            return_value="Could you clarify whether this is about billing or technical support?"
        )
        mock_emb.encode = MagicMock(return_value=[0.1] * 384)
        mock_endee.search = MagicMock(return_value=[
            {
                "id": "vec_1",
                "similarity": 0.72,
                "meta": {
                    "company_id": "company_123",
                    "title": "Billing FAQ",
                    "raw_text": "How to update payment method",
                    "category": "general",
                },
            },
            {
                "id": "vec_2",
                "similarity": 0.68,
                "meta": {
                    "company_id": "company_123",
                    "title": "Tech Support",
                    "raw_text": "Troubleshooting connection issues",
                    "category": "general",
                },
            },
        ])

        result = await process("I need help with my account", "company_123")

        assert result.action == "clarify"
        assert len(result.suggested_docs) > 0

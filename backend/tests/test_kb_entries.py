# =============================================================================
# tests/test_kb_entries.py — Knowledge Base Entry & Learning Loop Tests
# =============================================================================
# Covers:
#   - Resolve conversation → KB entry creation + Endee ingestion (learning loop)
#   - doc_id stored back from ingestion result
#   - ingest_to_kb=False path: no entry, no vector upsert
#   - Admin KB entry CRUD (list, update, delete)
#   - Staff cannot access admin KB endpoints (RBAC enforcement)
#   - Resolved KBEntry boosts orchestrator to auto_reply on similar questions
# =============================================================================

import pytest
from unittest.mock import AsyncMock, patch, MagicMock, call
from fastapi import HTTPException

from services.orchestrator import OrchestratorResult, process_conversation_message
from api.conversations import resolve_conv, ResolveRequest
from api.admin import (
    list_kb,
    update_kb,
    delete_kb,
    UpdateKBEntryRequest,
)


# =============================================================================
# Shared Helpers
# =============================================================================

def _make_conversation(conv_id="conv_1", company_id="co_123", status="active"):
    return {
        "_id": conv_id,
        "company_id": company_id,
        "customer_id": "session_abc",
        "status": status,
    }


def _staff_user(company_id="co_123"):
    return {"role": "staff", "user_id": "staff_1", "company_id": company_id}


def _admin_user(company_id="co_123"):
    return {"role": "admin", "user_id": "admin_1", "company_id": company_id}


# =============================================================================
# Learning Loop: Resolve → KB Entry → Ingestion
# =============================================================================

class TestResolutionLearningLoop:

    @pytest.mark.asyncio
    @patch("api.conversations.get_conversation", new_callable=AsyncMock)
    @patch("api.conversations.list_messages", new_callable=AsyncMock)
    @patch("api.conversations.create_kb_entry", new_callable=AsyncMock, return_value="kb_entry_1")
    @patch("api.conversations.update_conversation", new_callable=AsyncMock)
    @patch("api.conversations.log_audit", new_callable=AsyncMock)
    async def test_ingest_to_kb_true_calls_ingest_pipeline(
        self, mock_audit, mock_update, mock_create_kb, mock_list_msgs, mock_get_conv
    ):
        """
        Resolving with ingest_to_kb=True triggers ingest_resolved_ticket()
        which embeds the canonical answer and upserts it into Endee.
        """
        mock_get_conv.return_value = _make_conversation()
        mock_list_msgs.return_value = [
            {"sender_type": "customer", "content": "How do I cancel my subscription?"}
        ]

        with patch("services.ingestion.ingest_resolved_ticket", new_callable=AsyncMock,
                   return_value={"doc_id": "doc_abc", "chunk_count": 3}) as mock_ingest, \
             patch("api.conversations.set_kb_entry_doc_id", new_callable=AsyncMock) as mock_set_doc:

            result = await resolve_conv(
                "conv_1",
                ResolveRequest(
                    canonical_answer="Go to Settings > Subscription > Cancel.",
                    title="How to cancel subscription",
                    tags="billing,subscription",
                    ingest_to_kb=True,
                ),
                user=_staff_user(),
            )

        # Ingestion pipeline was called
        mock_ingest.assert_called_once()
        call_kwargs = mock_ingest.call_args[1]
        assert call_kwargs["company_id"] == "co_123"
        assert "cancel" in call_kwargs["resolution"].lower()

        # doc_id stored back to KB entry
        mock_set_doc.assert_called_once_with("kb_entry_1", "doc_abc")

        # Response confirms ingestion
        assert result["kb_ingested"] is True
        assert result["chunks_ingested"] == 3
        assert result["kb_entry_id"] == "kb_entry_1"

    @pytest.mark.asyncio
    @patch("api.conversations.get_conversation", new_callable=AsyncMock)
    @patch("api.conversations.list_messages", new_callable=AsyncMock, return_value=[])
    @patch("api.conversations.create_kb_entry", new_callable=AsyncMock)
    @patch("api.conversations.update_conversation", new_callable=AsyncMock)
    @patch("api.conversations.log_audit", new_callable=AsyncMock)
    async def test_ingest_to_kb_false_skips_everything(
        self, mock_audit, mock_update, mock_create_kb, mock_list_msgs, mock_get_conv
    ):
        """
        ingest_to_kb=False must NOT call create_kb_entry or ingest_resolved_ticket.
        """
        mock_get_conv.return_value = _make_conversation()

        with patch("services.ingestion.ingest_resolved_ticket", new_callable=AsyncMock) as mock_ingest:
            result = await resolve_conv(
                "conv_1",
                ResolveRequest(
                    canonical_answer="The answer is proprietary.",
                    ingest_to_kb=False,
                ),
                user=_staff_user(),
            )

        mock_create_kb.assert_not_called()
        mock_ingest.assert_not_called()
        assert result["kb_entry_id"] is None
        assert result["kb_ingested"] is False
        assert result["chunks_ingested"] == 0

    @pytest.mark.asyncio
    @patch("api.conversations.get_conversation", new_callable=AsyncMock)
    @patch("api.conversations.list_messages", new_callable=AsyncMock)
    @patch("api.conversations.create_kb_entry", new_callable=AsyncMock, return_value="kb_entry_2")
    @patch("api.conversations.update_conversation", new_callable=AsyncMock)
    @patch("api.conversations.log_audit", new_callable=AsyncMock)
    async def test_ingestion_error_does_not_block_resolve(
        self, mock_audit, mock_update, mock_create_kb, mock_list_msgs, mock_get_conv
    ):
        """
        If Endee ingestion fails, the conversation must still be marked resolved.
        The error is logged but not propagated to the caller.
        """
        mock_get_conv.return_value = _make_conversation()
        mock_list_msgs.return_value = [
            {"sender_type": "customer", "content": "Question"}
        ]

        with patch("services.ingestion.ingest_resolved_ticket", new_callable=AsyncMock,
                   side_effect=Exception("Endee unreachable")):

            result = await resolve_conv(
                "conv_1",
                ResolveRequest(
                    canonical_answer="The answer.",
                    ingest_to_kb=True,
                ),
                user=_staff_user(),
            )

        # Conversation is still resolved despite ingestion failure
        assert result["status"] == "resolved"
        mock_update.assert_called_once()
        update_data = mock_update.call_args[0][1]
        assert update_data["status"] == "resolved"

    @pytest.mark.asyncio
    @patch("api.conversations.get_conversation", new_callable=AsyncMock)
    @patch("api.conversations.list_messages", new_callable=AsyncMock)
    @patch("api.conversations.create_kb_entry", new_callable=AsyncMock, return_value="kb_3")
    @patch("api.conversations.update_conversation", new_callable=AsyncMock)
    @patch("api.conversations.log_audit", new_callable=AsyncMock)
    async def test_title_auto_generated_from_customer_question(
        self, mock_audit, mock_update, mock_create_kb, mock_list_msgs, mock_get_conv
    ):
        """
        When no title is supplied, the KB entry title is derived from the
        first customer message.
        """
        mock_get_conv.return_value = _make_conversation()
        mock_list_msgs.return_value = [
            {"sender_type": "customer", "content": "My payment keeps failing at checkout"}
        ]

        with patch("services.ingestion.ingest_resolved_ticket", new_callable=AsyncMock,
                   return_value={"doc_id": "d1", "chunk_count": 1}), \
             patch("api.conversations.set_kb_entry_doc_id", new_callable=AsyncMock):

            await resolve_conv(
                "conv_1",
                ResolveRequest(
                    canonical_answer="Check card details and retry.",
                    title="",  # No explicit title
                    ingest_to_kb=True,
                ),
                user=_staff_user(),
            )

        # The KB entry was created with aTitle that starts with "Resolved:"
        kb_call_kwargs = mock_create_kb.call_args[0][0]
        assert kb_call_kwargs.title.startswith("Resolved:")
        assert "payment" in kb_call_kwargs.title.lower()


# =============================================================================
# Admin KB CRUD
# =============================================================================

class TestAdminKBCRUD:

    @pytest.mark.asyncio
    @patch("api.admin.list_kb_entries", new_callable=AsyncMock)
    async def test_admin_can_list_kb_entries(self, mock_list):
        """Admin can list KB entries for their company."""
        mock_list.return_value = [
            {"entry_id": "kb_1", "title": "Password Reset", "verified": True},
            {"entry_id": "kb_2", "title": "Billing FAQ", "verified": False},
        ]

        result = await list_kb(user=_admin_user())

        assert "kb_entries" in result
        assert result["total"] == 2
        mock_list.assert_called_once_with("co_123")

    @pytest.mark.asyncio
    @patch("api.admin.update_kb_entry", new_callable=AsyncMock, return_value=True)
    async def test_admin_can_update_kb_entry(self, mock_update):
        """Admin can update a KB entry's canonical answer."""
        result = await update_kb(
            "kb_1",
            UpdateKBEntryRequest(canonical_answer="Updated answer.", verified=True),
            user=_admin_user(),
        )

        assert result["status"] == "updated"
        assert result["entry_id"] == "kb_1"
        mock_update.assert_called_once()

    @pytest.mark.asyncio
    @patch("api.admin.update_kb_entry", new_callable=AsyncMock, return_value=False)
    async def test_update_nonexistent_kb_raises_404(self, mock_update):
        """Updating a non-existent KB entry must return 404."""
        with pytest.raises(HTTPException) as exc_info:
            await update_kb(
                "kb_ghost",
                UpdateKBEntryRequest(title="X"),
                user=_admin_user(),
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    @patch("api.admin.delete_kb_entry", new_callable=AsyncMock, return_value=True)
    async def test_admin_can_delete_kb_entry(self, mock_delete):
        """Admin can delete a KB entry."""
        result = await delete_kb("kb_1", user=_admin_user())
        assert result["status"] == "deleted"
        assert result["entry_id"] == "kb_1"

    @pytest.mark.asyncio
    @patch("api.admin.delete_kb_entry", new_callable=AsyncMock, return_value=False)
    async def test_delete_nonexistent_kb_raises_404(self, mock_delete):
        """Deleting a non-existent KB entry must return 404."""
        with pytest.raises(HTTPException) as exc_info:
            await delete_kb("kb_ghost", user=_admin_user())
        assert exc_info.value.status_code == 404


# =============================================================================
# RBAC: Staff cannot access admin KB endpoints
# =============================================================================

class TestKBEntryRBAC:

    @pytest.mark.asyncio
    async def test_staff_blocked_from_kb_list(self):
        """Staff role must be rejected by require_admin on KB list."""
        from api.auth import require_admin
        staff = {"role": "staff", "user_id": "s1", "company_id": "co_123"}
        with pytest.raises(HTTPException) as exc_info:
            await require_admin(user=staff)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_staff_blocked_from_kb_delete(self):
        """Staff role must be rejected by require_admin on KB delete."""
        from api.auth import require_admin
        staff = {"role": "staff", "user_id": "s1", "company_id": "co_123"}
        with pytest.raises(HTTPException) as exc_info:
            await require_admin(user=staff)
        assert exc_info.value.status_code == 403


# =============================================================================
# Learning Loop Integration: Resolved KB boosts orchestrator auto-reply
# =============================================================================

class TestLearningLoopOrchestrator:
    """
    Verifies that a KB entry with is_resolved="true" in its Endee metadata
    is scored with intent_match=True unconditionally, enabling the orchestrator
    to auto_reply on similar future questions.
    """

    @pytest.mark.asyncio
    @patch("services.orchestrator.llm_service")
    @patch("services.orchestrator.embedding_service")
    @patch("services.orchestrator.endee_client")
    @patch("services.orchestrator.log_audit", new_callable=AsyncMock)
    async def test_resolved_kb_entry_triggers_auto_reply(
        self, mock_audit, mock_endee, mock_emb, mock_llm
    ):
        """
        A resolved KB entry (is_resolved='true') with similarity >= 0.70
        should cross the auto_resolve_threshold after intent_match boost.
        """
        mock_llm.classify_intent = AsyncMock(return_value="billing")
        mock_llm.generate_rag_response = AsyncMock(
            return_value="Go to Settings > Billing to update your payment info."
        )
        mock_emb.encode = MagicMock(return_value=[0.1] * 384)
        mock_endee.search = MagicMock(return_value=[
            {
                "id": "vec_kb_1",
                "similarity": 0.88,
                "meta": {
                    "company_id": "co_123",
                    "ticket_id": "kb_entry_1",
                    "raw_text": "Go to Settings > Billing to update your payment info.",
                    "category": "billing",
                    "is_resolved": "true",
                    "source_type": "ticket_resolution",
                },
            }
        ])

        result = await process_conversation_message(
            customer_message="How do I update my payment method?",
            company_id="co_123",
            conversation_id="conv_1",
            company_settings={
                "auto_resolve_threshold": 0.82,
                "clarify_threshold": 0.60,
            },
        )

        assert result.action == "auto_reply", (
            f"Expected auto_reply but got {result.action} (confidence={result.confidence})"
        )
        assert result.confidence >= 0.82

    @pytest.mark.asyncio
    @patch("services.orchestrator.llm_service")
    @patch("services.orchestrator.embedding_service")
    @patch("services.orchestrator.endee_client")
    @patch("services.orchestrator.log_audit", new_callable=AsyncMock)
    async def test_resolved_kb_cross_category_still_auto_replies(
        self, mock_audit, mock_endee, mock_emb, mock_llm
    ):
        """
        A resolved KB entry categorised as 'general' but queried with intent
        'billing' should still auto-reply (intent_match=True for resolved entries),
        rather than being penalised for the category mismatch.

        This is the core fix for Bug #6 (learning loop).
        """
        mock_llm.classify_intent = AsyncMock(return_value="billing")
        mock_llm.generate_rag_response = AsyncMock(
            return_value="Resolved answer for billing query."
        )
        mock_emb.encode = MagicMock(return_value=[0.1] * 384)
        mock_endee.search = MagicMock(return_value=[
            {
                "id": "vec_kb_2",
                "similarity": 0.85,
                "meta": {
                    "company_id": "co_123",
                    "ticket_id": "kb_entry_2",
                    "raw_text": "Resolved billing issue - staff approved answer.",
                    "category": "general",    # category mismatch vs intent "billing"
                    "is_resolved": "true",    # but this is a human-verified resolution
                    "source_type": "ticket_resolution",
                },
            }
        ])

        result = await process_conversation_message(
            customer_message="My billing statement is wrong",
            company_id="co_123",
            conversation_id="conv_2",
            company_settings={
                "auto_resolve_threshold": 0.82,
                "clarify_threshold": 0.60,
            },
        )

        assert result.action == "auto_reply", (
            f"Resolved KB entry should override category mismatch. "
            f"Got {result.action} (confidence={result.confidence})"
        )

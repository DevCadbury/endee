# =============================================================================
# tests/test_conversations.py — Conversation Lifecycle Tests
# =============================================================================
# Covers:
#   - Widget: open (new / resume / post-resolve), message flow, deletion guard
#   - Widget: orchestrator action routing (auto_reply → resolve, escalate → keep active)
#   - Widget: session ownership validation
#   - Staff: reply, assign, resolve, escalate
#   - Cross-company access enforcement (403)
# =============================================================================

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone
from fastapi import HTTPException

from services.orchestrator import OrchestratorResult
from api.widget import (
    open_conversation,
    send_message,
    delete_conversation,
    OpenConversationRequest,
    CustomerMessageRequest,
)
from api.conversations import (
    list_convs,
    get_conv,
    staff_reply,
    assign_conv,
    resolve_conv,
    escalate_conv,
    StaffMessageRequest,
    AssignRequest,
    ResolveRequest,
    EscalateRequest,
)


# =============================================================================
# Shared Fixtures / Helpers
# =============================================================================

def _make_company(company_id="co_123", slug="acme"):
    return {"_id": company_id, "company_id": company_id, "name": "Acme", "slug": slug, "settings": {}}


def _make_conversation(
    conv_id="conv_1",
    company_id="co_123",
    customer_id="session_abc",
    status="active",
):
    return {
        "_id": conv_id,
        "company_id": company_id,
        "customer_id": customer_id,
        "widget_session_id": customer_id,
        "status": status,
        "assigned_staff_id": "",
    }


def _admin_user(company_id="co_123"):
    return {"role": "admin", "user_id": "admin_1", "company_id": company_id}


def _staff_user(company_id="co_123"):
    return {"role": "staff", "user_id": "staff_1", "company_id": company_id}


def _auto_reply_result():
    return OrchestratorResult(
        action="auto_reply",
        message="Your invoice is in the account panel.",
        sources=["KB-001"],
        confidence=0.92,
        intent="billing",
    )


def _escalate_result():
    return OrchestratorResult(
        action="escalate",
        message="Let me connect you with a team member.",
        sources=[],
        confidence=0.40,
        intent="general",
        context_passed_to_agent=True,
    )


# =============================================================================
# Widget: open_conversation
# =============================================================================

class TestWidgetOpenConversation:

    @pytest.mark.asyncio
    @patch("api.widget.get_company_by_slug", new_callable=AsyncMock)
    @patch("api.widget.get_active_conversation", new_callable=AsyncMock, return_value=None)
    @patch("api.widget.create_conversation", new_callable=AsyncMock, return_value="conv_new")
    async def test_creates_new_conversation_when_none_active(
        self, mock_create, mock_get_active, mock_get_company
    ):
        """First open call creates a new conversation."""
        mock_get_company.return_value = _make_company()

        result = await open_conversation(
            "acme",
            OpenConversationRequest(widget_session_id="session_abc"),
        )

        assert result["is_new"] is True
        assert result["conversation_id"] == "conv_new"
        assert result["status"] == "active"
        mock_create.assert_called_once()

    @pytest.mark.asyncio
    @patch("api.widget.get_company_by_slug", new_callable=AsyncMock)
    @patch("api.widget.get_active_conversation", new_callable=AsyncMock)
    @patch("api.widget.list_messages", new_callable=AsyncMock, return_value=[])
    async def test_returns_existing_active_conversation(
        self, mock_messages, mock_get_active, mock_get_company
    ):
        """Second open call with same session_id returns existing conversation."""
        mock_get_company.return_value = _make_company()
        mock_get_active.return_value = _make_conversation()

        result = await open_conversation(
            "acme",
            OpenConversationRequest(widget_session_id="session_abc"),
        )

        assert result["is_new"] is False
        assert result["conversation_id"] == "conv_1"
        assert result["status"] == "active"

    @pytest.mark.asyncio
    @patch("api.widget.get_company_by_slug", new_callable=AsyncMock, return_value=None)
    async def test_unknown_slug_raises_404(self, mock_get_company):
        """Unknown company slug must return 404."""
        with pytest.raises(HTTPException) as exc_info:
            await open_conversation(
                "no-such-company",
                OpenConversationRequest(widget_session_id="s1"),
            )
        assert exc_info.value.status_code == 404


# =============================================================================
# Widget: send_message
# =============================================================================

class TestWidgetSendMessage:

    @pytest.mark.asyncio
    async def test_empty_content_raises_400(self):
        """Whitespace-only message must be rejected."""
        with pytest.raises(HTTPException) as exc_info:
            await send_message(
                "acme",
                CustomerMessageRequest(conversation_id="conv_1", content="   "),
                x_session_id="session_abc",
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    @patch("api.widget.get_company_by_slug", new_callable=AsyncMock)
    @patch("api.widget.get_conversation", new_callable=AsyncMock)
    async def test_session_mismatch_raises_403(self, mock_get_conv, mock_get_company):
        """X-Session-Id that doesn't match conversation.customer_id must return 403."""
        mock_get_company.return_value = _make_company()
        mock_get_conv.return_value = _make_conversation(customer_id="real_session")

        with pytest.raises(HTTPException) as exc_info:
            await send_message(
                "acme",
                CustomerMessageRequest(conversation_id="conv_1", content="Hello"),
                x_session_id="impostor_session",
            )
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    @patch("api.widget.get_company_by_slug", new_callable=AsyncMock)
    @patch("api.widget.get_conversation", new_callable=AsyncMock)
    async def test_resolved_conversation_raises_409(self, mock_get_conv, mock_get_company):
        """Sending a message to a resolved conversation must return 409."""
        mock_get_company.return_value = _make_company()
        mock_get_conv.return_value = _make_conversation(status="resolved")

        with pytest.raises(HTTPException) as exc_info:
            await send_message(
                "acme",
                CustomerMessageRequest(conversation_id="conv_1", content="Still here"),
                x_session_id="session_abc",
            )
        assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    @patch("api.widget.get_company_by_slug", new_callable=AsyncMock)
    @patch("api.widget.get_conversation", new_callable=AsyncMock)
    @patch("api.widget.create_message", new_callable=AsyncMock, return_value="msg_1")
    @patch("api.widget.process_conversation_message", new_callable=AsyncMock)
    @patch("api.widget.update_conversation", new_callable=AsyncMock)
    @patch("api.widget.log_audit", new_callable=AsyncMock)
    async def test_auto_reply_resolves_conversation(
        self, mock_audit, mock_update, mock_process, mock_create_msg, mock_get_conv, mock_get_company
    ):
        """
        auto_reply action + auto_resolve_auto_close=True (default) should mark
        the conversation as resolved.
        """
        mock_get_company.return_value = _make_company()
        mock_get_conv.return_value = _make_conversation()
        mock_process.return_value = _auto_reply_result()

        result = await send_message(
            "acme",
            CustomerMessageRequest(conversation_id="conv_1", content="Where is my invoice?"),
            x_session_id="session_abc",
        )

        assert result["action"] == "auto_reply"
        assert result["conversation_status"] == "resolved"
        # update_conversation should have been called with status=resolved
        mock_update.assert_called_once()
        call_args = mock_update.call_args[0]
        assert call_args[1]["status"] == "resolved"

    @pytest.mark.asyncio
    @patch("api.widget.get_company_by_slug", new_callable=AsyncMock)
    @patch("api.widget.get_conversation", new_callable=AsyncMock)
    @patch("api.widget.create_message", new_callable=AsyncMock, return_value="msg_1")
    @patch("api.widget.process_conversation_message", new_callable=AsyncMock)
    @patch("api.widget.update_conversation", new_callable=AsyncMock)
    @patch("api.widget.log_audit", new_callable=AsyncMock)
    async def test_escalate_keeps_conversation_active(
        self, mock_audit, mock_update, mock_process, mock_create_msg, mock_get_conv, mock_get_company
    ):
        """Escalated messages must leave the conversation active."""
        mock_get_company.return_value = _make_company()
        mock_get_conv.return_value = _make_conversation()
        mock_process.return_value = _escalate_result()

        result = await send_message(
            "acme",
            CustomerMessageRequest(conversation_id="conv_1", content="My problem is complex"),
            x_session_id="session_abc",
        )

        assert result["action"] == "escalate"
        assert result["conversation_status"] == "active"
        assert result["context_passed_to_agent"] is True
        # No status update should have happened
        mock_update.assert_not_called()

    @pytest.mark.asyncio
    @patch("api.widget.get_company_by_slug", new_callable=AsyncMock)
    @patch("api.widget.get_conversation", new_callable=AsyncMock)
    @patch("api.widget.create_message", new_callable=AsyncMock, return_value="msg_1")
    @patch("api.widget.process_conversation_message", new_callable=AsyncMock,
           side_effect=Exception("Orchestrator crashed"))
    @patch("api.widget.update_conversation", new_callable=AsyncMock)
    @patch("api.widget.log_audit", new_callable=AsyncMock)
    async def test_orchestrator_failure_gracefully_escalates(
        self, mock_audit, mock_update, mock_process, mock_create_msg, mock_get_conv, mock_get_company
    ):
        """If orchestrator raises, the widget falls back to escalate gracefully."""
        mock_get_company.return_value = _make_company()
        mock_get_conv.return_value = _make_conversation()

        result = await send_message(
            "acme",
            CustomerMessageRequest(conversation_id="conv_1", content="Test"),
            x_session_id="session_abc",
        )

        assert result["action"] == "escalate"
        assert "wrong" in result["message"].lower() or "member" in result["message"].lower()


# =============================================================================
# Widget: delete_conversation
# =============================================================================

class TestWidgetDeleteConversation:

    @pytest.mark.asyncio
    @patch("api.widget.get_company_by_slug", new_callable=AsyncMock)
    @patch("api.widget.delete_conversation_user_side", new_callable=AsyncMock)
    async def test_delete_resolved_conversation_succeeds(self, mock_delete, mock_get_company):
        """Deleting a resolved conversation should succeed."""
        mock_get_company.return_value = _make_company()
        mock_delete.return_value = {"deleted": True}

        result = await delete_conversation("acme", "conv_1", x_session_id="s1")
        assert result["status"] == "deleted"

    @pytest.mark.asyncio
    @patch("api.widget.get_company_by_slug", new_callable=AsyncMock)
    @patch("api.widget.delete_conversation_user_side", new_callable=AsyncMock)
    async def test_delete_active_conversation_raises_409(self, mock_delete, mock_get_company):
        """Deleting an active conversation must return 409."""
        mock_get_company.return_value = _make_company()
        mock_delete.return_value = {"error": "not_resolved"}

        with pytest.raises(HTTPException) as exc_info:
            await delete_conversation("acme", "conv_1", x_session_id="s1")
        assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    @patch("api.widget.get_company_by_slug", new_callable=AsyncMock)
    @patch("api.widget.delete_conversation_user_side", new_callable=AsyncMock)
    async def test_delete_nonexistent_conversation_raises_404(self, mock_delete, mock_get_company):
        """Deleting a non-existent conversation must return 404."""
        mock_get_company.return_value = _make_company()
        mock_delete.return_value = {"error": "not_found"}

        with pytest.raises(HTTPException) as exc_info:
            await delete_conversation("acme", "conv_999", x_session_id="s1")
        assert exc_info.value.status_code == 404


# =============================================================================
# Staff: reply
# =============================================================================

class TestStaffReply:

    @pytest.mark.asyncio
    @patch("api.conversations.get_conversation", new_callable=AsyncMock)
    @patch("api.conversations.create_message", new_callable=AsyncMock, return_value="msg_2")
    @patch("api.conversations.log_audit", new_callable=AsyncMock)
    async def test_staff_reply_persists_message(self, mock_audit, mock_create_msg, mock_get_conv):
        """Staff reply should persist a message and return its ID."""
        mock_get_conv.return_value = _make_conversation()

        result = await staff_reply(
            "conv_1",
            StaffMessageRequest(content="I can help with that."),
            user=_staff_user(),
        )

        assert result["message_id"] == "msg_2"
        mock_create_msg.assert_called_once()

    @pytest.mark.asyncio
    @patch("api.conversations.get_conversation", new_callable=AsyncMock)
    async def test_staff_reply_on_resolved_raises_409(self, mock_get_conv):
        """Staff cannot reply to a resolved conversation."""
        mock_get_conv.return_value = _make_conversation(status="resolved")

        with pytest.raises(HTTPException) as exc_info:
            await staff_reply(
                "conv_1",
                StaffMessageRequest(content="Late reply"),
                user=_staff_user(),
            )
        assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    @patch("api.conversations.get_conversation", new_callable=AsyncMock)
    async def test_empty_staff_reply_raises_400(self, mock_get_conv):
        """Empty staff reply must be rejected."""
        mock_get_conv.return_value = _make_conversation()

        with pytest.raises(HTTPException) as exc_info:
            await staff_reply(
                "conv_1",
                StaffMessageRequest(content=""),
                user=_staff_user(),
            )
        assert exc_info.value.status_code == 400


# =============================================================================
# Staff: assign
# =============================================================================

class TestStaffAssign:

    @pytest.mark.asyncio
    @patch("api.conversations.get_conversation", new_callable=AsyncMock)
    @patch("api.conversations.update_conversation", new_callable=AsyncMock, return_value=True)
    async def test_assign_conversation(self, mock_update, mock_get_conv):
        """Admin can assign a conversation to a staff member."""
        mock_get_conv.return_value = _make_conversation()

        result = await assign_conv(
            "conv_1",
            AssignRequest(staff_user_id="staff_99"),
            user=_admin_user(),
        )

        assert result["status"] == "assigned"
        assert result["assigned_to"] == "staff_99"
        mock_update.assert_called_once_with("conv_1", {"assigned_staff_id": "staff_99"})


# =============================================================================
# Staff: resolve
# =============================================================================

class TestStaffResolve:

    @pytest.mark.asyncio
    @patch("api.conversations.get_conversation", new_callable=AsyncMock)
    @patch("api.conversations.list_messages", new_callable=AsyncMock)
    @patch("api.conversations.create_kb_entry", new_callable=AsyncMock, return_value="kb_1")
    @patch("api.conversations.update_conversation", new_callable=AsyncMock)
    @patch("api.conversations.log_audit", new_callable=AsyncMock)
    async def test_resolve_with_ingest_creates_kb_entry(
        self, mock_audit, mock_update, mock_create_kb, mock_list_msgs, mock_get_conv
    ):
        """Resolving with ingest_to_kb=True should create a KB entry."""
        mock_get_conv.return_value = _make_conversation()
        mock_list_msgs.return_value = [
            {"sender_type": "customer", "content": "How do I reset my password?"}
        ]

        with patch("services.ingestion.ingest_resolved_ticket", new_callable=AsyncMock,
                   return_value={"doc_id": "doc_xyz", "chunk_count": 2}) as mock_ingest, \
             patch("api.conversations.set_kb_entry_doc_id", new_callable=AsyncMock):

            result = await resolve_conv(
                "conv_1",
                ResolveRequest(
                    canonical_answer="Click 'Forgot Password' on the login page.",
                    ingest_to_kb=True,
                ),
                user=_staff_user(),
            )

        assert result["status"] == "resolved"
        assert result["kb_entry_id"] == "kb_1"
        assert result["kb_ingested"] is True
        mock_create_kb.assert_called_once()

    @pytest.mark.asyncio
    @patch("api.conversations.get_conversation", new_callable=AsyncMock)
    @patch("api.conversations.list_messages", new_callable=AsyncMock, return_value=[])
    @patch("api.conversations.create_kb_entry", new_callable=AsyncMock, return_value="kb_1")
    @patch("api.conversations.update_conversation", new_callable=AsyncMock)
    @patch("api.conversations.log_audit", new_callable=AsyncMock)
    async def test_resolve_without_ingest_skips_kb_entry(
        self, mock_audit, mock_update, mock_create_kb, mock_list_msgs, mock_get_conv
    ):
        """Resolving with ingest_to_kb=False should NOT create a KB entry."""
        mock_get_conv.return_value = _make_conversation()

        result = await resolve_conv(
            "conv_1",
            ResolveRequest(
                canonical_answer="The answer is 42.",
                ingest_to_kb=False,
            ),
            user=_staff_user(),
        )

        assert result["status"] == "resolved"
        assert result["kb_entry_id"] is None
        assert result["kb_ingested"] is False
        # KB entry should NOT have been created
        mock_create_kb.assert_not_called()

    @pytest.mark.asyncio
    @patch("api.conversations.get_conversation", new_callable=AsyncMock)
    async def test_resolve_already_resolved_raises_409(self, mock_get_conv):
        """Cannot resolve an already-resolved conversation."""
        mock_get_conv.return_value = _make_conversation(status="resolved")

        with pytest.raises(HTTPException) as exc_info:
            await resolve_conv(
                "conv_1",
                ResolveRequest(canonical_answer="Too late."),
                user=_staff_user(),
            )
        assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    @patch("api.conversations.get_conversation", new_callable=AsyncMock)
    async def test_resolve_empty_answer_raises_400(self, mock_get_conv):
        """canonical_answer cannot be empty."""
        mock_get_conv.return_value = _make_conversation()

        with pytest.raises(HTTPException) as exc_info:
            await resolve_conv(
                "conv_1",
                ResolveRequest(canonical_answer="  "),
                user=_staff_user(),
            )
        assert exc_info.value.status_code == 400


# =============================================================================
# Staff: escalate
# =============================================================================

class TestStaffEscalate:

    @pytest.mark.asyncio
    @patch("api.conversations.get_conversation", new_callable=AsyncMock)
    @patch("api.conversations.update_conversation", new_callable=AsyncMock)
    @patch("api.conversations.create_message", new_callable=AsyncMock)
    @patch("api.conversations.log_audit", new_callable=AsyncMock)
    async def test_escalate_clears_assignment(
        self, mock_audit, mock_create_msg, mock_update, mock_get_conv
    ):
        """Escalating should clear the assigned_staff_id."""
        mock_get_conv.return_value = _make_conversation()

        result = await escalate_conv(
            "conv_1",
            EscalateRequest(reason="Needs senior engineer"),
            user=_staff_user(),
        )

        assert result["status"] == "escalated"
        mock_update.assert_called_once_with("conv_1", {"assigned_staff_id": ""})

    @pytest.mark.asyncio
    @patch("api.conversations.get_conversation", new_callable=AsyncMock)
    async def test_escalate_resolved_raises_409(self, mock_get_conv):
        """Cannot escalate a resolved conversation."""
        mock_get_conv.return_value = _make_conversation(status="resolved")

        with pytest.raises(HTTPException) as exc_info:
            await escalate_conv(
                "conv_1",
                EscalateRequest(),
                user=_staff_user(),
            )
        assert exc_info.value.status_code == 409


# =============================================================================
# Cross-Company Access
# =============================================================================

class TestCrossCompanyIsolation:

    @pytest.mark.asyncio
    @patch("api.conversations.get_conversation", new_callable=AsyncMock)
    async def test_cross_company_conversation_raises_403(self, mock_get_conv):
        """User from company B must not access company A's conversation."""
        # Conversation belongs to co_A
        mock_get_conv.return_value = _make_conversation(company_id="co_A")

        # User is from co_B
        user_from_co_b = {"role": "admin", "user_id": "u2", "company_id": "co_B"}

        with pytest.raises(HTTPException) as exc_info:
            await get_conv("conv_1", user=user_from_co_b)
        assert exc_info.value.status_code == 403

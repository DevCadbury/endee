# =============================================================================
# tests/test_websocket.py — WebSocket Real-Time Chat Tests
# =============================================================================
# Covers:
#   - ConnectionManager: connect, disconnect, broadcast, subscribe/unsubscribe
#   - Widget WS: company validation, conversation creation, message flow,
#                orchestrator integration, auto-resolve broadcast
#   - Staff WS: JWT validation, room join/leave, bidirectional message send,
#               typing indicators, new-conversation notification
#   - Cross-company isolation on WS (staff cannot join other company's room)
#   - REST endpoint WS broadcast (widget.py and conversations.py both emit)
# =============================================================================

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import WebSocketDisconnect
from fastapi.testclient import TestClient

from services.connection_manager import ConnectionManager
from api.auth import create_jwt_token
from api.ws import widget_ws, staff_ws


# =============================================================================
# Mock WebSocket helper
# =============================================================================

class MockWebSocket:
    """
    Minimal mock for FastAPI WebSocket used in handler unit tests.
    Drives the receive loop via a pre-set queue of messages.
    """
    def __init__(self, inbound_messages: list = None):
        self.accepted = False
        self.closed = False
        self.close_code: int | None = None
        self.close_reason: str | None = None
        self.sent: list[dict] = []
        self._inbound = list(inbound_messages or [])

    async def accept(self):
        self.accepted = True

    async def send_json(self, data: dict):
        self.sent.append(data)

    async def receive_json(self):
        if self._inbound:
            return self._inbound.pop(0)
        raise WebSocketDisconnect(code=1000)

    async def close(self, code: int = 1000, reason: str = ""):
        self.closed = True
        self.close_code = code
        self.close_reason = reason

    def find(self, msg_type: str) -> dict | None:
        return next((m for m in self.sent if m.get("type") == msg_type), None)

    def find_all(self, msg_type: str) -> list[dict]:
        return [m for m in self.sent if m.get("type") == msg_type]


# =============================================================================
# ConnectionManager Unit Tests
# =============================================================================

class TestConnectionManager:
    """Pure unit tests — no DB or WS connections needed."""

    @pytest.fixture
    def cm(self):
        return ConnectionManager()

    @pytest.mark.asyncio
    async def test_connect_widget_registers_in_conv_room(self, cm):
        ws = MockWebSocket()
        await cm.connect_widget(ws, conv_id="conv_1", company_id="co_1", session_id="s_1")
        assert ws in cm._conv_rooms["conv_1"]
        meta = cm._meta[ws]
        assert meta["role"] == "customer"
        assert meta["session_id"] == "s_1"

    @pytest.mark.asyncio
    async def test_connect_staff_registers_in_company_channel(self, cm):
        ws = MockWebSocket()
        await cm.connect_staff(ws, company_id="co_1", user_id="u_1", role="staff")
        assert ws in cm._company_staff["co_1"]
        assert cm._meta[ws]["role"] == "staff"

    @pytest.mark.asyncio
    async def test_disconnect_removes_from_all_rooms(self, cm):
        ws = MockWebSocket()
        await cm.connect_staff(ws, company_id="co_1", user_id="u_1", role="admin")
        await cm.subscribe_to_conv(ws, "conv_1")
        await cm.subscribe_to_conv(ws, "conv_2")

        await cm.disconnect(ws)

        assert ws not in cm._company_staff["co_1"]
        assert ws not in cm._conv_rooms.get("conv_1", set())
        assert ws not in cm._conv_rooms.get("conv_2", set())
        assert ws not in cm._meta

    @pytest.mark.asyncio
    async def test_subscribe_adds_to_conv_room(self, cm):
        ws = MockWebSocket()
        await cm.connect_staff(ws, company_id="co_1", user_id="u_1", role="staff")
        await cm.subscribe_to_conv(ws, "conv_99")
        assert ws in cm._conv_rooms["conv_99"]

    @pytest.mark.asyncio
    async def test_unsubscribe_removes_from_conv_room(self, cm):
        ws = MockWebSocket()
        await cm.connect_staff(ws, company_id="co_1", user_id="u_1", role="staff")
        await cm.subscribe_to_conv(ws, "conv_5")
        await cm.unsubscribe_from_conv(ws, "conv_5")
        assert ws not in cm._conv_rooms["conv_5"]

    @pytest.mark.asyncio
    async def test_broadcast_to_conv_sends_to_all_participants(self, cm):
        ws1 = MockWebSocket()
        ws2 = MockWebSocket()
        await cm.connect_widget(ws1, "conv_x", "co_1", "session_1")
        await cm.connect_staff(ws2, "co_1", "u_1", "staff")
        await cm.subscribe_to_conv(ws2, "conv_x")

        await cm.broadcast_to_conv("conv_x", {"type": "test_event"})

        assert ws1.sent[-1] == {"type": "test_event"}
        assert ws2.sent[-1] == {"type": "test_event"}

    @pytest.mark.asyncio
    async def test_broadcast_to_conv_respects_exclude(self, cm):
        ws1 = MockWebSocket()
        ws2 = MockWebSocket()
        await cm.connect_widget(ws1, "conv_x", "co_1", "session_1")
        await cm.connect_staff(ws2, "co_1", "u_1", "staff")
        await cm.subscribe_to_conv(ws2, "conv_x")

        await cm.broadcast_to_conv("conv_x", {"type": "msg"}, exclude=ws1)

        assert not any(m.get("type") == "msg" for m in ws1.sent)
        assert ws2.sent[-1]["type"] == "msg"

    @pytest.mark.asyncio
    async def test_broadcast_to_company_staff_reaches_all_staff(self, cm):
        ws1 = MockWebSocket()
        ws2 = MockWebSocket()
        await cm.connect_staff(ws1, "co_1", "u_1", "staff")
        await cm.connect_staff(ws2, "co_1", "u_2", "admin")

        await cm.broadcast_to_company_staff("co_1", {"type": "new_conversation"})

        assert ws1.sent[-1]["type"] == "new_conversation"
        assert ws2.sent[-1]["type"] == "new_conversation"

    @pytest.mark.asyncio
    async def test_broadcast_to_company_staff_does_not_reach_other_company(self, cm):
        ws_co1 = MockWebSocket()
        ws_co2 = MockWebSocket()
        await cm.connect_staff(ws_co1, "co_1", "u_1", "staff")
        await cm.connect_staff(ws_co2, "co_2", "u_2", "staff")

        await cm.broadcast_to_company_staff("co_1", {"type": "secret"})

        assert any(m.get("type") == "secret" for m in ws_co1.sent)
        assert not any(m.get("type") == "secret" for m in ws_co2.sent)

    @pytest.mark.asyncio
    async def test_dead_connection_gc_on_broadcast(self, cm):
        """GC: connections that raise on send_json are removed from rooms."""
        ws_good = MockWebSocket()
        ws_dead = MockWebSocket()

        # Override send_json to fail on ws_dead
        async def broken_send(data):
            raise OSError("connection closed")
        ws_dead.send_json = broken_send

        await cm.connect_widget(ws_good, "conv_1", "co_1", "s1")
        await cm.connect_widget(ws_dead, "conv_1", "co_1", "s2")

        await cm.broadcast_to_conv("conv_1", {"type": "alive"})

        assert ws_good.sent[-1]["type"] == "alive"
        assert ws_dead not in cm._conv_rooms.get("conv_1", set())

    def test_company_staff_online_count(self, cm):
        assert cm.company_staff_online("co_1") == 0

    @pytest.mark.asyncio
    async def test_company_staff_online_count_after_connect(self, cm):
        ws = MockWebSocket()
        await cm.connect_staff(ws, "co_1", "u_1", "staff")
        assert cm.company_staff_online("co_1") == 1

    @pytest.mark.asyncio
    async def test_get_conv_participants(self, cm):
        ws1 = MockWebSocket()
        ws2 = MockWebSocket()
        await cm.connect_widget(ws1, "conv_1", "co_1", "cust_session")
        await cm.connect_staff(ws2, "co_1", "u_1", "staff")
        await cm.subscribe_to_conv(ws2, "conv_1")

        participants = cm.get_conv_participants("conv_1")
        roles = [p["role"] for p in participants]
        assert "customer" in roles
        assert "staff" in roles


# =============================================================================
# Widget WS Handler Unit Tests
# =============================================================================

class TestWidgetWebSocket:

    @pytest.mark.asyncio
    @patch("api.ws.get_company_by_slug", new_callable=AsyncMock, return_value=None)
    async def test_unknown_company_closes_4004(self, mock_get_company):
        """Unknown slug must close with code 4004."""
        from api.ws import widget_ws
        ws = MockWebSocket()

        await widget_ws(ws, slug="ghost-co", session_id="s1")

        assert ws.closed
        assert ws.close_code == 4004

    @pytest.mark.asyncio
    @patch("api.ws.get_company_by_slug", new_callable=AsyncMock)
    @patch("api.ws.get_active_conversation", new_callable=AsyncMock, return_value=None)
    @patch("api.ws.create_conversation", new_callable=AsyncMock, return_value="conv_new")
    @patch("api.ws.list_messages", new_callable=AsyncMock, return_value=[])
    async def test_new_conversation_created_on_connect(
        self, mock_msgs, mock_create, mock_active, mock_company
    ):
        """Widget connects with no existing conversation → new conv created."""
        mock_company.return_value = {"company_id": "co_1", "name": "Acme", "settings": {}}

        ws = MockWebSocket(inbound_messages=[])  # No messages → immediate disconnect

        await widget_ws(ws, slug="acme", session_id="new_session", conv_id=None)

        assert ws.accepted
        connected = ws.find("connected")
        assert connected is not None
        assert connected["conv_id"] == "conv_new"
        mock_create.assert_called_once()

    @pytest.mark.asyncio
    @patch("api.ws.get_company_by_slug", new_callable=AsyncMock)
    @patch("api.ws.get_active_conversation", new_callable=AsyncMock)
    @patch("api.ws.list_messages", new_callable=AsyncMock, return_value=[])
    async def test_existing_conversation_resumed(
        self, mock_msgs, mock_active, mock_company
    ):
        """Widget connects with existing active conv → resumed without creating new."""
        mock_company.return_value = {"company_id": "co_1", "name": "Acme", "settings": {}}
        mock_active.return_value = {
            "_id": "conv_existing",
            "company_id": "co_1",
            "customer_id": "session_abc",
            "status": "active",
        }

        ws = MockWebSocket()
        await widget_ws(ws, slug="acme", session_id="session_abc", conv_id=None)

        connected = ws.find("connected")
        assert connected["conv_id"] == "conv_existing"
        assert connected.get("is_new") != True

    @pytest.mark.asyncio
    @patch("api.ws.get_company_by_slug", new_callable=AsyncMock)
    @patch("api.ws.get_active_conversation", new_callable=AsyncMock, return_value=None)
    @patch("api.ws.create_conversation", new_callable=AsyncMock, return_value="conv_1")
    @patch("api.ws.list_messages", new_callable=AsyncMock, return_value=[])
    async def test_ping_returns_pong(self, mock_msgs, mock_create, mock_active, mock_company):
        """{"type":"ping"} → {"type":"pong"}."""
        mock_company.return_value = {"company_id": "co_1", "settings": {}}

        ws = MockWebSocket(inbound_messages=[{"type": "ping"}])
        await widget_ws(ws, slug="acme", session_id="s1", conv_id=None)

        assert ws.find("pong") is not None

    @pytest.mark.asyncio
    @patch("api.ws.get_company_by_slug", new_callable=AsyncMock)
    @patch("api.ws.get_active_conversation", new_callable=AsyncMock, return_value=None)
    @patch("api.ws.create_conversation", new_callable=AsyncMock, return_value="conv_1")
    @patch("api.ws.list_messages", new_callable=AsyncMock, return_value=[])
    @patch("api.ws.get_conversation", new_callable=AsyncMock)
    @patch("api.ws.create_message", new_callable=AsyncMock)
    @patch("api.ws.update_conversation", new_callable=AsyncMock)
    @patch("api.ws.log_audit", new_callable=AsyncMock)
    @patch("api.ws.process_conversation_message", new_callable=AsyncMock)
    async def test_customer_message_runs_orchestrator(
        self, mock_orch, mock_audit, mock_update, mock_create_msg,
        mock_get_conv, mock_msgs, mock_create, mock_active, mock_company
    ):
        """Customer message → orchestrator → AI response broadcast back."""
        from services.orchestrator import OrchestratorResult
        mock_company.return_value = {"company_id": "co_1", "settings": {}}
        mock_get_conv.return_value = {"_id": "conv_1", "company_id": "co_1", "status": "active"}
        mock_create_msg.side_effect = ["cust_msg_1", "ai_msg_1"]
        mock_orch.return_value = OrchestratorResult(
            action="auto_reply",
            message="Your invoice is available in the account portal.",
            sources=["KB-1"],
            confidence=0.95,
        )

        ws = MockWebSocket(inbound_messages=[
            {"type": "message", "content": "Where is my invoice?"}
        ])
        await widget_ws(ws, slug="acme", session_id="s1", conv_id=None)

        # ACK back to sender
        ack = ws.find("message_ack")
        assert ack is not None
        assert ack["sender_type"] == "customer"

        # AI message broadcast
        ai_msgs = [m for m in ws.sent if m.get("type") == "message" and m.get("sender_type") == "ai"]
        assert len(ai_msgs) >= 1
        assert "invoice" in ai_msgs[0]["content"]

    @pytest.mark.asyncio
    @patch("api.ws.get_company_by_slug", new_callable=AsyncMock)
    @patch("api.ws.get_active_conversation", new_callable=AsyncMock, return_value=None)
    @patch("api.ws.create_conversation", new_callable=AsyncMock, return_value="conv_1")
    @patch("api.ws.list_messages", new_callable=AsyncMock, return_value=[])
    @patch("api.ws.get_conversation", new_callable=AsyncMock)
    @patch("api.ws.create_message", new_callable=AsyncMock, side_effect=["c1", "a1"])
    @patch("api.ws.update_conversation", new_callable=AsyncMock)
    @patch("api.ws.log_audit", new_callable=AsyncMock)
    @patch("api.ws.process_conversation_message", new_callable=AsyncMock)
    async def test_auto_reply_triggers_conversation_status_broadcast(
        self, mock_orch, mock_audit, mock_update, mock_create_msg,
        mock_get_conv, mock_msgs, mock_create, mock_active, mock_company
    ):
        """auto_reply + auto_resolve=True → conversation_status resolved broadcast."""
        from services.orchestrator import OrchestratorResult
        mock_company.return_value = {"company_id": "co_1", "settings": {"auto_resolve_auto_close": True}}
        mock_get_conv.return_value = {"_id": "conv_1", "company_id": "co_1", "status": "active"}
        mock_orch.return_value = OrchestratorResult(action="auto_reply", message="Done!", confidence=0.9)

        ws = MockWebSocket(inbound_messages=[{"type": "message", "content": "Help me"}])
        await widget_ws(ws, slug="acme", session_id="s1", conv_id=None)

        status_event = ws.find("conversation_status")
        assert status_event is not None
        assert status_event["new_status"] == "resolved"
        mock_update.assert_called_once()

    @pytest.mark.asyncio
    @patch("api.ws.get_company_by_slug", new_callable=AsyncMock)
    @patch("api.ws.get_active_conversation", new_callable=AsyncMock, return_value=None)
    @patch("api.ws.create_conversation", new_callable=AsyncMock, return_value="conv_1")
    @patch("api.ws.list_messages", new_callable=AsyncMock, return_value=[])
    @patch("api.ws.get_conversation", new_callable=AsyncMock)
    @patch("api.ws.create_message", new_callable=AsyncMock, side_effect=["c1", "a1"])
    @patch("api.ws.update_conversation", new_callable=AsyncMock)
    @patch("api.ws.log_audit", new_callable=AsyncMock)
    @patch("api.ws.process_conversation_message", new_callable=AsyncMock)
    async def test_orchestrator_error_falls_back_to_escalate(
        self, mock_orch, mock_audit, mock_update, mock_create_msg,
        mock_get_conv, mock_msgs, mock_create, mock_active, mock_company
    ):
        """Orchestrator crash → fallback escalate message sent to client."""
        mock_company.return_value = {"company_id": "co_1", "settings": {}}
        mock_get_conv.return_value = {"_id": "conv_1", "company_id": "co_1", "status": "active"}
        mock_orch.side_effect = RuntimeError("LLM unavailable")

        ws = MockWebSocket(inbound_messages=[{"type": "message", "content": "Help"}])
        await widget_ws(ws, slug="acme", session_id="s1", conv_id=None)

        ai_msgs = [m for m in ws.sent if m.get("type") == "message" and m.get("sender_type") == "ai"]
        assert any("team member" in m.get("content", "") for m in ai_msgs)

    @pytest.mark.asyncio
    @patch("api.ws.get_company_by_slug", new_callable=AsyncMock)
    @patch("api.ws.get_active_conversation", new_callable=AsyncMock, return_value=None)
    @patch("api.ws.create_conversation", new_callable=AsyncMock, return_value="conv_1")
    @patch("api.ws.list_messages", new_callable=AsyncMock, return_value=[])
    async def test_empty_message_returns_error(
        self, mock_msgs, mock_create, mock_active, mock_company
    ):
        """{"type":"message","content":""} → {"type":"error","code":"empty_message"}."""
        mock_company.return_value = {"company_id": "co_1", "settings": {}}

        ws = MockWebSocket(inbound_messages=[{"type": "message", "content": "  "}])
        await widget_ws(ws, slug="acme", session_id="s1", conv_id=None)

        error = ws.find("error")
        assert error is not None
        assert error["code"] == "empty_message"


# =============================================================================
# Staff WS Handler Unit Tests
# =============================================================================

class TestStaffWebSocket:

    @pytest.mark.asyncio
    async def test_invalid_jwt_closes_4001(self):
        """Invalid token → close 4001."""
        from api.ws import staff_ws
        ws = MockWebSocket()
        await staff_ws(ws, token="garbage.jwt.token")
        assert ws.closed
        assert ws.close_code == 4001

    @pytest.mark.asyncio
    async def test_customer_role_is_rejected(self):
        """JWT with role='customer' → 4003."""
        from api.ws import staff_ws
        token = create_jwt_token("cust@e.com", "co_1", "u1", "customer")
        ws = MockWebSocket()
        await staff_ws(ws, token=token)
        assert ws.closed
        assert ws.close_code == 4003

    @pytest.mark.asyncio
    async def test_valid_staff_jwt_receives_connected(self):
        """Valid staff JWT → accepted + connected event."""
        from api.ws import staff_ws
        token = create_jwt_token("staff@co.com", "co_1", "u1", "staff")
        ws = MockWebSocket()  # No messages → immediate disconnect
        await staff_ws(ws, token=token)

        assert ws.accepted
        connected = ws.find("connected")
        assert connected is not None
        assert connected["role"] == "staff"
        assert connected["company_id"] == "co_1"

    @pytest.mark.asyncio
    async def test_ping_pong_from_staff(self):
        """Staff {"type":"ping"} → {"type":"pong"}."""
        from api.ws import staff_ws
        token = create_jwt_token("staff@co.com", "co_1", "u1", "staff")
        ws = MockWebSocket(inbound_messages=[{"type": "ping"}])
        await staff_ws(ws, token=token)
        assert ws.find("pong") is not None

    @pytest.mark.asyncio
    @patch("api.ws.get_conversation", new_callable=AsyncMock)
    @patch("api.ws.list_messages", new_callable=AsyncMock, return_value=[])
    async def test_staff_join_conversation_sends_history(self, mock_msgs, mock_get_conv):
        """Staff {"type":"join","conv_id":"conv_1"} → conversation_history event."""
        from api.ws import staff_ws
        mock_get_conv.return_value = {
            "_id": "conv_1", "company_id": "co_1", "status": "active"
        }
        token = create_jwt_token("staff@co.com", "co_1", "u1", "staff")
        ws = MockWebSocket(inbound_messages=[{"type": "join", "conv_id": "conv_1"}])
        await staff_ws(ws, token=token)

        history = ws.find("conversation_history")
        assert history is not None
        assert history["conv_id"] == "conv_1"

    @pytest.mark.asyncio
    @patch("api.ws.get_conversation", new_callable=AsyncMock)
    async def test_staff_cannot_join_other_company_conversation(self, mock_get_conv):
        """Staff from co_A cannot join a conversation belonging to co_B."""
        from api.ws import staff_ws
        mock_get_conv.return_value = {
            "_id": "conv_b", "company_id": "co_B", "status": "active"
        }
        # Staff token for co_A
        token = create_jwt_token("staff@co-a.com", "co_A", "u1", "staff")
        ws = MockWebSocket(inbound_messages=[{"type": "join", "conv_id": "conv_b"}])
        await staff_ws(ws, token=token)

        error = ws.find("error")
        assert error is not None
        assert error["code"] == "forbidden"

    @pytest.mark.asyncio
    @patch("api.ws.get_conversation", new_callable=AsyncMock)
    @patch("api.ws.create_message", new_callable=AsyncMock, return_value="msg_staff_1")
    @patch("api.ws.log_audit", new_callable=AsyncMock)
    async def test_staff_message_persisted_and_acked(
        self, mock_audit, mock_create_msg, mock_get_conv
    ):
        """Staff sends message → message persisted + message_ack returned."""
        from api.ws import staff_ws
        mock_get_conv.return_value = {
            "_id": "conv_1", "company_id": "co_1", "status": "active"
        }
        token = create_jwt_token("staff@co.com", "co_1", "u1", "staff")
        ws = MockWebSocket(inbound_messages=[
            {"type": "message", "conv_id": "conv_1", "content": "How can I help you?"}
        ])
        await staff_ws(ws, token=token)

        ack = ws.find("message_ack")
        assert ack is not None
        assert ack["sender_type"] == "staff"
        assert ack["content"] == "How can I help you?"
        assert ack["msg_id"] == "msg_staff_1"
        mock_create_msg.assert_called_once()

    @pytest.mark.asyncio
    @patch("api.ws.get_conversation", new_callable=AsyncMock)
    async def test_staff_cannot_send_to_resolved_conversation(self, mock_get_conv):
        """Staff trying to message a resolved conversation → error."""
        from api.ws import staff_ws
        mock_get_conv.return_value = {
            "_id": "conv_1", "company_id": "co_1", "status": "resolved"
        }
        token = create_jwt_token("staff@co.com", "co_1", "u1", "staff")
        ws = MockWebSocket(inbound_messages=[
            {"type": "message", "conv_id": "conv_1", "content": "Late reply"}
        ])
        await staff_ws(ws, token=token)

        error = ws.find("error")
        assert error is not None
        assert error["code"] == "conversation_resolved"


# =============================================================================
# REST→WebSocket Broadcast Integration
# =============================================================================

class TestRestBroadcast:
    """
    Ensure that the REST endpoints (widget.py, conversations.py) broadcast
    messages to the ConnectionManager when they process them.
    """

    @pytest.mark.asyncio
    @patch("api.widget.get_company_by_slug", new_callable=AsyncMock)
    @patch("api.widget.get_conversation", new_callable=AsyncMock)
    @patch("api.widget.create_message", new_callable=AsyncMock)
    @patch("api.widget.update_conversation", new_callable=AsyncMock)
    @patch("api.widget.log_audit", new_callable=AsyncMock)
    @patch("api.widget.process_conversation_message", new_callable=AsyncMock)
    async def test_rest_widget_message_broadcasts_to_ws_room(
        self, mock_orch, mock_audit, mock_update, mock_create_msg,
        mock_get_conv, mock_get_company
    ):
        """
        When a customer uses REST POST /widget/{slug}/message, the resulting
        AI message should be broadcast to any staff subscribed via WS.
        """
        from services.orchestrator import OrchestratorResult
        from api.widget import send_message, CustomerMessageRequest
        from services.connection_manager import manager as prod_manager

        mock_get_company.return_value = {"company_id": "co_1", "settings": {}}
        mock_get_conv.return_value = {
            "_id": "conv_1", "company_id": "co_1",
            "customer_id": "s1", "status": "active",
        }
        mock_create_msg.side_effect = ["cust_msg", "ai_msg"]
        mock_orch.return_value = OrchestratorResult(
            action="escalate", message="Escalating.", confidence=0.3
        )

        # Register a staff WS connection in the conversation room
        staff_ws = MockWebSocket()
        await prod_manager.connect_staff(staff_ws, "co_1", "u1", "staff")
        await prod_manager.subscribe_to_conv(staff_ws, "conv_1")

        try:
            await send_message(
                "acme",
                CustomerMessageRequest(conversation_id="conv_1", content="Where is my invoice?"),
                x_session_id="s1",
            )
        finally:
            await prod_manager.disconnect(staff_ws)

        # Staff WS should have received the AI message broadcast
        ai_broadcasts = [m for m in staff_ws.sent if m.get("type") == "message" and m.get("sender_type") == "ai"]
        assert len(ai_broadcasts) >= 1

    @pytest.mark.asyncio
    @patch("api.conversations.get_conversation", new_callable=AsyncMock)
    @patch("api.conversations.create_message", new_callable=AsyncMock, return_value="m1")
    @patch("api.conversations.log_audit", new_callable=AsyncMock)
    async def test_rest_staff_reply_broadcasts_to_ws_room(
        self, mock_audit, mock_create_msg, mock_get_conv
    ):
        """
        When staff uses REST POST /conversations/{id}/message, the message is
        broadcast to the widget user who is connected via WS.
        """
        from api.conversations import staff_reply, StaffMessageRequest
        from services.connection_manager import manager as prod_manager

        mock_get_conv.return_value = {
            "_id": "conv_2", "company_id": "co_2", "status": "active",
        }
        staff_user = {"role": "staff", "user_id": "u_staff", "company_id": "co_2"}

        # Register a widget (customer) WS in the conversation room
        widget_ws = MockWebSocket()
        await prod_manager.connect_widget(widget_ws, "conv_2", "co_2", "customer_session")

        try:
            await staff_reply(
                "conv_2",
                StaffMessageRequest(content="Hi, I can help with that."),
                user=staff_user,
            )
        finally:
            await prod_manager.disconnect(widget_ws)

        # Widget WS should have received the staff message broadcast
        broadcasts = [m for m in widget_ws.sent if m.get("type") == "message"]
        assert len(broadcasts) >= 1
        assert broadcasts[0]["sender_type"] == "staff"
        assert "help" in broadcasts[0]["content"]

# =============================================================================
# api/ws.py — WebSocket Endpoints for Real-Time Chat
# =============================================================================
# Two endpoints:
#
#   WS /api/v1/ws/widget/{slug}
#       ?session_id=<widget_session_id>
#       [&conv_id=<existing_conv_id>]
#
#       Public (no JWT).  Widget user connects, sends/receives messages in
#       real-time.  Orchestrator runs on the server; AI response is broadcast
#       back to the room so staff also see it immediately.
#
#   WS /api/v1/ws/staff
#       ?token=<JWT>
#
#       JWT-authenticated.  Staff/Admin connects; receives company-wide
#       new-conversation notifications.  Uses "join"/"leave" events to
#       subscribe to individual conversation rooms.
#
# Event model (JSON messages)
# ───────────────────────────
#   Client → Server
#     {"type":"ping"}
#     {"type":"message",  "conv_id":"...", "content":"..."}
#     {"type":"typing",   "conv_id":"...", "is_typing":true/false}
#     {"type":"join",     "conv_id":"..."}   (staff only)
#     {"type":"leave",    "conv_id":"..."}   (staff only)
#
#   Server → Client
#     {"type":"connected",            "conv_id":"...", "session_id":"...", "messages":[...]}
#     {"type":"pong"}
#     {"type":"message",              "msg_id":"...", "conv_id":"...",
#                                     "sender_type":"customer|ai|staff|admin",
#                                     "sender_id":"...", "content":"...",
#                                     "created_at":"...", "metadata":{...}}
#     {"type":"message_ack",          same fields as message + echoed back to sender}
#     {"type":"ai_thinking",          "conv_id":"..."}
#     {"type":"typing",               "conv_id":"...", "sender_type":"...",
#                                     "sender_id":"...", "is_typing":true/false}
#     {"type":"presence",             "conv_id":"...", "event":"joined|left",
#                                     "role":"...", "id":"..."}
#     {"type":"new_conversation",     "conv_id":"...", "customer_id":"..."}
#     {"type":"conversation_status",  "conv_id":"...", "new_status":"resolved|archived"}
#     {"type":"error",                "code":"...", "message":"..."}
# =============================================================================

import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

from api.auth import decode_jwt_token
from services.connection_manager import manager
from services.mongo import (
    get_company_by_slug,
    get_active_conversation,
    create_conversation,
    get_conversation,
    update_conversation,
    list_messages,
    create_message,
    Conversation,
    Message,
    AuditLog,
    log_audit,
)
from services.orchestrator import process_conversation_message

logger = logging.getLogger(__name__)
router = APIRouter(tags=["WebSocket"])


# =============================================================================
# Helpers
# =============================================================================

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_safe(obj):
    """Recursively convert datetime objects to ISO strings so send_json works."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_safe(item) for item in obj]
    return obj


def _msg_event(msg_id: str, conv_id: str, sender_type: str,
               sender_id: str, content: str, metadata: dict = None) -> dict:
    return {
        "type": "message",
        "msg_id": msg_id,
        "conv_id": conv_id,
        "sender_type": sender_type,
        "sender_id": sender_id,
        "content": content,
        "metadata": metadata or {},
        "created_at": _now_iso(),
    }


async def _send_error(ws: WebSocket, code: str, message: str) -> None:
    try:
        await ws.send_json({"type": "error", "code": code, "message": message})
    except Exception:
        pass


# =============================================================================
# Widget WebSocket  — WS /api/v1/ws/widget/{slug}
# =============================================================================

@router.websocket("/api/v1/ws/widget/{slug}")
async def widget_ws(
    websocket: WebSocket,
    slug: str,
    session_id: str = Query(...),
    conv_id: str = Query(None),
):
    """
    Real-time connection for widget (customer) users.
    No JWT required — identified by session_id (UUID stored in widget localStorage).
    """
    await websocket.accept()

    # --- Validate company ---
    company = await get_company_by_slug(slug)
    if not company:
        await _send_error(websocket, "invalid_company", "Company not found")
        await websocket.close(code=4004)
        return

    company_id = company.get("company_id") or company["_id"]
    company_settings = company.get("settings", {})

    # --- Resolve or create conversation ---
    resolved_conv_id: str = conv_id or ""
    if resolved_conv_id:
        conv = await get_conversation(resolved_conv_id)
        if not conv or conv["company_id"] != company_id or conv.get("customer_id") != session_id:
            await _send_error(websocket, "invalid_conversation", "Conversation not found")
            await websocket.close(code=4003)
            return
        history = await list_messages(resolved_conv_id)
    else:
        existing = await get_active_conversation(company_id, session_id)
        if existing:
            resolved_conv_id = existing["_id"]
            history = await list_messages(resolved_conv_id)
        else:
            new_conv = Conversation(
                company_id=company_id,
                customer_id=session_id,
                widget_session_id=session_id,
            )
            resolved_conv_id = await create_conversation(new_conv)
            history = []
            # Notify all company staff that a new conversation started
            await manager.broadcast_to_company_staff(company_id, {
                "type": "new_conversation",
                "conv_id": resolved_conv_id,
                "customer_id": session_id,
                "created_at": _now_iso(),
            })

    # --- Register connection ---
    await manager.connect_widget(websocket, resolved_conv_id, company_id, session_id)

    # --- Broadcast widget presence to staff watching this conversation ---
    await manager.broadcast_to_conv(resolved_conv_id, {
        "type": "presence",
        "event": "joined",
        "role": "customer",
        "id": session_id,
        "conv_id": resolved_conv_id,
    }, exclude=websocket)

    # --- Send initial state to widget ---
    await websocket.send_json({
        "type": "connected",
        "conv_id": resolved_conv_id,
        "session_id": session_id,
        "messages": _json_safe(history),
        "staff_online": manager.company_staff_online(company_id),
    })

    # ================================================================
    # Main receive loop
    # ================================================================
    try:
        while True:
            try:
                data = await websocket.receive_json()
            except Exception:
                # Non-JSON frame or network error
                break

            msg_type = data.get("type", "")

            # ── ping / keepalive ──────────────────────────────────────
            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})

            # ── typing indicator ──────────────────────────────────────
            elif msg_type == "typing":
                await manager.broadcast_to_conv(resolved_conv_id, {
                    "type": "typing",
                    "conv_id": resolved_conv_id,
                    "sender_type": "customer",
                    "sender_id": session_id,
                    "is_typing": bool(data.get("is_typing", True)),
                }, exclude=websocket)

            # ── customer message ─────────────────────────────────────
            elif msg_type == "message":
                content = data.get("content", "").strip()
                if not content:
                    await _send_error(websocket, "empty_message", "Message cannot be empty")
                    continue

                # Re-check conversation is still active
                conv = await get_conversation(resolved_conv_id)
                if not conv or conv["status"] != "active":
                    await _send_error(websocket, "conversation_resolved",
                                      "Conversation is resolved. Please start a new one.")
                    continue

                # Persist customer message
                cust_msg = Message(
                    conversation_id=resolved_conv_id,
                    company_id=company_id,
                    sender_type="customer",
                    sender_id=session_id,
                    content=content,
                )
                cust_msg_id = await create_message(cust_msg)

                # ACK to sender
                cust_event = _msg_event(cust_msg_id, resolved_conv_id,
                                        "customer", session_id, content)
                await websocket.send_json({**cust_event, "type": "message_ack"})

                # Broadcast customer message to staff in the room
                await manager.broadcast_to_conv(resolved_conv_id, cust_event,
                                                exclude=websocket)

                # Show "AI is thinking" indicator
                thinking_event = {"type": "ai_thinking", "conv_id": resolved_conv_id}
                await websocket.send_json(thinking_event)
                await manager.broadcast_to_conv(resolved_conv_id, thinking_event,
                                                exclude=websocket)

                # ── Run orchestrator ──────────────────────────────────
                try:
                    result = await process_conversation_message(
                        customer_message=content,
                        company_id=company_id,
                        conversation_id=resolved_conv_id,
                        company_settings=company_settings,
                    )
                    ai_action = result.action
                    ai_message = result.message
                    ai_sources = result.sources or []
                    ai_confidence = result.confidence
                    ai_intent = result.intent
                except Exception as exc:
                    logger.error(
                        f"[WS] Orchestrator error for conv {resolved_conv_id}: {exc}"
                    )
                    ai_action = "escalate"
                    ai_message = (
                        "Something went wrong on our end. "
                        "Let me connect you with a team member."
                    )
                    ai_sources = []
                    ai_confidence = 0.0
                    ai_intent = "general"

                # Persist AI message
                ai_msg = Message(
                    conversation_id=resolved_conv_id,
                    company_id=company_id,
                    sender_type="ai",
                    content=ai_message,
                    metadata={
                        "action": ai_action,
                        "sources": ai_sources,
                        "confidence": ai_confidence,
                        "intent": ai_intent,
                    },
                )
                ai_msg_id = await create_message(ai_msg)

                # Broadcast AI message to the whole room
                ai_event = _msg_event(
                    ai_msg_id, resolved_conv_id, "ai", "ai", ai_message,
                    metadata={
                        "action": ai_action,
                        "sources": ai_sources,
                        "confidence": ai_confidence,
                        "intent": ai_intent,
                    },
                )
                await manager.broadcast_to_conv(resolved_conv_id, ai_event)

                # Auto-close on auto_reply
                if (ai_action == "auto_reply"
                        and company_settings.get("auto_resolve_auto_close", True)):
                    await update_conversation(resolved_conv_id, {
                        "status": "resolved",
                        "resolved_at": datetime.now(timezone.utc),
                        "resolved_by_user_id": "ai",
                    })
                    status_event = {
                        "type": "conversation_status",
                        "conv_id": resolved_conv_id,
                        "new_status": "resolved",
                    }
                    await manager.broadcast_to_conv(resolved_conv_id, status_event)

                # Audit log (best-effort)
                try:
                    await log_audit(AuditLog(
                        company_id=company_id,
                        event_type=ai_action,
                        request_summary=content[:200],
                        response_summary=ai_message[:200],
                        confidence=ai_confidence,
                        sources=ai_sources,
                    ))
                except Exception as e:
                    logger.warning(f"[WS] Audit log failed: {e}")

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"[WS] Widget handler error for conv {resolved_conv_id}: {e}")
    finally:
        # Broadcast departure
        await manager.broadcast_to_conv(resolved_conv_id, {
            "type": "presence",
            "event": "left",
            "role": "customer",
            "id": session_id,
            "conv_id": resolved_conv_id,
        }, exclude=websocket)
        await manager.disconnect(websocket)


# =============================================================================
# Staff WebSocket  — WS /api/v1/ws/staff
# =============================================================================

@router.websocket("/api/v1/ws/staff")
async def staff_ws(
    websocket: WebSocket,
    token: str = Query(...),
):
    """
    Real-time connection for staff / admin users.
    Authenticated via JWT passed as `?token=<JWT>` query parameter.
    """
    await websocket.accept()

    # --- Validate JWT ---
    try:
        payload = decode_jwt_token(token)
    except Exception:
        await _send_error(websocket, "auth_failed", "Invalid or expired token")
        await websocket.close(code=4001)
        return

    role = payload.get("role", "staff")
    if role not in ("staff", "admin", "superadmin"):
        await _send_error(websocket, "forbidden", "Insufficient permissions")
        await websocket.close(code=4003)
        return

    company_id = payload.get("company_id", "")
    user_id = payload.get("user_id", "")

    # --- Register connection ---
    await manager.connect_staff(websocket, company_id, user_id, role)

    # --- Confirmation ---
    await websocket.send_json({
        "type": "connected",
        "user_id": user_id,
        "role": role,
        "company_id": company_id,
    })

    # ================================================================
    # Main receive loop
    # ================================================================
    try:
        while True:
            try:
                data = await websocket.receive_json()
            except Exception:
                break

            msg_type = data.get("type", "")

            # ── ping / keepalive ──────────────────────────────────────
            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})

            # ── join conversation room ────────────────────────────────
            elif msg_type == "join":
                conv_id = data.get("conv_id", "")
                if not conv_id:
                    continue
                # Verify conversation belongs to this company
                conv = await get_conversation(conv_id)
                if not conv:
                    await _send_error(websocket, "not_found", "Conversation not found")
                    continue
                if role != "superadmin" and conv["company_id"] != company_id:
                    await _send_error(websocket, "forbidden", "Access denied")
                    continue

                await manager.subscribe_to_conv(websocket, conv_id)

                # Send message history on join
                messages = await list_messages(conv_id)
                await websocket.send_json({
                    "type": "conversation_history",
                    "conv_id": conv_id,
                    "messages": _json_safe(messages),
                    "participants": manager.get_conv_participants(conv_id),
                    "status": conv.get("status", "active"),
                })

                # Broadcast staff presence to others in the room
                await manager.broadcast_to_conv(conv_id, {
                    "type": "presence",
                    "event": "joined",
                    "role": role,
                    "id": user_id,
                    "conv_id": conv_id,
                }, exclude=websocket)

            # ── leave conversation room ───────────────────────────────
            elif msg_type == "leave":
                conv_id = data.get("conv_id", "")
                if not conv_id:
                    continue
                await manager.unsubscribe_from_conv(websocket, conv_id)
                await manager.broadcast_to_conv(conv_id, {
                    "type": "presence",
                    "event": "left",
                    "role": role,
                    "id": user_id,
                    "conv_id": conv_id,
                }, exclude=websocket)

            # ── staff sends a message ─────────────────────────────────
            elif msg_type == "message":
                conv_id = data.get("conv_id", "")
                content = data.get("content", "").strip()
                if not conv_id or not content:
                    await _send_error(websocket, "invalid_request",
                                      "conv_id and content are required")
                    continue

                conv = await get_conversation(conv_id)
                if not conv:
                    await _send_error(websocket, "not_found", "Conversation not found")
                    continue
                if role != "superadmin" and conv["company_id"] != company_id:
                    await _send_error(websocket, "forbidden", "Access denied")
                    continue
                if conv["status"] != "active":
                    await _send_error(websocket, "conversation_resolved",
                                      "Cannot reply to a resolved conversation")
                    continue

                sender_type = "admin" if role in ("admin", "superadmin") else "staff"
                msg = Message(
                    conversation_id=conv_id,
                    company_id=conv["company_id"],
                    sender_type=sender_type,
                    sender_id=user_id,
                    content=content,
                )
                msg_id = await create_message(msg)

                # ACK to sender
                event = _msg_event(msg_id, conv_id, sender_type, user_id, content)
                await websocket.send_json({**event, "type": "message_ack"})

                # Broadcast to whole conversation room
                await manager.broadcast_to_conv(conv_id, event, exclude=websocket)

                # Audit log (best-effort)
                try:
                    await log_audit(AuditLog(
                        company_id=conv["company_id"],
                        user_id=user_id,
                        event_type="staff_reply_ws",
                        request_summary=f"WS staff reply in conv {conv_id}",
                        response_summary=content[:200],
                    ))
                except Exception as e:
                    logger.warning(f"[WS] Audit log failed: {e}")

            # ── typing indicator ──────────────────────────────────────
            elif msg_type == "typing":
                conv_id = data.get("conv_id", "")
                if not conv_id:
                    continue
                sender_type = "admin" if role in ("admin", "superadmin") else "staff"
                await manager.broadcast_to_conv(conv_id, {
                    "type": "typing",
                    "conv_id": conv_id,
                    "sender_type": sender_type,
                    "sender_id": user_id,
                    "is_typing": bool(data.get("is_typing", True)),
                }, exclude=websocket)

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"[WS] Staff handler error for user {user_id}: {e}")
    finally:
        await manager.disconnect(websocket)

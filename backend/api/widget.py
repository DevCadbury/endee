# =============================================================================
# api/widget.py — Customer-Facing Widget Endpoints (no auth required)
# =============================================================================
# Public endpoints called by the embedded chat widget.
# Manages the single-active-conversation-per-session lifecycle.
# =============================================================================

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel

from services.mongo import (
    get_company_by_slug,
    get_active_conversation,
    create_conversation,
    get_conversation,
    update_conversation,
    delete_conversation_user_side,
    list_messages,
    create_message,
    Conversation,
    Message,
    AuditLog,
    log_audit,
)
from services.orchestrator import process_conversation_message
from services.connection_manager import manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/widget", tags=["Widget"])


# =============================================================================
# Request Models
# =============================================================================

class OpenConversationRequest(BaseModel):
    widget_session_id: str
    customer_name: str = ""


class CustomerMessageRequest(BaseModel):
    conversation_id: str
    content: str


# =============================================================================
# Helper
# =============================================================================

async def _get_company_or_404(slug: str) -> dict:
    company = await get_company_by_slug(slug)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return company


# =============================================================================
# Routes
# =============================================================================

@router.post("/{slug}/open")
async def open_conversation(slug: str, request: OpenConversationRequest):
    """
    Open or resume a conversation for a widget session.

    - If an active conversation exists for this session → return it.
    - If the previous conversation is resolved/archived
      (or no conversation exists) → create a new one.
    - Returns the conversation_id and full message history.
    """
    company = await _get_company_or_404(slug)
    company_id = company.get("company_id") or company["_id"]
    customer_id = request.widget_session_id

    # Check for existing active conversation
    existing = await get_active_conversation(company_id, customer_id)
    if existing:
        messages = await list_messages(existing["_id"])
        return {
            "conversation_id": existing["_id"],
            "status": existing["status"],
            "messages": messages,
            "is_new": False,
        }

    # Create a new conversation
    conv = Conversation(
        company_id=company_id,
        customer_id=customer_id,
        widget_session_id=request.widget_session_id,
    )
    conv_id = await create_conversation(conv)

    logger.info(
        f"New conversation {conv_id} for session "
        f"'{customer_id}' in company '{slug}' ({company_id})"
    )

    # Notify any online staff about the new conversation (best-effort)
    try:
        await manager.broadcast_to_company_staff(company_id, {
            "type": "new_conversation",
            "conv_id": conv_id,
            "customer_id": customer_id,
        })
    except Exception:
        pass

    return {
        "conversation_id": conv_id,
        "status": "active",
        "messages": [],
        "is_new": True,
    }


@router.post("/{slug}/message")
async def send_message(
    slug: str,
    request: CustomerMessageRequest,
    x_session_id: str = Header(None, alias="X-Session-Id"),
):
    """
    Customer sends a message via the widget.

    Flow:
    1. Validate conversation is active and belongs to this session/company
    2. Persist customer message
    3. Run orchestrator with company-specific thresholds
    4. Persist AI response message
    5. If auto_reply + auto_resolve_auto_close → mark conversation resolved
    6. Return AI response
    """
    if not request.content.strip():
        raise HTTPException(status_code=400, detail="Message content cannot be empty")

    company = await _get_company_or_404(slug)
    company_id = company.get("company_id") or company["_id"]
    company_settings = company.get("settings", {})
    conv_id = request.conversation_id

    # Fetch and validate conversation
    conv = await get_conversation(conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if conv["company_id"] != company_id:
        raise HTTPException(status_code=403, detail="Access denied")
    # Validate session ownership: X-Session-Id must match the conversation's customer_id
    if x_session_id and conv.get("customer_id") and x_session_id != conv["customer_id"]:
        raise HTTPException(status_code=403, detail="Session ID does not match conversation")
    if conv["status"] != "active":
        raise HTTPException(
            status_code=409,
            detail="Conversation is resolved. Start a new conversation.",
        )

    # Persist customer message
    customer_msg = Message(
        conversation_id=conv_id,
        company_id=company_id,
        sender_type="customer",
        sender_id=x_session_id or conv.get("customer_id", ""),
        content=request.content.strip(),
    )
    cust_msg_id = await create_message(customer_msg)

    # Push customer message to any WS participants in this conversation (staff)
    try:
        await manager.broadcast_to_conv(conv_id, {
            "type": "message",
            "msg_id": cust_msg_id,
            "conv_id": conv_id,
            "sender_type": "customer",
            "sender_id": x_session_id or conv.get("customer_id", ""),
            "content": request.content.strip(),
            "metadata": {},
        })
    except Exception:
        pass

    # Run orchestrator
    try:
        result = await process_conversation_message(
            customer_message=request.content.strip(),
            company_id=company_id,
            conversation_id=conv_id,
            company_settings=company_settings,
        )
    except Exception as e:
        logger.error(f"Orchestrator failed for conv {conv_id}: {e}")
        result_action = "escalate"
        result_message = (
            "Something went wrong on our end. "
            "Let me connect you with a team member."
        )
        result_sources = []
        result_confidence = 0.0
        result_intent = "general"
    else:
        result_action = result.action
        result_message = result.message
        result_sources = result.sources or []
        result_confidence = result.confidence
        result_intent = result.intent

    # Persist AI message
    ai_msg = Message(
        conversation_id=conv_id,
        company_id=company_id,
        sender_type="ai",
        content=result_message,
        metadata={
            "action": result_action,
            "sources": result_sources,
            "confidence": result_confidence,
            "intent": result_intent,
        },
    )
    ai_msg_id = await create_message(ai_msg)

    # Push AI message to any WS participants in this conversation
    try:
        await manager.broadcast_to_conv(conv_id, {
            "type": "message",
            "msg_id": ai_msg_id,
            "conv_id": conv_id,
            "sender_type": "ai",
            "sender_id": "ai",
            "content": result_message,
            "metadata": {
                "action": result_action,
                "sources": result_sources,
                "confidence": result_confidence,
                "intent": result_intent,
            },
        })
    except Exception:
        pass

    # Auto-close conversation if auto_reply and setting enabled
    if (
        result_action == "auto_reply"
        and company_settings.get("auto_resolve_auto_close", True)
    ):
        await update_conversation(conv_id, {
            "status": "resolved",
            "resolved_at": datetime.now(timezone.utc),
            "resolved_by_user_id": "ai",
        })
        new_status = "resolved"
        # Broadcast status change to WS participants
        try:
            await manager.broadcast_to_conv(conv_id, {
                "type": "conversation_status",
                "conv_id": conv_id,
                "new_status": "resolved",
            })
        except Exception:
            pass
    else:
        new_status = "active"

    # Audit log
    try:
        await log_audit(AuditLog(
            company_id=company_id,
            event_type=result_action,
            request_summary=request.content[:200],
            response_summary=result_message[:200],
            confidence=result_confidence,
            sources=result_sources,
        ))
    except Exception as e:
        logger.warning(f"Audit log failed for conv {conv_id}: {e}")

    return {
        "action": result_action,
        "message": result_message,
        "sources": result_sources,
        "context_passed_to_agent": result_action == "escalate",
        "conversation_status": new_status,
        "conversation_id": conv_id,
    }


@router.delete("/{slug}/conversation/{conv_id}")
async def delete_conversation(
    slug: str,
    conv_id: str,
    x_session_id: str = Header(None, alias="X-Session-Id"),
):
    """
    Customer-side soft-delete.

    Only allowed when conversation.status == "resolved".
    The server retains the master copy for audit; only marks deleted_by_user=True.
    """
    company = await _get_company_or_404(slug)
    company_id = company.get("company_id") or company["_id"]

    result = await delete_conversation_user_side(conv_id, company_id)

    if "error" in result:
        if result["error"] == "not_found":
            raise HTTPException(status_code=404, detail="Conversation not found")
        if result["error"] == "not_resolved":
            raise HTTPException(
                status_code=409,
                detail="Cannot delete an active conversation. "
                       "Please wait for resolution before deleting.",
            )

    return {"status": "deleted", "conversation_id": conv_id}

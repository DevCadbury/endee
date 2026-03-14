# =============================================================================
# api/conversations.py — Staff Conversation Management Routes
# =============================================================================
# Staff and Admin routes for viewing, replying to, assigning, and resolving
# conversations. Resolution triggers automatic KB entry creation and ingestion
# into the Endee vector store (the learning loop).
# =============================================================================

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel

from api.auth import require_staff, require_admin, get_current_user
from services.connection_manager import manager
from services.mongo import (
    get_conversation,
    list_conversations,
    update_conversation,
    list_messages,
    create_message,
    create_kb_entry,
    set_kb_entry_doc_id,
    Message,
    KBEntry,
    AuditLog,
    log_audit,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/conversations", tags=["Conversations"])


# =============================================================================
# Request Models
# =============================================================================

class StaffMessageRequest(BaseModel):
    content: str


class AssignRequest(BaseModel):
    staff_user_id: str


class ResolveRequest(BaseModel):
    canonical_answer: str           # the final, agent-approved response
    title: str = ""                 # optional KB entry title
    tags: str = ""
    ingest_to_kb: bool = True       # whether to index in Endee


class EscalateRequest(BaseModel):
    reason: str = ""


# =============================================================================
# Helper
# =============================================================================

async def _get_conv_for_company(conv_id: str, user: dict) -> dict:
    """Fetch a conversation, enforcing company isolation."""
    conv = await get_conversation(conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if user.get("role") != "superadmin" and conv["company_id"] != user.get("company_id"):
        raise HTTPException(status_code=403, detail="Access denied")
    return conv


# =============================================================================
# Routes
# =============================================================================

@router.get("")
async def list_convs(
    status: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    user: dict = Depends(require_staff),
):
    """
    List conversations.
    - Admin/SuperAdmin: see all conversations for the company.
    - Staff: see conversations assigned to them.
    """
    company_id = user["company_id"]
    role = user.get("role", "staff")

    # Staff only sees assigned conversations; admin sees all
    assigned_filter = user.get("user_id") if role == "staff" else None

    convs = await list_conversations(
        company_id=company_id,
        status=status,
        assigned_staff_id=assigned_filter,
        limit=limit,
    )
    return {"conversations": convs, "total": len(convs)}


@router.get("/{conv_id}")
async def get_conv(conv_id: str, user: dict = Depends(require_staff)):
    """Get a conversation with its full message history."""
    conv = await _get_conv_for_company(conv_id, user)
    messages = await list_messages(conv_id)
    return {**conv, "messages": messages}


@router.post("/{conv_id}/message")
async def staff_reply(
    conv_id: str,
    request: StaffMessageRequest,
    user: dict = Depends(require_staff),
):
    """
    Staff sends a message in a conversation.
    Conversation must be active (not resolved/archived).
    """
    if not request.content.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    conv = await _get_conv_for_company(conv_id, user)
    if conv["status"] != "active":
        raise HTTPException(
            status_code=409, detail="Cannot reply to a resolved conversation"
        )

    company_id = conv["company_id"]
    role = user.get("role", "staff")
    sender_type = "admin" if role in ("admin", "superadmin") else "staff"

    msg = Message(
        conversation_id=conv_id,
        company_id=company_id,
        sender_type=sender_type,
        sender_id=user.get("user_id", ""),
        content=request.content.strip(),
    )
    msg_id = await create_message(msg)

    # Push message to any WS participants in this conversation (e.g. widget user)
    try:
        await manager.broadcast_to_conv(conv_id, {
            "type": "message",
            "msg_id": msg_id,
            "conv_id": conv_id,
            "sender_type": sender_type,
            "sender_id": user.get("user_id", ""),
            "content": request.content.strip(),
            "metadata": {},
        })
    except Exception:
        pass

    # Audit
    try:
        await log_audit(AuditLog(
            company_id=company_id,
            user_id=user.get("user_id", ""),
            event_type="staff_reply",
            request_summary=f"Staff reply in conv {conv_id}",
            response_summary=request.content[:200],
        ))
    except Exception as e:
        logger.warning(f"Audit log failed: {e}")

    return {"message_id": msg_id, "conversation_id": conv_id}


@router.post("/{conv_id}/assign")
async def assign_conv(
    conv_id: str,
    request: AssignRequest,
    user: dict = Depends(require_admin),
):
    """Assign a conversation to a specific staff member (Admin only)."""
    conv = await _get_conv_for_company(conv_id, user)

    updated = await update_conversation(conv_id, {
        "assigned_staff_id": request.staff_user_id,
    })
    if not updated:
        raise HTTPException(status_code=500, detail="Failed to assign conversation")
    return {"status": "assigned", "assigned_to": request.staff_user_id}


@router.post("/{conv_id}/resolve")
async def resolve_conv(
    conv_id: str,
    request: ResolveRequest,
    user: dict = Depends(require_staff),
):
    """
    Staff resolves a conversation and ingests a KB entry into Endee.

    Flow:
    1. Verify conversation is active
    2. Gather customer messages for context
    3. Create a KBEntry (canonical answer written by staff)
    4. If ingest_to_kb: embed and upsert into Endee
    5. Mark conversation resolved
    6. Audit log
    """
    if not request.canonical_answer.strip():
        raise HTTPException(status_code=400, detail="canonical_answer cannot be empty")

    conv = await _get_conv_for_company(conv_id, user)
    if conv["status"] != "active":
        raise HTTPException(
            status_code=409, detail="Conversation is already resolved"
        )

    company_id = conv["company_id"]
    user_id = user.get("user_id", "")

    # Gather the customer's question for context
    messages = await list_messages(conv_id)
    customer_msgs = [
        m["content"] for m in messages if m.get("sender_type") == "customer"
    ]
    original_question = customer_msgs[0] if customer_msgs else conv.get("customer_id", "")

    # Ingest into Endee and create KB entry (the learning loop)
    entry_id = None
    ingest_result = None
    if request.ingest_to_kb:
        entry_title = request.title or f"Resolved: {original_question[:60]}"
        kb_entry = KBEntry(
            company_id=company_id,
            source_type="ticket_resolution",
            title=entry_title,
            canonical_answer=request.canonical_answer.strip(),
            tags=request.tags,
            created_by_user_id=user_id,
            verified=True,
        )
        entry_id = await create_kb_entry(kb_entry)
        try:
            from services.ingestion import ingest_resolved_ticket
            ingest_result = await ingest_resolved_ticket(
                company_id=company_id,
                ticket_id=entry_id,
                question=original_question,
                resolution=request.canonical_answer.strip(),
                category="general",
                tags=request.tags,
            )
            if ingest_result and ingest_result.get("doc_id"):
                await set_kb_entry_doc_id(entry_id, ingest_result["doc_id"])
            logger.info(
                f"KB ingestion for conv {conv_id}: "
                f"{ingest_result.get('chunk_count', 0)} chunks"
            )
        except Exception as e:
            logger.error(f"KB ingestion failed for conv {conv_id}: {e}")

    # Mark conversation resolved
    await update_conversation(conv_id, {
        "status": "resolved",
        "resolved_at": datetime.now(timezone.utc),
        "resolved_by_user_id": user_id,
    })

    # Notify WS participants that conversation is now resolved
    try:
        await manager.broadcast_to_conv(conv_id, {
            "type": "conversation_status",
            "conv_id": conv_id,
            "new_status": "resolved",
        })
    except Exception:
        pass

    # Audit
    try:
        await log_audit(AuditLog(
            company_id=company_id,
            user_id=user_id,
            event_type="conversation_resolved",
            request_summary=f"Conversation {conv_id} resolved",
            response_summary=request.canonical_answer[:200],
        ))
    except Exception as e:
        logger.warning(f"Audit log failed: {e}")

    return {
        "status": "resolved",
        "conversation_id": conv_id,
        "kb_entry_id": entry_id,
        "kb_ingested": ingest_result is not None,
        "chunks_ingested": ingest_result.get("chunk_count", 0) if ingest_result else 0,
    }


@router.post("/{conv_id}/escalate")
async def escalate_conv(
    conv_id: str,
    request: EscalateRequest,
    user: dict = Depends(require_staff),
):
    """
    Escalate a conversation (unassign from current staff, clear assignment
    so admin can reassign to a higher tier or another agent).
    """
    conv = await _get_conv_for_company(conv_id, user)
    if conv["status"] != "active":
        raise HTTPException(
            status_code=409, detail="Cannot escalate a resolved conversation"
        )

    company_id = conv["company_id"]

    # Clear assignment so admin can pick it up
    await update_conversation(conv_id, {"assigned_staff_id": ""})

    # Log escalation as an AI message for visibility in the thread
    escalation_note = Message(
        conversation_id=conv_id,
        company_id=company_id,
        sender_type="ai",
        content=(
            f"This conversation has been escalated."
            + (f" Reason: {request.reason}" if request.reason else "")
        ),
        metadata={"action": "escalate", "escalated_by": user.get("user_id", "")},
    )
    escalation_note_id = await create_message(escalation_note)

    # Notify WS participants about escalation
    try:
        await manager.broadcast_to_conv(conv_id, {
            "type": "message",
            "msg_id": escalation_note_id,
            "conv_id": conv_id,
            "sender_type": "ai",
            "sender_id": "ai",
            "content": escalation_note.content,
            "metadata": escalation_note.metadata,
        })
    except Exception:
        pass

    # Audit
    try:
        await log_audit(AuditLog(
            company_id=company_id,
            user_id=user.get("user_id", ""),
            event_type="escalation",
            request_summary=f"Conversation {conv_id} escalated",
            response_summary=request.reason[:200] if request.reason else "No reason given",
        ))
    except Exception as e:
        logger.warning(f"Audit log failed: {e}")

    return {"status": "escalated", "conversation_id": conv_id}

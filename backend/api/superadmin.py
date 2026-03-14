# =============================================================================
# api/superadmin.py — SuperAdmin Global Management Routes
# =============================================================================
# Read-only global views for the SuperAdmin role.
# SuperAdmin can see all companies, users, conversations, and audit logs.
# =============================================================================

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query

from api.auth import require_superadmin
from services.mongo import (
    list_companies,
    list_all_users,
    list_all_conversations,
    get_all_audit_logs,
    get_db,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/superadmin", tags=["SuperAdmin"])


@router.get("/companies")
async def get_all_companies(user: dict = Depends(require_superadmin)):
    """
    List all registered companies with basic stats.
    """
    companies = await list_companies()

    # Enrich each company with user + conversation counts
    db = get_db()
    enriched = []
    for c in companies:
        cid = c.get("company_id") or c["_id"]
        user_count = await db.users.count_documents({"company_id": cid})
        conv_count = await db.conversations.count_documents({"company_id": cid})
        active_count = await db.conversations.count_documents(
            {"company_id": cid, "status": "active"}
        )
        enriched.append({
            **c,
            "user_count": user_count,
            "conversation_count": conv_count,
            "active_conversations": active_count,
        })

    return {"companies": enriched, "total": len(enriched)}


@router.get("/users")
async def get_all_users(user: dict = Depends(require_superadmin)):
    """
    List all users across all companies (passwords excluded).
    """
    users = await list_all_users()
    return {"users": users, "total": len(users)}


@router.get("/conversations")
async def get_all_conversations_view(
    status: Optional[str] = Query(None),
    limit: int = Query(100, le=500),
    user: dict = Depends(require_superadmin),
):
    """
    List all conversations across all companies.
    Optionally filtered by status (active|resolved|archived).
    """
    convs = await list_all_conversations(status=status, limit=limit)
    return {"conversations": convs, "total": len(convs)}


@router.get("/audit-logs")
async def get_global_audit_logs(
    limit: int = Query(100, le=500),
    user: dict = Depends(require_superadmin),
):
    """
    Get recent audit events across all companies.
    """
    logs = await get_all_audit_logs(limit=limit)
    return {"audit_logs": logs, "total": len(logs)}


@router.get("/stats")
async def get_global_stats(user: dict = Depends(require_superadmin)):
    """
    Platform-wide aggregate statistics.
    """
    db = get_db()
    total_companies = await db.companies.count_documents({})
    total_users = await db.users.count_documents({})
    total_conversations = await db.conversations.count_documents({})
    active_conversations = await db.conversations.count_documents({"status": "active"})
    resolved_conversations = await db.conversations.count_documents({"status": "resolved"})
    total_kb_entries = await db.kb_entries.count_documents({})
    total_chat_sessions = await db.chat_sessions.count_documents({})
    auto_resolved = await db.chat_sessions.count_documents({"action": "auto_reply"})

    return {
        "total_companies": total_companies,
        "total_users": total_users,
        "total_conversations": total_conversations,
        "active_conversations": active_conversations,
        "resolved_conversations": resolved_conversations,
        "total_kb_entries": total_kb_entries,
        "total_chat_sessions": total_chat_sessions,
        "global_auto_resolve_rate": (
            round(auto_resolved / total_chat_sessions * 100, 1)
            if total_chat_sessions > 0 else 0
        ),
    }

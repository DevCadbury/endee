# =============================================================================
# api/dashboard.py — Company Dashboard API Routes
# =============================================================================
# Provides endpoints for the frontend dashboard:
# Stats overview, ticket management, audit logs, and ticket resolution.
# =============================================================================

import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from api.auth import get_current_user, require_staff, require_admin
from services.mongo import (
    get_dashboard_stats,
    list_tickets,
    resolve_ticket,
    get_audit_logs,
)
from services.ingestion import ingest_resolved_ticket

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/dashboard", tags=["Dashboard"])


# =============================================================================
# Request/Response Models
# =============================================================================

class ResolveTicketRequest(BaseModel):
    """Request to resolve a ticket and optionally ingest into KB."""
    resolution: str
    ingest_to_kb: bool = True  # Auto-ingest resolution into KB
    category: str = "general"
    tags: str = ""


# =============================================================================
# Routes
# =============================================================================

@router.get("/stats")
async def get_stats(user: dict = Depends(require_staff)):
    """
    Get aggregated dashboard statistics for the company.
    
    Returns: total_chats, auto_resolved, escalated, clarified,
    pending_tickets, total_documents, auto_resolve_rate, escalation_rate.
    """
    company_id = user["company_id"]
    stats = await get_dashboard_stats(company_id)
    return stats


@router.get("/tickets")
async def get_tickets(
    status: Optional[str] = None,
    user: dict = Depends(require_staff),
):
    """
    List tickets for the company, optionally filtered by status.
    
    Status values: pending, assigned, resolved.
    """
    company_id = user["company_id"]
    tickets = await list_tickets(company_id, status=status)
    return {"tickets": tickets, "total": len(tickets)}


@router.patch("/tickets/{ticket_id}")
async def resolve_ticket_endpoint(
    ticket_id: str,
    request: ResolveTicketRequest,
    user: dict = Depends(require_admin),
):
    """
    Resolve an escalated ticket.
    
    If ingest_to_kb is True (default), the resolution is automatically
    embedded and indexed into the knowledge base — this is the
    HUMAN-IN-THE-LOOP LEARNING LOOP.
    """
    company_id = user["company_id"]

    # Resolve the ticket in MongoDB — returns the ticket doc (with customer_message)
    resolved = await resolve_ticket(ticket_id, company_id, request.resolution)
    if not resolved:
        raise HTTPException(status_code=404, detail="Ticket not found")

    # Learning loop: ingest the resolution into the KB
    ingest_result = None
    if request.ingest_to_kb:
        try:
            ingest_result = await ingest_resolved_ticket(
                company_id=company_id,
                ticket_id=ticket_id,
                question=resolved.get("customer_message", ""),  # actual customer question
                resolution=request.resolution,
                category=request.category,
                tags=request.tags,
            )
            logger.info(
                f"Learning loop: ticket {ticket_id} resolution "
                f"ingested into KB for company {company_id}"
            )
        except Exception as e:
            logger.error(f"Failed to ingest resolution into KB: {e}")

    return {
        "status": "resolved",
        "ticket_id": ticket_id,
        "kb_ingested": ingest_result is not None,
    }


@router.get("/audit")
async def get_audit(
    limit: int = 50,
    user: dict = Depends(require_staff),
):
    """
    Get recent audit logs for the company.
    Shows all AI interactions with provenance data.
    """
    company_id = user["company_id"]
    logs = await get_audit_logs(company_id, limit=limit)
    return {"audit_logs": logs, "total": len(logs)}

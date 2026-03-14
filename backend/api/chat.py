# =============================================================================
# api/chat.py — Chat Widget Endpoint (The Public-Facing API)
# =============================================================================
# This is the endpoint that the embeddable widget calls.
# Authentication is via X-API-Key header (not JWT).
# Implements: Rate Limiting → Auth → Orchestrator → Response.
# =============================================================================

import logging

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from api.auth import get_company_from_api_key
from services.redis_cache import check_rate_limit
from services.orchestrator import process, OrchestratorResult

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/chat", tags=["Chat Widget"])


# =============================================================================
# Request/Response Models
# =============================================================================

class ChatRequest(BaseModel):
    """Incoming chat message from the widget."""
    customer_message: str
    customer_id: str = ""  # Optional: for session tracking


class ChatResponse(BaseModel):
    """
    Response sent back to the chat widget.
    
    Actions:
        - auto_reply: AI generated an answer from the KB
        - clarify: AI needs more info, suggests related topics
        - escalate: Routing to human agent
    """
    action: str
    message: str
    sources: list[str] = []
    suggested_docs: list[str] = []
    context_passed_to_agent: bool = False


# =============================================================================
# Routes
# =============================================================================

@router.post("/incoming", response_model=ChatResponse)
async def incoming_message(
    request: ChatRequest,
    company_id: str = Depends(get_company_from_api_key),
):
    """
    Process an incoming customer support message.
    
    This is the main entry point for the embeddable chat widget.
    The full flow:
    1. Rate Limiting (Redis) — 429 if exceeded
    2. Auth Validation (API Key → company_id)
    3. Orchestrator processes the message through the decision engine
    4. Returns action + response to the widget
    
    The widget communicates with this endpoint via:
        POST /api/v1/chat/incoming
        Headers: { "X-API-Key": "pk_live_xxx" }
        Body: { "customer_message": "...", "customer_id": "optional" }
    """

    # --- Step 1: Rate Limiting ---
    # company_id was already extracted by the dependency
    allowed = await check_rate_limit(company_id)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Too many requests. Please try again in a moment.",
        )

    # --- Step 2: Validate input ---
    if not request.customer_message.strip():
        raise HTTPException(
            status_code=400,
            detail="Message cannot be empty.",
        )

    # --- Step 3: Process through the orchestrator ---
    try:
        result: OrchestratorResult = await process(
            customer_message=request.customer_message,
            company_id=company_id,
        )
    except Exception as e:
        # CRITICAL FALLBACK: If ANYTHING fails, escalate gracefully.
        # The customer must NEVER be left without a response.
        logger.error(f"Orchestrator failure: {e}", exc_info=True)
        result = OrchestratorResult(
            action="escalate",
            message="I'm experiencing a technical issue. Let me connect you with a human agent who can help right away.",
            context_passed_to_agent=True,
        )

    # --- Step 4: Return response ---
    return ChatResponse(
        action=result.action,
        message=result.message,
        sources=result.sources,
        suggested_docs=result.suggested_docs,
        context_passed_to_agent=result.context_passed_to_agent,
    )

# =============================================================================
# services/orchestrator.py — The Agentic Decision Engine ("The Brain")
# =============================================================================
# Ties together intent classification, vector search, confidence scoring,
# and the decision matrix to autonomously handle support queries.
#
# Decision Flow:
#   1. Intent classification (LLM fast call)
#   2. Safety check (human_escalation → instant escalate)
#   3. Vectorize message (local embedding)
#   4. Search Endee (top-10 with company_id filter)
#   5. Score & rank results (weighted composite score)
#   6. Decision matrix:
#      - High confidence (≥0.82) → RAG auto-reply
#      - Medium confidence (0.60–0.82) → Clarify
#      - Low confidence (<0.60) → Escalate
# =============================================================================

import logging
import time
from datetime import datetime, timezone
from dataclasses import dataclass

from core.config import get_settings
from services.embedding import embedding_service
from services.endee_client import endee_client
from services import llm as llm_service
from services.mongo import (
    ChatSession,
    Ticket,
    AuditLog,
    log_chat_session,
    create_ticket,
    log_audit,
)

logger = logging.getLogger(__name__)


@dataclass
class OrchestratorResult:
    """
    The output of the orchestrator's decision process.
    
    Attributes:
        action: One of "auto_reply", "clarify", "escalate".
        message: The response message to send to the customer.
        sources: List of source ticket/doc IDs used in the answer.
        suggested_docs: Summaries of candidate docs (for clarify action).
        context_passed_to_agent: Whether context was passed to human (for escalate).
        confidence: The computed confidence score.
        intent: The classified intent category.
    """
    action: str
    message: str
    sources: list[str] = None
    suggested_docs: list[str] = None
    context_passed_to_agent: bool = False
    confidence: float = 0.0
    intent: str = "general"

    def __post_init__(self):
        self.sources = self.sources or []
        self.suggested_docs = self.suggested_docs or []

    def to_dict(self) -> dict:
        """Convert to API response dict."""
        result = {
            "action": self.action,
            "message": self.message,
        }
        if self.sources:
            result["sources"] = self.sources
        if self.suggested_docs:
            result["suggested_docs"] = self.suggested_docs
        if self.action == "escalate":
            result["context_passed_to_agent"] = self.context_passed_to_agent
        return result


def compute_weighted_score(
    similarity: float,
    intent_match: bool,
    recency_factor: float = 1.0,
    source_reliability: float = 1.0,
) -> float:
    """
    Compute a weighted composite confidence score.
    
    Formula: similarity * 0.5 + intent_match * 0.2 + recency * 0.15 + reliability * 0.15
    
    Args:
        similarity: Raw cosine similarity from Endee (0-1).
        intent_match: Whether the result's category matches the classified intent.
        recency_factor: How recent the document is (0-1, 1 = very recent).
        source_reliability: Reliability score of the source (0-1).
        
    Returns:
        Weighted score between 0 and 1.
    """
    intent_score = 1.0 if intent_match else 0.5
    return (
        similarity * 0.50
        + intent_score * 0.20
        + recency_factor * 0.15
        + source_reliability * 0.15
    )


async def process(
    customer_message: str,
    company_id: str,
) -> OrchestratorResult:
    """
    Main orchestration pipeline. This is the "Brain" of the system.
    
    Processes an incoming customer message through the full decision flow:
    intent → safety → embed → search → score → decide → respond.
    
    Args:
        customer_message: The raw customer support message.
        company_id: The tenant company ID for data isolation.
        
    Returns:
        OrchestratorResult with the action decision and response.
    """
    settings = get_settings()
    start_time = time.time()

    # =========================================================================
    # STEP 1: Intent Classification
    # =========================================================================
    intent = await llm_service.classify_intent(customer_message)
    logger.info(f"Intent: {intent} | Message: '{customer_message[:60]}...'")

    # =========================================================================
    # STEP 2: Safety Check — Immediate escalation triggers
    # =========================================================================
    if intent == "human_escalation":
        logger.info("Human escalation intent detected — escalating immediately")

        # Log the session
        session_id = await log_chat_session(ChatSession(
            company_id=company_id,
            message=customer_message,
            action="escalate",
            response="Customer requested human agent.",
            intent=intent,
        ))

        # Create a ticket for the human agent
        await create_ticket(Ticket(
            company_id=company_id,
            chat_session_id=session_id,
            customer_message=customer_message,
            ai_context="Customer explicitly requested to speak to a human agent.",
            status="pending",
        ))

        # Audit log
        await _log_audit(
            company_id=company_id,
            event_type="escalation",
            request=customer_message,
            response="Immediate escalation: human requested",
            latency_ms=_elapsed_ms(start_time),
            confidence=0.0,
        )

        return OrchestratorResult(
            action="escalate",
            message="I understand you'd like to speak with a human agent. I'm routing your request now — an agent will be with you shortly.",
            context_passed_to_agent=True,
            intent=intent,
        )

    # =========================================================================
    # STEP 3: Vectorize the customer message
    # =========================================================================
    query_vector = embedding_service.encode(customer_message)

    # =========================================================================
    # STEP 4: Search Endee (Top 10, filtered by company_id)
    # =========================================================================
    search_results = endee_client.search(
        query_vector=query_vector,
        top_k=10,
        filters={"company_id": company_id},
    )

    # =========================================================================
    # STEP 5: Score & Rank Results
    # =========================================================================
    if not search_results:
        # No results at all → escalate
        logger.info("No search results found — escalating")
        return await _handle_escalation(
            customer_message, company_id, intent, start_time,
            reason="No matching documents found in knowledge base.",
        )

    # Compute weighted scores for each result
    scored_results = []
    for result in search_results:
        meta = result.get("meta", {})
        raw_similarity = result.get("similarity", 0.0)

        # Check if the result's category matches the intent
        result_category = meta.get("category", "general")
        # Resolved tickets: human verified → always trust regardless of category
        is_resolved = meta.get("is_resolved", "false") == "true"
        intent_match = is_resolved or (result_category == intent) or (intent == "general")

        # Compute reliability (resolved tickets are more reliable)
        reliability = 1.0 if is_resolved else 0.8

        weighted = compute_weighted_score(
            similarity=raw_similarity,
            intent_match=intent_match,
            recency_factor=0.8,  # Default for now
            source_reliability=reliability,
        )

        scored_results.append({
            **result,
            "weighted_score": weighted,
            "raw_similarity": raw_similarity,
        })

    # Sort by weighted score (highest first)
    scored_results.sort(key=lambda x: x["weighted_score"], reverse=True)

    # Top score determines the action
    top_score = scored_results[0]["weighted_score"]
    top_3 = scored_results[:3]

    logger.info(
        f"Top score: {top_score:.3f} | "
        f"Raw similarity: {scored_results[0]['raw_similarity']:.3f} | "
        f"Results: {len(scored_results)}"
    )

    # =========================================================================
    # STEP 6: Decision Matrix
    # =========================================================================

    # --- HIGH CONFIDENCE: Auto-resolve with RAG ---
    if top_score >= settings.AUTO_RESOLVE_THRESHOLD:
        return await _handle_auto_reply(
            customer_message, company_id, intent, top_3,
            top_score, start_time,
        )

    # --- MEDIUM CONFIDENCE: Ask for clarification ---
    if top_score >= settings.CLARIFY_THRESHOLD:
        return await _handle_clarify(
            customer_message, company_id, intent, top_3,
            top_score, start_time,
        )

    # --- LOW CONFIDENCE: Escalate to human ---
    return await _handle_escalation(
        customer_message, company_id, intent, start_time,
        reason=f"Low confidence score ({top_score:.2f}). No reliable KB match found.",
        candidates=top_3,
    )


# =============================================================================
# Action Handlers
# =============================================================================

async def _handle_auto_reply(
    message: str,
    company_id: str,
    intent: str,
    top_results: list[dict],
    confidence: float,
    start_time: float,
) -> OrchestratorResult:
    """Handle high-confidence auto-reply using RAG generation."""

    # Build context docs for RAG
    context_docs = []
    source_ids = []
    for r in top_results:
        meta = r.get("meta", {})
        context_docs.append({
            "ticket_id": meta.get("ticket_id", meta.get("doc_id", r.get("id", ""))),
            "raw_text": meta.get("raw_text", ""),
            "category": meta.get("category", "general"),
        })
        source_id = meta.get("ticket_id") or meta.get("doc_id") or r.get("id", "")
        if source_id and source_id not in source_ids:
            source_ids.append(source_id)

    # Generate RAG response
    answer = await llm_service.generate_rag_response(message, context_docs)

    # If the LLM itself says ESCALATE, respect that
    if answer.strip().upper() == "ESCALATE":
        logger.info("LLM returned ESCALATE — context insufficient")
        return await _handle_escalation(
            message, company_id, intent, start_time,
            reason="LLM determined context was insufficient for a reliable answer.",
            candidates=top_results,
        )

    # Log the successful auto-reply
    await log_chat_session(ChatSession(
        company_id=company_id,
        message=message,
        action="auto_reply",
        response=answer,
        confidence=confidence,
        intent=intent,
        sources=source_ids,
    ))

    # Audit log
    await _log_audit(
        company_id=company_id,
        event_type="rag_generation",
        request=message,
        response=f"Auto-reply: {answer[:100]}{'...' if len(answer) > 100 else ''}",
        latency_ms=_elapsed_ms(start_time),
        sources=source_ids,
        confidence=confidence,
    )

    return OrchestratorResult(
        action="auto_reply",
        message=answer,
        sources=source_ids,
        confidence=confidence,
        intent=intent,
    )


async def _handle_clarify(
    message: str,
    company_id: str,
    intent: str,
    top_results: list[dict],
    confidence: float,
    start_time: float,
) -> OrchestratorResult:
    """Handle medium-confidence by asking a clarifying question."""

    # Build candidate summaries
    candidate_docs = []
    for r in top_results:
        meta = r.get("meta", {})
        candidate_docs.append({
            "title": meta.get("title", "Unknown"),
            "ticket_id": meta.get("ticket_id", ""),
            "summary": meta.get("raw_text", "")[:150],
            "category": meta.get("category", "general"),
        })

    # Generate clarifying question
    clarify_msg = await llm_service.generate_clarifying_question(
        message, candidate_docs
    )

    suggested = [
        f"{doc['title']}: {doc['summary'][:80]}..."
        for doc in candidate_docs
        if doc.get("title")
    ]

    # Log session
    await log_chat_session(ChatSession(
        company_id=company_id,
        message=message,
        action="clarify",
        response=clarify_msg,
        confidence=confidence,
        intent=intent,
    ))

    # Audit log
    await _log_audit(
        company_id=company_id,
        event_type="clarification",
        request=message,
        response=f"Clarify: {clarify_msg[:100]}...",
        latency_ms=_elapsed_ms(start_time),
        confidence=confidence,
    )

    return OrchestratorResult(
        action="clarify",
        message=clarify_msg,
        suggested_docs=suggested,
        confidence=confidence,
        intent=intent,
    )


async def _handle_escalation(
    message: str,
    company_id: str,
    intent: str,
    start_time: float,
    reason: str = "",
    candidates: list[dict] | None = None,
) -> OrchestratorResult:
    """Handle low-confidence by escalating to a human agent."""

    # Build context for the human agent
    candidate_sources = []
    if candidates:
        for r in candidates:
            meta = r.get("meta", {})
            source_id = meta.get("ticket_id") or meta.get("doc_id") or r.get("id", "")
            if source_id:
                candidate_sources.append(source_id)

    # Log session
    session_id = await log_chat_session(ChatSession(
        company_id=company_id,
        message=message,
        action="escalate",
        response=reason,
        confidence=0.0,
        intent=intent,
    ))

    # Create ticket for human agent
    await create_ticket(Ticket(
        company_id=company_id,
        chat_session_id=session_id,
        customer_message=message,
        ai_context=reason,
        candidate_sources=candidate_sources,
        status="pending",
    ))

    # Audit log
    await _log_audit(
        company_id=company_id,
        event_type="escalation",
        request=message,
        response=f"Escalated: {reason}",
        latency_ms=_elapsed_ms(start_time),
    )

    return OrchestratorResult(
        action="escalate",
        message="I'm routing your request to a human agent who can help you directly. An agent will be with you shortly.",
        context_passed_to_agent=True,
        confidence=0.0,
        intent=intent,
    )


# =============================================================================
# Helpers
# =============================================================================

def _elapsed_ms(start_time: float) -> float:
    """Calculate elapsed time in milliseconds."""
    return round((time.time() - start_time) * 1000, 2)


async def _log_audit(
    company_id: str,
    event_type: str,
    request: str,
    response: str,
    latency_ms: float,
    sources: list[str] | None = None,
    confidence: float = 0.0,
) -> None:
    """Helper to create an audit log entry."""
    settings = get_settings()
    try:
        await log_audit(AuditLog(
            company_id=company_id,
            event_type=event_type,
            request_summary=request[:200],
            response_summary=response[:200],
            latency_ms=latency_ms,
            model=settings.LLM_MODEL,
            sources=sources or [],
            confidence=confidence,
        ))
    except Exception as e:
        logger.error(f"Failed to write audit log: {e}")


# =============================================================================
# Conversation-Aware Entry Point (for the new widget/conversation endpoints)
# =============================================================================

async def process_conversation_message(
    customer_message: str,
    company_id: str,
    conversation_id: str,
    company_settings: dict | None = None,
) -> OrchestratorResult:
    """
    Conversation-aware decision engine entry point.

    Identical logic to `process()` but:
    - Uses company_settings for configurable thresholds (falls back to defaults)
    - Does NOT create Ticket or ChatSession records — caller handles persistence
    - Caller is responsible for creating Message records in the Conversation

    Args:
        customer_message: The raw customer support message.
        company_id: Tenant company ID.
        conversation_id: The active conversation ID (for logging context).
        company_settings: Company-level overrides for thresholds.

    Returns:
        OrchestratorResult with action, message, sources, confidence.
    """
    settings = get_settings()
    settings_dict = company_settings or {}

    # Per-company configurable thresholds (default to global settings)
    auto_resolve_threshold = float(
        settings_dict.get("auto_resolve_threshold", settings.AUTO_RESOLVE_THRESHOLD)
    )
    clarify_threshold = float(
        settings_dict.get("clarify_threshold", settings.CLARIFY_THRESHOLD)
    )

    start_time = time.time()

    # --- Step 1: Intent classification ---
    intent = await llm_service.classify_intent(customer_message)
    logger.info(
        f"[conv:{conversation_id}] Intent={intent} | "
        f"Message='{customer_message[:60]}'"
    )

    # --- Step 2: Immediate escalation for human request ---
    if intent == "human_escalation":
        return OrchestratorResult(
            action="escalate",
            message="Understood — I'm connecting you with a human agent now. "
                    "Someone will be with you shortly.",
            context_passed_to_agent=True,
            confidence=0.0,
            intent=intent,
        )

    # --- Step 3: Embed the customer message ---
    query_vector = embedding_service.encode(customer_message)

    # --- Step 4: Vector search (top-10, company-scoped) ---
    search_results = endee_client.search(
        query_vector=query_vector,
        top_k=10,
        filters={"company_id": company_id},
    )

    if not search_results:
        return OrchestratorResult(
            action="escalate",
            message="I wasn't able to find a relevant answer in the knowledge base. "
                    "Let me connect you with a team member.",
            context_passed_to_agent=True,
            confidence=0.0,
            intent=intent,
        )

    # --- Step 5: Score & rank ---
    scored = []
    for result in search_results:
        meta = result.get("meta", {})
        similarity = result.get("similarity", 0.0)
        result_category = meta.get("category", "general")
        # Resolved tickets: human verified → always trust regardless of category
        is_resolved = meta.get("is_resolved", "false") == "true"
        intent_match = is_resolved or (result_category == intent) or (intent == "general")
        reliability = 1.0 if is_resolved else 0.8
        weighted = compute_weighted_score(
            similarity=similarity,
            intent_match=intent_match,
            recency_factor=0.8,
            source_reliability=reliability,
        )
        scored.append({**result, "weighted_score": weighted, "raw_similarity": similarity})

    scored.sort(key=lambda x: x["weighted_score"], reverse=True)
    top_score = scored[0]["weighted_score"]
    top_3 = scored[:3]

    logger.info(
        f"[conv:{conversation_id}] Top score={top_score:.3f} | "
        f"Raw similarity={scored[0]['raw_similarity']:.3f}"
    )

    # --- Step 6: Decision (uses company-specific thresholds) ---

    if top_score >= auto_resolve_threshold:
        context_docs = [
            {
                "ticket_id": r.get("meta", {}).get("ticket_id", r.get("id", "")),
                "raw_text": r.get("meta", {}).get("raw_text", ""),
                "category": r.get("meta", {}).get("category", "general"),
            }
            for r in top_3
        ]
        answer = await llm_service.generate_rag_response(customer_message, context_docs)

        if answer.strip().upper() == "ESCALATE":
            return OrchestratorResult(
                action="escalate",
                message="The available information wasn't sufficient to answer confidently. "
                        "A team member will assist you.",
                context_passed_to_agent=True,
                confidence=top_score,
                intent=intent,
            )

        sources = [
            r.get("meta", {}).get("ticket_id") or r.get("meta", {}).get("doc_id") or r.get("id", "")
            for r in top_3 if r.get("meta", {}).get("ticket_id") or r.get("id")
        ]
        elapsed = _elapsed_ms(start_time)
        logger.info(f"[conv:{conversation_id}] Auto-reply ({elapsed}ms, score={top_score:.3f})")
        return OrchestratorResult(
            action="auto_reply",
            message=answer,
            sources=sources,
            confidence=top_score,
            intent=intent,
        )

    if top_score >= clarify_threshold:
        candidate_docs = [
            {
                "title": r.get("meta", {}).get("title", "Unknown"),
                "ticket_id": r.get("meta", {}).get("ticket_id", ""),
                "summary": r.get("meta", {}).get("raw_text", "")[:150],
                "category": r.get("meta", {}).get("category", "general"),
            }
            for r in top_3
        ]
        clarify_msg = await llm_service.generate_clarifying_question(
            customer_message, candidate_docs
        )
        suggested = [
            f"{d['title']}: {d['summary'][:80]}..." for d in candidate_docs if d.get("title")
        ]
        return OrchestratorResult(
            action="clarify",
            message=clarify_msg,
            suggested_docs=suggested,
            confidence=top_score,
            intent=intent,
        )

    # Low confidence — escalate
    return OrchestratorResult(
        action="escalate",
        message="I want to make sure you get the right answer. "
                "Let me connect you with a team member who can help.",
        context_passed_to_agent=True,
        confidence=top_score,
        intent=intent,
    )

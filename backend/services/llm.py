# =============================================================================
# services/llm.py — Google Gemini LLM Service (httpx REST)
# =============================================================================
# Calls the Gemini REST API directly using httpx.AsyncClient.
# Provides intent classification, RAG generation, clarification, and scoring.
# All calls are wrapped in try/except — any failure defaults to ESCALATE.
# =============================================================================

import logging
import httpx
from core.config import get_settings
from core.prompts import (
    INTENT_CLASSIFICATION_PROMPT,
    RAG_SYSTEM_PROMPT,
    RAG_USER_PROMPT,
    CLARIFY_PROMPT,
    CONFIDENCE_SCORING_PROMPT,
)

logger = logging.getLogger(__name__)

settings = get_settings()

GEMINI_API_ENDPOINT = (
    "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
)

# Valid intent categories for validation
VALID_INTENTS = {
    "billing", "technical", "cancellation",
    "account", "general", "human_escalation",
}


async def _call_gemini(
    user_prompt: str,
    system_prompt: str | None = None,
    max_tokens: int = 300,
    temperature: float = 0.3,
) -> str:
    """
    Low-level helper: POST to Gemini generateContent and return the text.

    Args:
        user_prompt:   The user-turn content.
        system_prompt: Optional system instruction.
        max_tokens:    Maximum output tokens.
        temperature:   Sampling temperature.

    Returns:
        Stripped text from the first candidate.

    Raises:
        httpx.HTTPError or KeyError on network/parse failure (caller catches).
    """
    payload: dict = {
        "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
        "generationConfig": {
            "maxOutputTokens": max_tokens,
            "temperature": temperature,
        },
    }
    if system_prompt:
        payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}

    url = f"{GEMINI_API_ENDPOINT}?key={settings.GEMINI_API_KEY}"

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()
        data = response.json()
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()


# =============================================================================
async def classify_intent(message: str) -> str:
    """
    Classify the customer's intent using Gemini.

    Returns one of: billing, technical, cancellation, account,
    general, or human_escalation. Defaults to "general" on failure.
    """
    try:
        prompt = INTENT_CLASSIFICATION_PROMPT.format(message=message)
        intent = await _call_gemini(prompt, max_tokens=20, temperature=0.0)
        intent = intent.lower()

        if intent in VALID_INTENTS:
            logger.info(f"Intent classified: '{intent}' for: '{message[:50]}…'")
            return intent

        logger.warning(f"Unknown intent '{intent}', defaulting to 'general'")
        return "general"

    except Exception as e:
        logger.error(f"Intent classification failed: {e}")
        return "general"


# =============================================================================
async def generate_rag_response(
    question: str,
    context_docs: list[dict],
) -> str:
    """
    Generate an answer using RAG (Retrieval-Augmented Generation).

    Constructs a context string from retrieved documents and asks Gemini
    to answer using ONLY that context. Returns "ESCALATE" when context
    is insufficient or any error occurs.
    """
    try:
        context_parts = []
        for i, doc in enumerate(context_docs, 1):
            ticket_id = doc.get("ticket_id", doc.get("id", f"doc_{i}"))
            text = doc.get("raw_text", doc.get("text", ""))
            category = doc.get("category", "general")
            context_parts.append(
                f"[Source: {ticket_id}] (Category: {category})\n{text}"
            )

        context = "\n\n---\n\n".join(context_parts)
        user_prompt = RAG_USER_PROMPT.format(context=context, question=question)

        answer = await _call_gemini(
            user_prompt=user_prompt,
            system_prompt=RAG_SYSTEM_PROMPT,
            max_tokens=300,
            temperature=0.3,
        )
        logger.info(f"RAG response generated ({len(answer)} chars)")
        return answer

    except Exception as e:
        logger.error(f"RAG generation failed: {e}")
        return "ESCALATE"


# =============================================================================
async def generate_clarifying_question(
    message: str,
    candidate_docs: list[dict],
) -> str:
    """
    Generate a clarifying question when confidence is medium.

    Returns a friendly question string to help narrow down the issue.
    """
    try:
        candidates = "\n".join(
            f"- {doc.get('title', doc.get('ticket_id', 'Unknown'))}: "
            f"{doc.get('summary', doc.get('raw_text', '')[:100])}"
            for doc in candidate_docs
        )
        prompt = CLARIFY_PROMPT.format(message=message, candidates=candidates)
        return await _call_gemini(prompt, max_tokens=100, temperature=0.5)

    except Exception as e:
        logger.error(f"Clarifying question generation failed: {e}")
        return "Could you provide more details about your issue so we can help you better?"


# =============================================================================
async def score_confidence(question: str, context: str) -> float:
    """
    Ask Gemini to self-assess how well the context answers the question.

    Returns a float in [0.0, 1.0]. Defaults to 0.0 on failure.
    """
    try:
        prompt = CONFIDENCE_SCORING_PROMPT.format(context=context, question=question)
        score_str = await _call_gemini(prompt, max_tokens=10, temperature=0.0)
        score = float(score_str)
        return max(0.0, min(1.0, score))

    except Exception as e:
        logger.error(f"Confidence scoring failed: {e}")
        return 0.0

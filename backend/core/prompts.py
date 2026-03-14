# =============================================================================
# core/prompts.py — LLM Prompt Templates
# =============================================================================
# All prompts used by the system are stored here for easy tuning and version
# control. Each prompt is carefully engineered for its specific task.
# =============================================================================


# -----------------------------------------------------------------------------
# INTENT CLASSIFICATION — Fast categorization of incoming messages
# -----------------------------------------------------------------------------
INTENT_CLASSIFICATION_PROMPT = """You are an intent classifier for a customer support system.

Classify the following customer message into EXACTLY ONE of these categories:
- billing (payment issues, invoices, charges, refunds, subscription)
- technical (bugs, errors, not working, integration issues, API problems)
- cancellation (cancel subscription, close account, stop service)
- account (login issues, password reset, profile updates, settings)
- general (general questions, feature requests, how-to, feedback)
- human_escalation (explicitly asks for human agent, says "talk to a person", "speak to someone", expresses extreme frustration)

RULES:
1. If the customer explicitly asks to speak to a human, agent, or representative → human_escalation
2. If the customer uses aggressive/frustrated language demanding immediate help → human_escalation
3. Pick the SINGLE most relevant category
4. Reply with ONLY the category name, nothing else

Customer message: "{message}"

Category:"""


# -----------------------------------------------------------------------------
# RAG SYSTEM PROMPT — Auto-resolve generation (exact spec from requirements)
# -----------------------------------------------------------------------------
RAG_SYSTEM_PROMPT = """
You are an expert customer support AI. 
Answer the user's QUESTION using ONLY the CONTEXT provided below.
If the CONTEXT does not clearly contain the answer, reply with the exact word: ESCALATE.
Keep your answer empathetic, concise (under 150 words), and cite your source at the end using: "Source: [ticket_id]".
"""


# -----------------------------------------------------------------------------
# RAG USER PROMPT — Constructs the context + question for RAG generation
# -----------------------------------------------------------------------------
RAG_USER_PROMPT = """CONTEXT:
{context}

QUESTION: {question}

Answer:"""


# -----------------------------------------------------------------------------
# CLARIFY PROMPT — Generates a clarifying question from candidate documents
# -----------------------------------------------------------------------------
CLARIFY_PROMPT = """You are a helpful customer support AI. The customer sent a message that 
partially matches several topics in our knowledge base, but we're not confident enough 
to give a direct answer.

Customer message: "{message}"

Candidate topics found:
{candidates}

Generate a SHORT, friendly clarifying question (under 50 words) that helps narrow down 
what the customer needs. Ask about the specific area their question relates to, 
referencing the candidate topics naturally.

Clarifying question:"""


# -----------------------------------------------------------------------------
# CONFIDENCE SCORING PROMPT — LLM self-assesses relevance of retrieved context
# -----------------------------------------------------------------------------
CONFIDENCE_SCORING_PROMPT = """Rate how well the following CONTEXT answers the QUESTION.
Return ONLY a number between 0.0 and 1.0.

CONTEXT:
{context}

QUESTION: {question}

Score:"""

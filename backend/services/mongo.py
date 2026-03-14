# =============================================================================
# services/mongo.py — MongoDB Async Client + Data Models
# =============================================================================
# Uses Motor (async MongoDB driver) for all database operations.
# Defines Pydantic models for all collections and provides CRUD helpers.
#
# Collections:
#   companies, users, api_keys, documents, chat_sessions, tickets,
#   audit_logs, conversations, messages, kb_entries
# =============================================================================

import logging
import re
import uuid as _uuid
from datetime import datetime, timezone
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pydantic import BaseModel, Field
from core.config import get_settings

logger = logging.getLogger(__name__)

# --- Module-level database reference (set during startup) ---
_db: Optional[AsyncIOMotorDatabase] = None
_client: Optional[AsyncIOMotorClient] = None


# =============================================================================
# Pydantic Data Models — Legacy (kept for backwards compatibility)
# =============================================================================

class Company(BaseModel):
    """A registered company/tenant on the platform."""
    name: str
    slug: str = ""
    domain: str = ""
    owner_admin_id: str = ""
    settings: dict = Field(default_factory=lambda: {
        "auto_resolve_threshold": 0.82,
        "clarify_threshold": 0.60,
        "auto_resolve_auto_close": True,
    })
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class User(BaseModel):
    """A user belonging to a company (staff, admin) or global (superadmin)."""
    user_id: str = Field(default_factory=lambda: str(_uuid.uuid4()))
    email: str
    hashed_password: str
    company_id: str = ""   # empty string for superadmin
    name: str = ""
    role: str = "admin"    # superadmin | admin | staff
    enabled: bool = True
    created_by: str = ""   # user_id of creator (empty for self-registration)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ApiKey(BaseModel):
    """An API key linked to a company for widget authentication."""
    key: str
    company_id: str
    active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Document(BaseModel):
    """A knowledge base document that has been ingested (legacy)."""
    company_id: str
    title: str
    source_type: str  # text | pdf | slack | email | confluence | notion | drive | ticket
    content: str
    chunk_count: int = 0
    metadata: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ChatSession(BaseModel):
    """A single chat interaction from the legacy widget endpoint."""
    company_id: str
    customer_id: str = ""
    message: str
    action: str  # auto_reply | clarify | escalate
    response: str = ""
    confidence: float = 0.0
    intent: str = "general"
    sources: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Ticket(BaseModel):
    """An escalated support ticket for human agents (legacy)."""
    company_id: str
    chat_session_id: str = ""
    customer_message: str
    ai_context: str = ""
    candidate_sources: list[str] = Field(default_factory=list)
    status: str = "pending"  # pending | assigned | resolved
    assigned_to: str = ""
    resolution: str = ""
    resolved_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AuditLog(BaseModel):
    """Audit log entry for every AI interaction."""
    company_id: str
    user_id: str = ""   # staff user_id who acted (empty for AI/widget)
    event_type: str     # intent_classification | rag_generation | escalation | resolve | staff_reply
    request_summary: str
    response_summary: str
    latency_ms: float = 0.0
    model: str = ""
    sources: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# =============================================================================
# Pydantic Data Models — New (Multi-Tenant RBAC)
# =============================================================================

class Conversation(BaseModel):
    """
    A support conversation between a customer and AI/staff.
    One active conversation per widget_session_id at a time.
    """
    company_id: str
    customer_id: str                    # widget_session_id or user identifier
    widget_session_id: str = ""
    status: str = "active"              # active | resolved | archived
    assigned_staff_id: str = ""         # user_id of assigned staff
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    resolved_at: Optional[datetime] = None
    resolved_by_user_id: str = ""       # user_id of staff who resolved
    deleted_by_user: bool = False       # soft-delete from customer side


class Message(BaseModel):
    """
    A single message within a Conversation.
    Sender types: ai, staff, admin, customer
    """
    conversation_id: str
    company_id: str                     # denormalised for efficient queries
    sender_type: str                    # ai | staff | admin | customer
    sender_id: str = ""                 # user_id (empty for ai/anonymous customer)
    content: str
    metadata: dict = Field(default_factory=dict)  # sources, confidence, model, etc.
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class KBEntry(BaseModel):
    """
    A verified knowledge-base entry created from a resolved conversation.
    Gets embedded into Endee for future auto-resolution.
    """
    company_id: str
    source_type: str = "ticket_resolution"  # ticket_resolution | doc | faq
    title: str
    canonical_answer: str
    tags: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_by_user_id: str = ""            # user_id of staff who wrote it
    verified: bool = True
    version: int = 1
    endee_doc_id: str = ""                  # doc_id returned by Endee after ingestion


# =============================================================================
# Connection Management
# =============================================================================

async def connect_db() -> None:
    """Initialize the MongoDB connection and ensure all indexes."""
    global _client, _db
    settings = get_settings()
    logger.info(f"Connecting to MongoDB: {settings.MONGODB_URL}")
    _client = AsyncIOMotorClient(settings.MONGODB_URL)
    _db = _client.get_default_database()

    # --- Legacy indexes ---
    await _db.api_keys.create_index("key", unique=True)
    await _db.users.create_index("email", unique=True)
    await _db.chat_sessions.create_index("company_id")
    await _db.tickets.create_index([("company_id", 1), ("status", 1)])
    await _db.audit_logs.create_index([("company_id", 1), ("created_at", -1)])

    # --- New indexes ---
    await _db.companies.create_index("slug", unique=True, sparse=True)
    await _db.users.create_index("user_id", unique=True, sparse=True)
    await _db.conversations.create_index([("company_id", 1), ("customer_id", 1), ("status", 1)])
    await _db.conversations.create_index([("company_id", 1), ("status", 1)])
    await _db.messages.create_index("conversation_id")
    await _db.messages.create_index([("company_id", 1), ("created_at", -1)])
    await _db.kb_entries.create_index([("company_id", 1), ("created_at", -1)])
    await _db.audit_logs.create_index("user_id")

    logger.info("MongoDB connected and indexes created.")


async def close_db() -> None:
    """Close the MongoDB connection. Called during shutdown."""
    global _client
    if _client:
        _client.close()
        logger.info("MongoDB connection closed.")


def get_db() -> AsyncIOMotorDatabase:
    """Get the current database instance."""
    if _db is None:
        raise RuntimeError("Database not initialized. Call connect_db() first.")
    return _db


# =============================================================================
# Slug Helpers
# =============================================================================

def slugify(name: str) -> str:
    """Convert a company name into a URL-safe slug."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug[:50]


async def unique_slug(name: str) -> str:
    """Generate a unique slug, appending a counter if the base slug already exists."""
    db = get_db()
    base = slugify(name)
    candidate = base
    n = 1
    while await db.companies.find_one({"slug": candidate}):
        candidate = f"{base}-{n}"
        n += 1
    return candidate


# =============================================================================
# API Key Operations
# =============================================================================

async def validate_api_key(api_key: str) -> Optional[str]:
    """Validate an API key and return the associated company_id (Mongo ObjectId string)."""
    db = get_db()
    record = await db.api_keys.find_one({"key": api_key, "active": True})
    if record:
        return record["company_id"]
    return None


async def create_api_key(company_id: str, key: str) -> dict:
    """Create a new API key for a company."""
    db = get_db()
    doc = ApiKey(key=key, company_id=company_id).model_dump()
    result = await db.api_keys.insert_one(doc)
    doc["_id"] = str(result.inserted_id)
    return doc


async def list_api_keys(company_id: str) -> list[dict]:
    """List all API keys for a company (masks the key for security)."""
    db = get_db()
    cursor = db.api_keys.find({"company_id": company_id}).sort("created_at", -1)
    keys = await cursor.to_list(length=50)
    for k in keys:
        k["_id"] = str(k["_id"])
        # Mask the key: show first 12 + last 4 chars
        full_key = k.get("key", "")
        if len(full_key) > 16:
            k["key_masked"] = full_key[:12] + "…" + full_key[-4:]
        else:
            k["key_masked"] = full_key
    return keys


async def delete_api_key(key_id: str, company_id: str) -> bool:
    """Delete (revoke) an API key by its Mongo ObjectId."""
    from bson import ObjectId
    db = get_db()
    result = await db.api_keys.delete_one(
        {"_id": ObjectId(key_id), "company_id": company_id}
    )
    return result.deleted_count > 0


# =============================================================================
# Company Operations
# =============================================================================

async def create_company(name: str, domain: str = "", slug: str = "") -> dict:
    """
    Create a new company.

    Returns:
        dict with "company_id" (Mongo ObjectId string) and "slug".
    """
    db = get_db()
    resolved_slug = slug or await unique_slug(name)
    doc = Company(name=name, domain=domain, slug=resolved_slug).model_dump()
    result = await db.companies.insert_one(doc)
    company_id = str(result.inserted_id)
    return {"company_id": company_id, "slug": resolved_slug}


async def get_company(company_id: str) -> Optional[dict]:
    """Get company details by Mongo ObjectId string."""
    from bson import ObjectId
    db = get_db()
    doc = await db.companies.find_one({"_id": ObjectId(company_id)})
    if doc:
        doc["_id"] = str(doc["_id"])
    return doc


async def get_company_by_slug(slug: str) -> Optional[dict]:
    """Get company details by slug."""
    db = get_db()
    doc = await db.companies.find_one({"slug": slug})
    if doc:
        doc["_id"] = str(doc["_id"])
        if not doc.get("company_id"):
            doc["company_id"] = doc["_id"]
    return doc


async def update_company_settings(company_id: str, settings: dict) -> bool:
    """Merge-update the company settings dict."""
    from bson import ObjectId
    db = get_db()
    set_fields = {f"settings.{k}": v for k, v in settings.items()}
    result = await db.companies.update_one(
        {"_id": ObjectId(company_id)},
        {"$set": set_fields},
    )
    # Use matched_count: returns True even when values didn't change
    return result.matched_count > 0


async def set_company_owner(company_id: str, owner_user_id: str) -> None:
    """Set the owner_admin_id on a company after its first admin is created."""
    from bson import ObjectId
    db = get_db()
    await db.companies.update_one(
        {"_id": ObjectId(company_id)},
        {"$set": {"owner_admin_id": owner_user_id}},
    )


async def list_companies() -> list[dict]:
    """List all companies (SuperAdmin use)."""
    db = get_db()
    cursor = db.companies.find({}).sort("created_at", -1)
    companies = await cursor.to_list(length=500)
    for c in companies:
        c["_id"] = str(c["_id"])
        if not c.get("company_id"):
            c["company_id"] = c["_id"]
    return companies


# =============================================================================
# User Operations
# =============================================================================

async def create_user(
    email: str,
    hashed_password: str,
    company_id: str,
    role: str = "admin",
    name: str = "",
    enabled: bool = True,
    created_by: str = "",
) -> dict:
    """
    Create a new user.

    Returns:
        dict with "user_id" (UUID string) and "mongo_id" (Mongo ObjectId string).
    """
    db = get_db()
    user_id = str(_uuid.uuid4())
    doc = User(
        user_id=user_id,
        email=email,
        hashed_password=hashed_password,
        company_id=company_id,
        role=role,
        name=name,
        enabled=enabled,
        created_by=created_by,
    ).model_dump()
    result = await db.users.insert_one(doc)
    return {"user_id": user_id, "mongo_id": str(result.inserted_id)}


async def get_user_by_email(email: str) -> Optional[dict]:
    """Find a user by email address."""
    db = get_db()
    doc = await db.users.find_one({"email": email})
    if doc:
        doc["_id"] = str(doc["_id"])
    return doc


async def get_user_by_id(user_id: str) -> Optional[dict]:
    """Find a user by UUID user_id field."""
    db = get_db()
    doc = await db.users.find_one({"user_id": user_id})
    if doc:
        doc["_id"] = str(doc["_id"])
    return doc


async def list_users(company_id: str) -> list[dict]:
    """List all users for a company (staff + admin)."""
    db = get_db()
    cursor = db.users.find(
        {"company_id": company_id},
        {"hashed_password": 0},  # never return passwords
    ).sort("created_at", -1)
    users = await cursor.to_list(length=200)
    for u in users:
        u["_id"] = str(u["_id"])
    return users


async def list_all_users() -> list[dict]:
    """List all users across all companies (SuperAdmin use)."""
    db = get_db()
    cursor = db.users.find(
        {},
        {"hashed_password": 0},
    ).sort("created_at", -1)
    users = await cursor.to_list(length=1000)
    for u in users:
        u["_id"] = str(u["_id"])
    return users


async def update_user(user_id: str, company_id: str, data: dict) -> bool:
    """Update user fields (company-scoped). Cannot change email or company_id."""
    allowed = {"name", "role", "enabled"}
    safe_data = {k: v for k, v in data.items() if k in allowed}
    if not safe_data:
        return False
    db = get_db()
    result = await db.users.update_one(
        {"user_id": user_id, "company_id": company_id},
        {"$set": safe_data},
    )
    return result.modified_count > 0


async def disable_user(user_id: str, company_id: str) -> bool:
    """Soft-disable a user (does not delete)."""
    db = get_db()
    result = await db.users.update_one(
        {"user_id": user_id, "company_id": company_id},
        {"$set": {"enabled": False}},
    )
    return result.modified_count > 0


# =============================================================================
# Document Operations (Legacy KB)
# =============================================================================

async def create_document(doc: Document) -> str:
    """Insert a document record and return its Mongo ObjectId string."""
    db = get_db()
    data = doc.model_dump()
    result = await db.documents.insert_one(data)
    return str(result.inserted_id)


async def list_documents(company_id: str) -> list[dict]:
    """List all documents for a company (without full content)."""
    db = get_db()
    cursor = db.documents.find(
        {"company_id": company_id},
        {"content": 0},
    ).sort("created_at", -1)
    docs = await cursor.to_list(length=100)
    for d in docs:
        d["_id"] = str(d["_id"])
    return docs


async def delete_document(doc_id: str, company_id: str) -> bool:
    """Delete a document by ID (must belong to the company)."""
    from bson import ObjectId
    db = get_db()
    result = await db.documents.delete_one(
        {"_id": ObjectId(doc_id), "company_id": company_id}
    )
    return result.deleted_count > 0


# =============================================================================
# Chat Session Operations (Legacy)
# =============================================================================

async def log_chat_session(session: ChatSession) -> str:
    """Log a chat session and return its ID."""
    db = get_db()
    data = session.model_dump()
    result = await db.chat_sessions.insert_one(data)
    return str(result.inserted_id)


# =============================================================================
# Ticket Operations (Legacy)
# =============================================================================

async def create_ticket(ticket: Ticket) -> str:
    """Create an escalated ticket and return its ID."""
    db = get_db()
    data = ticket.model_dump()
    result = await db.tickets.insert_one(data)
    return str(result.inserted_id)


async def list_tickets(
    company_id: str, status: Optional[str] = None
) -> list[dict]:
    """List tickets for a company, optionally filtered by status."""
    db = get_db()
    query: dict = {"company_id": company_id}
    if status:
        query["status"] = status
    cursor = db.tickets.find(query).sort("created_at", -1)
    tickets = await cursor.to_list(length=100)
    for t in tickets:
        t["_id"] = str(t["_id"])
    return tickets


async def resolve_ticket(
    ticket_id: str, company_id: str, resolution: str
) -> dict | None:
    """Mark a ticket as resolved and return the full ticket document."""
    from bson import ObjectId
    db = get_db()
    ticket = await db.tickets.find_one(
        {"_id": ObjectId(ticket_id), "company_id": company_id}
    )
    if not ticket:
        return None
    await db.tickets.update_one(
        {"_id": ObjectId(ticket_id), "company_id": company_id},
        {
            "$set": {
                "status": "resolved",
                "resolution": resolution,
                "resolved_at": datetime.now(timezone.utc),
            }
        },
    )
    ticket["_id"] = str(ticket["_id"])
    return ticket


# =============================================================================
# Conversation Operations (New)
# =============================================================================

async def create_conversation(conv: Conversation) -> str:
    """Create a new conversation and return its Mongo ObjectId string."""
    db = get_db()
    data = conv.model_dump()
    result = await db.conversations.insert_one(data)
    return str(result.inserted_id)


async def get_conversation(conv_id: str) -> Optional[dict]:
    """Get a conversation by Mongo ObjectId string."""
    from bson import ObjectId
    db = get_db()
    doc = await db.conversations.find_one({"_id": ObjectId(conv_id)})
    if doc:
        doc["_id"] = str(doc["_id"])
    return doc


async def get_active_conversation(
    company_id: str, customer_id: str
) -> Optional[dict]:
    """
    Return the active conversation for a customer session, or None.
    Only one active conversation per (company_id, customer_id) is allowed.
    """
    db = get_db()
    doc = await db.conversations.find_one(
        {"company_id": company_id, "customer_id": customer_id,
         "status": "active", "deleted_by_user": {"$ne": True}}
    )
    if doc:
        doc["_id"] = str(doc["_id"])
    return doc


async def list_conversations(
    company_id: str,
    status: Optional[str] = None,
    assigned_staff_id: Optional[str] = None,
    limit: int = 100,
) -> list[dict]:
    """List conversations for a company with optional filters."""
    db = get_db()
    query: dict = {"company_id": company_id, "deleted_by_user": {"$ne": True}}
    if status:
        query["status"] = status
    if assigned_staff_id:
        query["assigned_staff_id"] = assigned_staff_id
    cursor = db.conversations.find(query).sort("created_at", -1)
    convs = await cursor.to_list(length=limit)
    for c in convs:
        c["_id"] = str(c["_id"])
    return convs


async def list_all_conversations(
    status: Optional[str] = None, limit: int = 200
) -> list[dict]:
    """List all conversations across all companies (SuperAdmin use)."""
    db = get_db()
    query: dict = {}
    if status:
        query["status"] = status
    cursor = db.conversations.find(query).sort("created_at", -1)
    convs = await cursor.to_list(length=limit)
    for c in convs:
        c["_id"] = str(c["_id"])
    return convs


async def update_conversation(conv_id: str, data: dict) -> bool:
    """Update conversation fields by Mongo ObjectId string."""
    from bson import ObjectId
    allowed = {
        "status", "assigned_staff_id", "resolved_at",
        "resolved_by_user_id", "deleted_by_user",
    }
    safe = {k: v for k, v in data.items() if k in allowed}
    if not safe:
        return False
    db = get_db()
    result = await db.conversations.update_one(
        {"_id": ObjectId(conv_id)},
        {"$set": safe},
    )
    return result.modified_count > 0


async def delete_conversation_user_side(
    conv_id: str, company_id: str
) -> dict:
    """
    Soft-delete a conversation from the customer's side.
    Only allowed when status == "resolved".

    Returns:
        {"ok": True} or {"error": "..."}
    """
    from bson import ObjectId
    db = get_db()
    conv = await db.conversations.find_one(
        {"_id": ObjectId(conv_id), "company_id": company_id}
    )
    if not conv:
        return {"error": "not_found"}
    if conv.get("status") != "resolved":
        return {"error": "not_resolved"}
    await db.conversations.update_one(
        {"_id": ObjectId(conv_id)},
        {"$set": {"deleted_by_user": True}},
    )
    return {"ok": True}


# =============================================================================
# Message Operations (New)
# =============================================================================

async def create_message(msg: Message) -> str:
    """Insert a message and return its Mongo ObjectId string."""
    db = get_db()
    data = msg.model_dump()
    result = await db.messages.insert_one(data)
    return str(result.inserted_id)


async def list_messages(conversation_id: str) -> list[dict]:
    """Get all messages for a conversation, ordered by creation time."""
    db = get_db()
    cursor = db.messages.find(
        {"conversation_id": conversation_id}
    ).sort("created_at", 1)
    msgs = await cursor.to_list(length=500)
    for m in msgs:
        m["_id"] = str(m["_id"])
    return msgs


# =============================================================================
# KB Entry Operations (New)
# =============================================================================

async def create_kb_entry(entry: KBEntry) -> str:
    """Insert a KB entry and return its Mongo ObjectId string."""
    db = get_db()
    data = entry.model_dump()
    result = await db.kb_entries.insert_one(data)
    return str(result.inserted_id)


async def list_kb_entries(company_id: str) -> list[dict]:
    """List all KB entries for a company."""
    db = get_db()
    cursor = db.kb_entries.find(
        {"company_id": company_id}
    ).sort("created_at", -1)
    entries = await cursor.to_list(length=200)
    for e in entries:
        e["_id"] = str(e["_id"])
    return entries


async def update_kb_entry(entry_id: str, company_id: str, data: dict) -> bool:
    """Update a KB entry (company-scoped)."""
    from bson import ObjectId
    allowed = {"title", "canonical_answer", "tags", "verified"}
    safe = {k: v for k, v in data.items() if k in allowed}
    if not safe:
        return False
    db = get_db()
    result = await db.kb_entries.update_one(
        {"_id": ObjectId(entry_id), "company_id": company_id},
        {"$set": safe},
    )
    return result.modified_count > 0


async def delete_kb_entry(entry_id: str, company_id: str) -> bool:
    """Delete a KB entry (company-scoped)."""
    from bson import ObjectId
    db = get_db()
    result = await db.kb_entries.delete_one(
        {"_id": ObjectId(entry_id), "company_id": company_id}
    )
    return result.deleted_count > 0


async def set_kb_entry_doc_id(entry_id: str, endee_doc_id: str) -> None:
    """Record the Endee doc_id after successful vector ingestion."""
    from bson import ObjectId
    db = get_db()
    await db.kb_entries.update_one(
        {"_id": ObjectId(entry_id)},
        {"$set": {"endee_doc_id": endee_doc_id}},
    )


# =============================================================================
# Audit Log Operations
# =============================================================================

async def log_audit(audit: AuditLog) -> None:
    """Insert an audit log entry."""
    db = get_db()
    await db.audit_logs.insert_one(audit.model_dump())


async def get_audit_logs(
    company_id: str, limit: int = 50
) -> list[dict]:
    """Get recent audit logs for a company."""
    db = get_db()
    cursor = db.audit_logs.find(
        {"company_id": company_id}
    ).sort("created_at", -1).limit(limit)
    logs = await cursor.to_list(length=limit)
    for log in logs:
        log["_id"] = str(log["_id"])
    return logs


async def get_all_audit_logs(limit: int = 200) -> list[dict]:
    """Get recent audit logs across all companies (SuperAdmin use)."""
    db = get_db()
    cursor = db.audit_logs.find({}).sort("created_at", -1).limit(limit)
    logs = await cursor.to_list(length=limit)
    for log in logs:
        log["_id"] = str(log["_id"])
    return logs


# =============================================================================
# Dashboard Stats
# =============================================================================

async def get_dashboard_stats(company_id: str) -> dict:
    """
    Get aggregated stats for the company dashboard.

    Returns:
        Dict with total_chats, auto_resolved, escalated, clarified,
        pending_tickets, total_documents, kb_entries, active_conversations,
        auto_resolve_rate, escalation_rate.
    """
    db = get_db()

    # --- Legacy flow counts (chat_sessions + tickets) ---
    legacy_total = await db.chat_sessions.count_documents({"company_id": company_id})
    legacy_auto = await db.chat_sessions.count_documents(
        {"company_id": company_id, "action": "auto_reply"}
    )
    legacy_escalated = await db.chat_sessions.count_documents(
        {"company_id": company_id, "action": "escalate"}
    )
    legacy_clarified = await db.chat_sessions.count_documents(
        {"company_id": company_id, "action": "clarify"}
    )

    # --- New widget flow counts (AI messages in conversations) ---
    widget_auto = await db.messages.count_documents(
        {"company_id": company_id, "sender_type": "ai", "metadata.action": "auto_reply"}
    )
    widget_escalated = await db.messages.count_documents(
        {"company_id": company_id, "sender_type": "ai", "metadata.action": "escalate"}
    )
    widget_clarified = await db.messages.count_documents(
        {"company_id": company_id, "sender_type": "ai", "metadata.action": "clarify"}
    )

    total = legacy_total + widget_auto + widget_escalated + widget_clarified
    auto_resolved = legacy_auto + widget_auto
    escalated = legacy_escalated + widget_escalated
    clarified = legacy_clarified + widget_clarified

    pending_tickets = await db.tickets.count_documents(
        {"company_id": company_id, "status": "pending"}
    )
    total_docs = await db.documents.count_documents({"company_id": company_id})
    kb_entries = await db.kb_entries.count_documents({"company_id": company_id})
    active_convs = await db.conversations.count_documents(
        {"company_id": company_id, "status": "active"}
    )
    resolved_convs = await db.conversations.count_documents(
        {"company_id": company_id, "status": "resolved"}
    )

    return {
        "total_chats": total,
        "auto_resolved": auto_resolved,
        "escalated": escalated,
        "clarified": clarified,
        "pending_tickets": pending_tickets,
        "total_documents": total_docs,
        "kb_entries": kb_entries,
        "active_conversations": active_convs,
        "resolved_conversations": resolved_convs,
        "auto_resolve_rate": round(auto_resolved / total * 100, 1) if total > 0 else 0,
        "escalation_rate": round(escalated / total * 100, 1) if total > 0 else 0,
    }

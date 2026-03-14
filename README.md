# ResolveAI — AI Customer Support Platform

An AI-powered, multi-tenant customer support platform that automatically resolves repeatable customer issues using **RAG (Retrieval-Augmented Generation)** with [Endee](https://github.com/endee-io/endee) as the vector database. When the AI is uncertain, it intelligently escalates to human agents — and then **learns from every human resolution** to handle similar queries automatically in the future.

---

## Problem Statement

Customer support teams are overwhelmed by repetitive questions — password resets, billing inquiries, shipping status, return policies. These consume agent time while customers wait. Existing chatbots rely on rigid scripts and fail outside predefined flows.

**ResolveAI solves this by:**
1. Ingesting your existing knowledge base (FAQs, docs, Slack threads, emails, PDFs)
2. Using semantic vector search (Endee) to find relevant answers for each query
3. Generating natural-language responses with an LLM (Google Gemini) grounded in your data
4. Automatically escalating when confidence is low
5. Continuously learning: every human resolution is re-ingested into the KB, improving future accuracy

---

## Key Features

| Feature | Description |
|---------|-------------|
| **RAG Pipeline** | Semantic search via Endee + LLM generation grounded in KB documents |
| **Learning Loop** | Resolved tickets are automatically embedded back into Endee for future queries |
| **Multi-Tenant** | Company-scoped vector filters ensure complete data isolation |
| **Real-Time Chat** | WebSocket-based widget with typing indicators, presence, and instant staff replies |
| **RBAC** | Role hierarchy: SuperAdmin > Admin > Staff. JWT-based auth with per-role access control |
| **Configurable Thresholds** | Per-company auto-resolve and clarification confidence thresholds |
| **Multi-Source Ingestion** | Text, PDF (with OCR), Slack, Email, Confluence, Notion, Google Drive |
| **Embeddable Widget** | Single `<script>` tag — works on any website |
| **Decision Engine** | Weighted scoring: similarity + intent match + recency + source reliability |

---

## System Architecture

```
                    +-----------------------+
                    |   Embeddable Widget   |     <script src="widget.js" data-slug="acme">
                    |  (WebSocket client)   |
                    +----------+------------+
                               |
                    WebSocket /api/v1/ws/widget/{slug}
                               |
+------------------+           v              +-------------------+
|  Next.js 16      |    +-----------+         |  Staff Inbox      |
|  Dashboard       +--->|  FastAPI  |<--------+  (WebSocket)      |
|  /admin /staff   |    |  Backend  |         |  /staff page      |
+------------------+    +-----+-----+         +-------------------+
                              |
              +---------------+---------------+
              |               |               |
        +-----v-----+  +-----v-----+  +------v------+
        |   Endee   |  |  MongoDB  |  |    Redis    |
        | Vector DB |  | Primary DB|  |  Rate Limit |
        +-----------+  +-----------+  +-------------+
              ^
              |  384-dim embeddings (BAAI/bge-small-en-v1.5)
              |
        +-----+-----+
        | Embedding  |
        |   Model    |
        +-----+------+
              |
        +-----v------+
        |  Google     |
        |  Gemini LLM |
        +-------------+
```

### Request Flow

1. **Customer sends message** via WebSocket widget
2. **Intent classification** — LLM categorizes the query (billing, technical, account, etc.)
3. **Safety check** — "talk to human" requests escalate immediately
4. **Vector search** — Query embedded with BGE-small, searched in Endee with `company_id` filter
5. **Weighted scoring** — `similarity * 0.5 + intent_match * 0.2 + recency * 0.15 + reliability * 0.15`
6. **Decision matrix:**
   - Score >= 0.82 → **Auto-reply** (RAG-generated answer from top-3 documents)
   - Score 0.60-0.82 → **Clarify** (suggest related topics, ask follow-up)
   - Score < 0.60 → **Escalate** to human agent with full context
7. **Learning loop** — When staff resolves a conversation, the Q&A pair is re-embedded into Endee

---

## How Endee Is Used

[Endee](https://github.com/endee-io/endee) is the core vector database powering all semantic search and retrieval in ResolveAI.

### Vector Indexing

```python
# services/endee_client.py — Index creation
client.create_index(
    name="support_kb",
    dimension=384,           # BAAI/bge-small-en-v1.5 output
    space_type="cosine",
    precision=Precision.INT8D,
)
```

### Document Ingestion Pipeline

```python
# services/ingestion.py — Chunking → Embedding → Upsert
chunks = chunk_text(content, chunk_size=500, overlap=100)   # sentence-aware splitting
vectors = embedding_service.encode_documents_batch(chunks)   # local BGE-small

endee_items = [{
    "id": f"{company_id}_{doc_id}_{i}",
    "vector": vector,
    "meta": {
        "company_id": company_id,       # tenant isolation
        "doc_id": doc_id,
        "title": title,
        "source_type": source_type,     # text/pdf/slack/email/ticket
        "raw_text": chunk[:500],        # stored for RAG context
        "is_resolved": "true",          # learning loop flag
        "category": "billing",
        "created_at": "2024-01-15T...",
    },
}]

index.upsert(endee_items)
```

### Filtered Semantic Search

```python
# services/endee_client.py — Multi-tenant filtered query
results = index.query(
    vector=query_vector,
    top_k=10,
    filter=[{"meta.company_id": {"$eq": "company_abc"}}],   # Endee array filter on metadata field
)
```

Every search is scoped to the requesting company's `company_id`, ensuring **complete multi-tenant data isolation**.

### Learning Loop (Continuous Improvement)

```
Customer asks "Where is my refund?"
           │
           ▼
   No KB match → Escalate to human
           │
           ▼
   Staff resolves: "Refunds are processed within 3-5 business days"
           │
           ▼
   Q+A pair embedded → Endee vector with is_resolved="true"
           │
           ▼
   Next customer asks "Where is my refund?"
           │
           ▼
   Endee returns match (similarity=0.95, is_resolved=true)
           │
           ▼
   Weighted score ≥ 0.82 → Auto-reply with RAG answer ✓
```

Resolved tickets get a **scoring boost**: `intent_match=True` and `reliability=1.0`, ensuring they rank higher in search results and trigger auto-resolution.

### Weighted Scoring Formula

```python
score = (
    similarity * 0.50 +       # Endee cosine similarity
    intent_match * 0.20 +     # 1.0 if category matches OR is_resolved
    recency_factor * 0.15 +   # time-based decay
    source_reliability * 0.15  # 1.0 for resolved tickets, 0.8 for docs
)
```

---

## Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Vector DB** | [Endee](https://github.com/endee-io/endee) v0.1.6 | Semantic search, multi-tenant vector storage |
| **Backend** | Python 3.11, FastAPI, Uvicorn | REST API + WebSocket server |
| **Frontend** | Next.js 16, React 19, Tailwind CSS v4 | Dashboard, admin panel, staff inbox |
| **Primary DB** | MongoDB 7 (Motor async) | Users, companies, conversations, tickets |
| **Cache** | Redis 7 | Rate limiting (sliding window) |
| **LLM** | Google Gemini 2.0 Flash (via REST) | Intent classification, RAG generation |
| **Embeddings** | BAAI/bge-small-en-v1.5 (local) | 384-dim document/query embeddings |
| **Auth** | JWT + bcrypt | Role-based access control |
| **Widget** | Vanilla JavaScript (zero deps) | Embeddable chat w/ WebSocket |

---

## Installation & Setup

### Prerequisites

- Docker & Docker Compose
- A Google Gemini API key ([get one free](https://aistudio.google.com/apikey))

### Quick Start (Docker — Recommended)

```bash
# 1. Clone the repository
git clone https://github.com/DevCadbury/endee.git
cd endee

# 2. Configure environment
cp .env.example .env
# Edit .env — set GEMINI_API_KEY and JWT_SECRET

# 3. Start all services
docker compose up --build

# Services:
#   Frontend  → http://localhost:3000
#   Backend   → http://localhost:8000  (Swagger docs: /docs)
#   Endee     → http://localhost:8080
#   MongoDB   → localhost:27017
#   Redis     → localhost:6379
```

### Local Development (Without Docker)

```bash
# 1. Start infrastructure (Endee, MongoDB, Redis)
docker compose up endee mongodb redis -d

# 2. Backend
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# 3. Frontend (new terminal)
cd frontend
npm install
npm run dev
```

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `GEMINI_API_KEY` | Google Gemini API key | **Required** |
| `JWT_SECRET` | JWT signing secret | Change in production |
| `ENDEE_URL` | Endee server URL | `http://localhost:8080` |
| `MONGODB_URL` | MongoDB connection string | `mongodb://localhost:27017/support_ai` |
| `REDIS_URL` | Redis connection string | `redis://localhost:6379` |
| `AUTO_RESOLVE_THRESHOLD` | Min score for auto-reply | `0.82` |
| `CLARIFY_THRESHOLD` | Min score for clarification | `0.60` |
| `RATE_LIMIT_REQUESTS` | Max requests per window | `20` |
| `RATE_LIMIT_WINDOW_SECONDS` | Rate limit window | `60` |

---

## Usage Guide

### 1. Register a Company

Visit `http://localhost:3000/register` or:

```bash
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"company_name": "Acme Corp", "email": "admin@acme.com", "password": "secure123"}'
```

Response includes your company `slug` and `login_url`.

### 2. Log In

Visit `http://localhost:3000/login/{slug}` (e.g., `/login/acme-corp`).

### 3. Ingest Knowledge Base Data

**Dashboard → Knowledge Base tab:**
- Paste FAQ text, select source type, click "Ingest Document"

**Via API:**
```bash
curl -X POST http://localhost:8000/api/v1/kb/ingest \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Refund Policy FAQ",
    "content": "How do I get a refund? Refunds are processed within 3-5 business days after approval. Go to Account > Orders > Request Refund.",
    "source_type": "text",
    "category": "billing"
  }'
```

### 4. Generate an API Key

**Dashboard → Developer tab → "+ New Key"**

Or via API:
```bash
curl -X POST http://localhost:8000/api/v1/auth/api-key \
  -H "Authorization: Bearer $TOKEN"
```

API keys can be listed, generated, and revoked from the Developer tab.

### 5. Embed the Chat Widget

Add this to any HTML page:

```html
<script src="http://localhost:3000/widget.js"
  data-slug="acme-corp"
  data-api-url="http://localhost:8000">
</script>
```

Or open `test-widget.html` in your browser for a standalone demo page.

### 6. Test End-to-End

1. Send a message in the widget → AI replies from KB (auto-reply) or escalates
2. Open **Staff Inbox** (`http://localhost:3000/staff`) → See escalated conversations
3. Reply from Staff Inbox → Reply appears in widget in real-time via WebSocket
4. Click "Resolve" → Resolution is ingested back into Endee (learning loop)
5. Send the same question again → AI now auto-resolves it

---

## API Endpoints

### Authentication
| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/api/v1/auth/register` | None | Register company + admin |
| POST | `/api/v1/auth/login` | None | Login, returns JWT |
| GET | `/api/v1/auth/company/{slug}` | None | Public company info |
| POST | `/api/v1/auth/api-key` | Admin | Generate API key |
| GET | `/api/v1/auth/api-keys` | Admin | List API keys |
| DELETE | `/api/v1/auth/api-key/{id}` | Admin | Revoke API key |

### Chat Widget (Legacy)
| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/api/v1/chat/incoming` | API Key | Send message (HTTP) |

### Widget (WebSocket)
| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| WS | `/api/v1/ws/widget/{slug}` | None | Real-time chat |
| POST | `/api/v1/widget/{slug}/open` | None | Open/resume conversation |
| POST | `/api/v1/widget/{slug}/message` | Session ID | Send message |

### Knowledge Base
| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/api/v1/kb/ingest` | Admin | Ingest text document |
| POST | `/api/v1/kb/ingest/pdf` | Admin | Ingest PDF |
| POST | `/api/v1/kb/feedback` | Admin | Learning loop ingestion |
| GET | `/api/v1/kb/documents` | Staff | List documents |
| DELETE | `/api/v1/kb/documents/{id}` | Admin | Delete document |

### Conversations (Staff)
| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/api/v1/conversations` | Staff | List conversations |
| GET | `/api/v1/conversations/{id}` | Staff | Get with messages |
| POST | `/api/v1/conversations/{id}/message` | Staff | Reply to customer |
| POST | `/api/v1/conversations/{id}/resolve` | Staff | Resolve + ingest KB |
| POST | `/api/v1/conversations/{id}/assign` | Admin | Assign to staff |

### Dashboard
| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/api/v1/dashboard/stats` | Staff | Company statistics |
| GET | `/api/v1/dashboard/tickets` | Staff | List tickets |
| PATCH | `/api/v1/dashboard/tickets/{id}` | Admin | Resolve ticket |

### Admin
| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/api/v1/admin/staff` | Admin | Create staff user |
| GET | `/api/v1/admin/staff` | Admin | List staff |
| DELETE | `/api/v1/admin/staff/{id}` | Admin | Disable staff |
| GET | `/api/v1/admin/settings` | Admin | Company settings |
| PATCH | `/api/v1/admin/settings` | Admin | Update thresholds |
| GET | `/api/v1/admin/kb-entries` | Admin | List KB entries |

### SuperAdmin
| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/api/v1/superadmin/companies` | SuperAdmin | All companies |
| GET | `/api/v1/superadmin/users` | SuperAdmin | All users |
| GET | `/api/v1/superadmin/conversations` | SuperAdmin | All conversations |

---

## Testing

```bash
cd backend
python -m pytest -v
```

**126 tests across 8 test files:**

| Test File | Tests | Coverage |
|-----------|-------|----------|
| `test_auth_rbac.py` | JWT, RBAC, registration, login, company slug |
| `test_conversations.py` | Widget open/message, staff reply/resolve, cross-company isolation |
| `test_kb_entries.py` | Learning loop ingestion, KB CRUD, orchestrator auto-reply |
| `test_websocket.py` | ConnectionManager, widget WS, staff WS, REST→WS broadcast |
| `test_endee_isolation.py` | Multi-tenant vector isolation, filter format |
| `test_ingestion.py` | Chunking, cleaning, source extractors, is_resolved metadata |
| `test_orchestrator.py` | Decision matrix (auto_reply, clarify, escalate) |
| `test_rate_limit.py` | Redis sliding-window rate limiting |

---

## Project Structure

```
resolveai/
├── backend/
│   ├── main.py                    # FastAPI app + lifespan + CORS
│   ├── core/config.py            # Pydantic Settings
│   ├── api/
│   │   ├── auth.py               # JWT, RBAC, registration, API keys
│   │   ├── chat.py               # Legacy widget endpoint (HTTP)
│   │   ├── widget.py             # New widget endpoints (REST + WS)
│   │   ├── ws.py                 # WebSocket handlers
│   │   ├── conversations.py      # Staff conversation management
│   │   ├── kb.py                 # Knowledge base ingestion
│   │   ├── dashboard.py          # Stats, tickets, audit
│   │   ├── admin.py              # Staff mgmt, settings, KB entries
│   │   └── superadmin.py         # Global admin views
│   ├── services/
│   │   ├── orchestrator.py       # Decision engine (RAG pipeline)
│   │   ├── endee_client.py       # Endee SDK wrapper
│   │   ├── embedding.py          # BGE-small embeddings
│   │   ├── llm.py                # Gemini LLM client
│   │   ├── ingestion.py          # Multi-source chunking + upsert
│   │   ├── mongo.py              # MongoDB models + CRUD
│   │   ├── redis_cache.py        # Rate limiting
│   │   └── connection_manager.py # WebSocket room registry
│   └── tests/                    # 126 tests
├── frontend/
│   ├── src/app/
│   │   ├── register/page.tsx     # Company registration
│   │   ├── login/page.tsx        # Slug input → /login/[slug]
│   │   ├── login/[slug]/page.tsx # Company-branded login
│   │   ├── dashboard/page.tsx    # Admin dashboard (Overview, KB, Dev, Inbox, Audit)
│   │   ├── staff/page.tsx        # Staff inbox (real-time WS)
│   │   ├── admin/page.tsx        # Admin panel (Staff, Settings, KB, Test Widget)
│   │   └── superadmin/page.tsx   # SuperAdmin global views
│   └── public/widget.js          # Embeddable chat widget (vanilla JS)
├── docker-compose.yml            # All 5 services
├── test-widget.html              # Standalone widget demo page
├── .env.example                  # Environment template
└── README.md
```

---

## RBAC (Role-Based Access Control)

```
SuperAdmin          ← Global platform admin, sees all companies
    │
    ├── Admin       ← Company owner, manages staff + settings + KB
    │     │
    │     └── Staff ← Handles escalated conversations, resolves tickets
    │
    └── Customer    ← Unauthenticated widget user (identified by session ID)
```

| Role | Capabilities |
|------|-------------|
| **SuperAdmin** | View all companies, users, conversations, audit logs |
| **Admin** | Manage staff, company settings, KB entries, API keys, resolve tickets |
| **Staff** | View conversations, reply to customers, resolve/escalate |
| **Customer** | Chat via widget (no authentication required) |

---

## Decision Thresholds

| Weighted Score | Action | Description |
|---------------|--------|-------------|
| >= 0.82 | **Auto-Reply** | Generate RAG answer from top-3 KB matches |
| 0.60 - 0.82 | **Clarify** | Suggest related topics, ask follow-up question |
| < 0.60 | **Escalate** | Route to human agent with full conversation context |

Thresholds are **configurable per-company** via Admin → Settings.

---

## Supported Ingestion Sources

| Source | Format | Endpoint |
|--------|--------|----------|
| Text/FAQ | Plain text | `POST /api/v1/kb/ingest` |
| PDF | File upload (OCR fallback) | `POST /api/v1/kb/ingest/pdf` |
| Slack | JSON export | `POST /api/v1/kb/ingest` (source_type=slack) |
| Email | JSON (subject, body, from) | `POST /api/v1/kb/ingest` (source_type=email) |
| Confluence | HTML page export | `POST /api/v1/kb/ingest` (source_type=confluence) |
| Notion | Markdown export | `POST /api/v1/kb/ingest` (source_type=notion) |
| Resolved Tickets | Auto-ingested on resolve | Learning loop (automatic) |

---

## License

MIT

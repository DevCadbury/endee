# =============================================================================
# api/kb.py — Knowledge Base Management Routes
# =============================================================================
# Handles document ingestion (text, PDF, structured data),
# human-in-the-loop feedback (learning loop), and document listing/deletion.
# =============================================================================

import logging
import json
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from pydantic import BaseModel

from api.auth import get_current_user, require_admin, require_staff
from services.ingestion import (
    ingest_document,
    ingest_resolved_ticket,
    extract_from_pdf,
    extract_from_slack_export,
    extract_from_email,
    extract_from_confluence_notion,
)
from services.mongo import list_documents, delete_document

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/kb", tags=["Knowledge Base"])


# =============================================================================
# Request/Response Models
# =============================================================================

class TextIngestRequest(BaseModel):
    """Request to ingest raw text content."""
    title: str
    content: str
    source_type: str = "text"  # text | slack | email | confluence | notion | drive
    category: str = "general"
    tags: str = ""
    ticket_id: str = ""


class FeedbackRequest(BaseModel):
    """
    Human-in-the-loop feedback: ingest a resolved ticket into the KB.
    This is the continuous learning mechanism.
    """
    ticket_id: str
    question: str
    resolution: str
    category: str = "general"
    tags: str = ""


class IngestResponse(BaseModel):
    """Response after document ingestion."""
    doc_id: str | None
    mongo_id: str | None = None
    chunk_count: int
    status: str


# =============================================================================
# Routes
# =============================================================================

@router.post("/ingest", response_model=IngestResponse)
async def ingest_text(
    request: TextIngestRequest,
    user: dict = Depends(require_admin),
):
    """
    Ingest a text document into the knowledge base.
    
    The text is chunked, embedded, and stored in both Endee (for vector
    search) and MongoDB (for management). Supports structured data from
    various sources (Slack, email, Confluence, etc.).
    """
    company_id = user["company_id"]

    # Process based on source type
    content = request.content

    if request.source_type == "slack":
        # Parse Slack export JSON
        try:
            slack_data = json.loads(content)
            messages = extract_from_slack_export(slack_data)
            content = "\n\n".join(
                f"[{m['user']}]: {m['text']}" for m in messages
            )
        except json.JSONDecodeError:
            pass  # Use raw content if not valid JSON

    elif request.source_type == "email":
        try:
            email_data = json.loads(content)
            extracted = extract_from_email(email_data)
            content = extracted["text"]
        except json.JSONDecodeError:
            pass

    elif request.source_type in ("confluence", "notion"):
        try:
            page_data = json.loads(content)
            content = extract_from_confluence_notion(page_data)
        except json.JSONDecodeError:
            pass

    result = await ingest_document(
        company_id=company_id,
        title=request.title,
        content=content,
        source_type=request.source_type,
        metadata={
            "category": request.category,
            "tags": request.tags,
            "ticket_id": request.ticket_id,
        },
    )

    return IngestResponse(**result)


@router.post("/ingest/pdf", response_model=IngestResponse)
async def ingest_pdf(
    file: UploadFile = File(...),
    title: str = Form(""),
    category: str = Form("general"),
    tags: str = Form(""),
    user: dict = Depends(require_admin),
):
    """
    Ingest a PDF document into the knowledge base.
    
    Extracts text from the PDF (with OCR fallback for scanned documents),
    then processes through the standard ingestion pipeline.
    """
    company_id = user["company_id"]

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="File must be a PDF")

    # Read file content
    file_bytes = await file.read()
    content = extract_from_pdf(file_bytes)

    if not content.strip():
        raise HTTPException(
            status_code=400,
            detail="Could not extract text from PDF. The file may be empty or scanned without OCR.",
        )

    doc_title = title or file.filename or "Uploaded PDF"

    result = await ingest_document(
        company_id=company_id,
        title=doc_title,
        content=content,
        source_type="pdf",
        metadata={
            "category": category,
            "tags": tags,
            "filename": file.filename,
        },
    )

    return IngestResponse(**result)


@router.post("/feedback", response_model=IngestResponse)
async def submit_feedback(
    request: FeedbackRequest,
    user: dict = Depends(require_admin),
):
    """
    Submit a human-resolved ticket back into the knowledge base.
    
    This is the LEARNING LOOP: when a human agent resolves a ticket,
    the question + resolution pair is embedded and indexed so future
    similar questions can be auto-resolved.
    """
    company_id = user["company_id"]

    result = await ingest_resolved_ticket(
        company_id=company_id,
        ticket_id=request.ticket_id,
        question=request.question,
        resolution=request.resolution,
        category=request.category,
        tags=request.tags,
    )

    logger.info(
        f"Learning loop: ingested resolved ticket '{request.ticket_id}' "
        f"for company {company_id}"
    )

    return IngestResponse(**result)


@router.get("/documents")
async def get_documents(user: dict = Depends(require_staff)):
    """
    List all ingested documents for the authenticated company.
    Returns metadata only (not full content).
    """
    company_id = user["company_id"]
    docs = await list_documents(company_id)
    return {"documents": docs, "total": len(docs)}


@router.delete("/documents/{doc_id}")
async def remove_document(
    doc_id: str,
    user: dict = Depends(require_admin),
):
    """
    Delete a document from the knowledge base.
    Removes the MongoDB record. (Vector cleanup is eventual.)
    """
    company_id = user["company_id"]
    deleted = await delete_document(doc_id, company_id)

    if not deleted:
        raise HTTPException(status_code=404, detail="Document not found")

    return {"status": "deleted", "doc_id": doc_id}

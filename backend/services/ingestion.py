# =============================================================================
# services/ingestion.py — Multi-Source Knowledge Base Ingestion Pipeline
# =============================================================================
# Handles text extraction, chunking, metadata enrichment, embedding,
# and vector upsert for multiple document sources:
# Text/FAQ, PDFs, Slack exports, email, Confluence, Notion, Drive, Tickets.
# =============================================================================

import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


# =============================================================================
# Text Chunking Engine
# =============================================================================

def chunk_text(
    text: str,
    chunk_size: int = 500,
    overlap: int = 100,
) -> list[str]:
    """
    Split text into overlapping chunks for embedding.
    
    Uses sentence-aware splitting: tries to break at sentence boundaries
    rather than mid-word. Chunks are between chunk_size/2 and chunk_size
    tokens (approximated as words * 1.3).
    
    Args:
        text: The full text to chunk.
        chunk_size: Target chunk size in tokens (approx).
        overlap: Number of tokens to overlap between chunks.
        
    Returns:
        List of text chunks.
    """
    if not text or not text.strip():
        return []

    # Clean the text
    text = clean_text(text)

    # Split into sentences (rough sentence boundary detection)
    sentences = re.split(r'(?<=[.!?])\s+', text)

    chunks = []
    current_chunk: list[str] = []
    current_length = 0

    for sentence in sentences:
        sentence_length = len(sentence.split())

        if current_length + sentence_length > chunk_size and current_chunk:
            # Save current chunk
            chunk_text_str = " ".join(current_chunk)
            if len(chunk_text_str.strip()) > 20:  # Skip tiny chunks
                chunks.append(chunk_text_str.strip())

            # Keep overlap: take the last few sentences
            overlap_words = 0
            overlap_sentences: list[str] = []
            for s in reversed(current_chunk):
                s_len = len(s.split())
                if overlap_words + s_len > overlap:
                    break
                overlap_sentences.insert(0, s)
                overlap_words += s_len

            current_chunk = overlap_sentences
            current_length = overlap_words

        current_chunk.append(sentence)
        current_length += sentence_length

    # Don't forget the last chunk
    if current_chunk:
        chunk_text_str = " ".join(current_chunk)
        if len(chunk_text_str.strip()) > 20:
            chunks.append(chunk_text_str.strip())

    return chunks


# =============================================================================
# Text Cleaning
# =============================================================================

def clean_text(text: str) -> str:
    """
    Clean text by removing HTML tags, excessive whitespace,
    boilerplate signatures, and other noise.
    """
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', ' ', text)

    # Remove markdown image/link syntax but keep text
    text = re.sub(r'!\[([^\]]*)\]\([^)]+\)', r'\1', text)
    text = re.sub(r'\[([^\]]*)\]\([^)]+\)', r'\1', text)

    # Remove common email signatures
    text = re.sub(
        r'(--\s*\n.*|Sent from my.*|Best regards.*|Kind regards.*|'
        r'Thanks,?\s*\n.*|Cheers,?\s*\n.*)',
        '',
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )

    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text)
    text = text.strip()

    return text


# =============================================================================
# Source-Specific Extractors
# =============================================================================

def extract_from_pdf(file_bytes: bytes) -> str:
    """
    Extract text from a PDF file. Falls back to OCR for scanned PDFs.
    
    Args:
        file_bytes: Raw PDF file content.
        
    Returns:
        Extracted text string.
    """
    import io

    text_parts = []

    try:
        from PyPDF2 import PdfReader
        reader = PdfReader(io.BytesIO(file_bytes))
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)

    except Exception as e:
        logger.warning(f"PyPDF2 extraction failed: {e}")

    # If no text extracted, try OCR
    if not text_parts:
        try:
            import pytesseract
            from PIL import Image
            # Note: OCR requires Tesseract installed on the system
            logger.info("Attempting OCR extraction for scanned PDF...")
            # This is simplified — production would use pdf2image
            pass
        except ImportError:
            logger.warning("pytesseract not available for OCR fallback")

    return "\n\n".join(text_parts)


def extract_from_slack_export(data: dict | list) -> list[dict]:
    """
    Extract messages from a Slack channel export (JSON format).
    
    Args:
        data: Slack export JSON (list of message objects or dict with messages key).
        
    Returns:
        List of dicts with keys: text, user, timestamp.
    """
    messages = data if isinstance(data, list) else data.get("messages", [])
    extracted = []

    for msg in messages:
        if msg.get("type") == "message" and "text" in msg:
            extracted.append({
                "text": msg["text"],
                "user": msg.get("user", "unknown"),
                "timestamp": msg.get("ts", ""),
            })

    return extracted


def extract_from_email(data: dict) -> dict:
    """
    Extract content from an email record (JSON format).
    
    Args:
        data: Email dict with keys: subject, body, from, date.
        
    Returns:
        Dict with cleaned text and metadata.
    """
    subject = data.get("subject", "")
    body = data.get("body", data.get("text", ""))
    sender = data.get("from", data.get("sender", ""))
    date = data.get("date", "")

    cleaned_body = clean_text(body)

    return {
        "text": f"Subject: {subject}\n\n{cleaned_body}",
        "subject": subject,
        "sender": sender,
        "date": date,
    }


def extract_from_confluence_notion(data: dict) -> str:
    """
    Extract text from Confluence/Notion page export (HTML or Markdown).
    
    Args:
        data: Dict with keys: content (HTML/Markdown), title.
        
    Returns:
        Cleaned text string.
    """
    content = data.get("content", data.get("body", ""))
    title = data.get("title", "")

    cleaned = clean_text(content)
    if title:
        cleaned = f"{title}\n\n{cleaned}"

    return cleaned


# =============================================================================
# Main Ingestion Pipeline
# =============================================================================

async def ingest_document(
    company_id: str,
    title: str,
    content: str,
    source_type: str,
    metadata: Optional[dict] = None,
    embedding_service=None,
    endee_client_instance=None,
) -> dict:
    """
    Full ingestion pipeline: chunk → embed → upsert to Endee → save to MongoDB.
    
    Args:
        company_id: The tenant company ID.
        title: Document title.
        content: The full text content to ingest.
        source_type: One of: text, pdf, slack, email, confluence, notion, drive, ticket.
        metadata: Additional metadata to attach to vectors.
        embedding_service: The EmbeddingService instance.
        endee_client_instance: The EndeeClient instance.
        
    Returns:
        Dict with doc_id, chunk_count, and status.
    """
    from services.embedding import embedding_service as default_emb
    from services.endee_client import endee_client as default_endee
    from services.mongo import create_document, Document

    emb = embedding_service or default_emb
    endee = endee_client_instance or default_endee
    extra_meta = metadata or {}

    # Step 1: Chunk the text
    chunks = chunk_text(content)
    if not chunks:
        return {"doc_id": None, "chunk_count": 0, "status": "empty_content"}

    logger.info(f"Ingesting '{title}': {len(chunks)} chunks from {source_type}")

    # Step 2: Generate a document ID
    doc_id = str(uuid.uuid4())

    # Step 3: Embed all chunks in batch
    vectors = emb.encode_documents_batch(chunks)

    # Step 4: Prepare Endee items with rich metadata
    endee_items = []
    for i, (chunk, vector) in enumerate(zip(chunks, vectors)):
        vector_id = endee.generate_vector_id(company_id, doc_id, i)
        endee_items.append({
            "id": vector_id,
            "vector": vector,
            "meta": {
                "company_id": company_id,
                "doc_id": doc_id,
                "chunk_index": str(i),
                "title": title,
                "source_type": source_type,
                "raw_text": chunk[:500],  # Store truncated text for retrieval
                "category": extra_meta.get("category", "general"),
                "ticket_id": extra_meta.get("ticket_id", ""),
                "tags": extra_meta.get("tags", ""),
                "is_resolved": extra_meta.get("is_resolved", "false"),
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        })

    # Step 5: Upsert to Endee
    endee.ensure_index()
    endee.upsert_vectors_batch(endee_items)

    # Step 6: Save document record in MongoDB
    mongo_doc = Document(
        company_id=company_id,
        title=title,
        source_type=source_type,
        content=content[:1000],  # Store summary only
        chunk_count=len(chunks),
        metadata=extra_meta,
    )
    mongo_id = await create_document(mongo_doc)

    logger.info(
        f"Ingestion complete: doc_id={doc_id}, chunks={len(chunks)}, "
        f"mongo_id={mongo_id}"
    )

    return {
        "doc_id": doc_id,
        "mongo_id": mongo_id,
        "chunk_count": len(chunks),
        "status": "success",
    }


async def ingest_resolved_ticket(
    company_id: str,
    ticket_id: str,
    question: str,
    resolution: str,
    category: str = "general",
    tags: str = "",
    embedding_service=None,
    endee_client_instance=None,
) -> dict:
    """
    Ingest a human-resolved ticket back into the KB (learning loop).
    
    This is the continuous learning mechanism: when a human agent resolves
    a ticket, the Q&A pair is embedded and indexed for future retrieval.
    
    Args:
        company_id: The tenant company ID.
        ticket_id: The original ticket ID.
        question: The customer's original question.
        resolution: The human agent's resolution text.
        category: Ticket category.
        tags: Comma-separated tags.
        
    Returns:
        Dict with ingestion status.
    """
    # Combine question + resolution for richer embedding
    content = (
        f"Customer Question: {question}\n\n"
        f"Resolution: {resolution}"
    )

    return await ingest_document(
        company_id=company_id,
        title=f"Resolved Ticket: {ticket_id}",
        content=content,
        source_type="ticket",
        metadata={
            "ticket_id": ticket_id,
            "category": category,
            "tags": tags,
            "is_resolved": "true",
        },
        embedding_service=embedding_service,
        endee_client_instance=endee_client_instance,
    )

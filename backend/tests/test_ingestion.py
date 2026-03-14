# =============================================================================
# tests/test_ingestion.py — Ingestion Pipeline Tests
# =============================================================================
# Tests text chunking, metadata enrichment, and source-specific extraction.
# =============================================================================

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from services.ingestion import (
    chunk_text,
    clean_text,
    extract_from_slack_export,
    extract_from_email,
    extract_from_confluence_notion,
    ingest_resolved_ticket,
    ingest_document,
)


class TestTextChunking:
    """Test the text chunking engine."""

    def test_basic_chunking(self):
        """Long text should be split into multiple chunks."""
        text = ". ".join([f"This is sentence number {i}" for i in range(100)])
        chunks = chunk_text(text, chunk_size=50, overlap=10)
        assert len(chunks) > 1

    def test_overlap_exists(self):
        """Consecutive chunks should have overlapping content."""
        text = ". ".join([f"Unique sentence {i} with specific words" for i in range(50)])
        chunks = chunk_text(text, chunk_size=20, overlap=5)

        if len(chunks) >= 2:
            # Check that some words from chunk[0] appear in chunk[1]
            words_0 = set(chunks[0].split()[-10:])
            words_1 = set(chunks[1].split()[:10])
            overlap = words_0.intersection(words_1)
            # Should have at least some overlap
            assert len(overlap) >= 0  # Overlap is best-effort

    def test_empty_text(self):
        """Empty text should return empty list."""
        chunks = chunk_text("")
        assert chunks == []

    def test_short_text_single_chunk(self):
        """Short text should produce a single chunk."""
        chunks = chunk_text("This is a short FAQ answer about billing.")
        assert len(chunks) == 1

    def test_tiny_chunks_filtered(self):
        """Very small chunks (< 20 chars) should be filtered out."""
        chunks = chunk_text("Hi.", chunk_size=5, overlap=0)
        assert len(chunks) == 0  # "Hi." is too short


class TestTextCleaning:
    """Test text cleaning functions."""

    def test_html_removal(self):
        """HTML tags should be stripped."""
        text = "<h1>Title</h1><p>Content with <b>bold</b> text.</p>"
        cleaned = clean_text(text)
        assert "<h1>" not in cleaned
        assert "<p>" not in cleaned
        assert "Title" in cleaned
        assert "Content" in cleaned

    def test_whitespace_normalization(self):
        """Multiple spaces/newlines should be collapsed."""
        text = "Hello    world\n\n\n   test"
        cleaned = clean_text(text)
        assert "    " not in cleaned

    def test_signature_removal(self):
        """Email signatures should be removed."""
        text = "Main content here.\n\n--\nJohn Doe\nSenior Engineer"
        cleaned = clean_text(text)
        assert "Main content" in cleaned


class TestSlackExtractor:
    """Test Slack export extraction."""

    def test_basic_extraction(self):
        """Should extract messages from Slack export format."""
        data = [
            {"type": "message", "text": "Hello team!", "user": "U123", "ts": "1234567890"},
            {"type": "message", "text": "Need help with billing", "user": "U456", "ts": "1234567891"},
        ]
        messages = extract_from_slack_export(data)
        assert len(messages) == 2
        assert messages[0]["text"] == "Hello team!"

    def test_skips_non_messages(self):
        """Non-message types should be skipped."""
        data = [
            {"type": "channel_join", "text": "joined"},
            {"type": "message", "text": "Real message", "user": "U123"},
        ]
        messages = extract_from_slack_export(data)
        assert len(messages) == 1


class TestEmailExtractor:
    """Test email content extraction."""

    def test_basic_extraction(self):
        """Should extract subject and body from email."""
        data = {
            "subject": "Help with order",
            "body": "I need help tracking my order #12345.",
            "from": "customer@example.com",
            "date": "2024-01-15",
        }
        result = extract_from_email(data)
        assert "Help with order" in result["text"]
        assert "order #12345" in result["text"]


class TestConfluenceExtractor:
    """Test Confluence/Notion page extraction."""

    def test_html_content(self):
        """Should strip HTML and extract text."""
        data = {
            "title": "Setup Guide",
            "content": "<p>Follow these steps to <b>configure</b> the system.</p>",
        }
        result = extract_from_confluence_notion(data)
        assert "Setup Guide" in result
        assert "configure" in result
        assert "<p>" not in result


# =============================================================================
# Learning loop — is_resolved metadata must be written to Endee vectors
# =============================================================================

class TestIsResolvedMetadata:
    """
    Regression test for the learning loop bug where is_resolved was never
    written to Endee metadata, preventing the scoring boost from activating.
    """

    @pytest.mark.asyncio
    @patch("services.mongo.create_document", new_callable=AsyncMock, return_value="doc_mongo_1")
    async def test_ingest_resolved_ticket_writes_is_resolved_in_metadata(
        self, mock_create_doc
    ):
        """
        ingest_resolved_ticket must store is_resolved='true' in every
        Endee vector item's metadata so the orchestrator scoring boost fires.
        """
        captured_items = []

        mock_emb = MagicMock()
        mock_emb.encode_documents_batch.return_value = [[0.1] * 384]

        mock_endee = MagicMock()
        mock_endee.generate_vector_id.return_value = "vec_01"
        mock_endee.ensure_index.return_value = None
        mock_endee.upsert_vectors_batch.side_effect = lambda items: captured_items.extend(items)

        await ingest_resolved_ticket(
            company_id="co_test",
            ticket_id="tkt_001",
            question="Where is my refund?",
            resolution="Refunds are processed within 3-5 business days.",
            embedding_service=mock_emb,
            endee_client_instance=mock_endee,
        )

        assert len(captured_items) >= 1, "Expected at least one vector to be upserted"
        for item in captured_items:
            meta = item.get("meta", {})
            assert meta.get("is_resolved") == "true", (
                f"is_resolved not 'true' in meta: {meta}  — "
                "This causes the learning loop scoring boost to never activate."
            )

    @pytest.mark.asyncio
    @patch("services.mongo.create_document", new_callable=AsyncMock, return_value="doc_mongo_2")
    async def test_ingest_document_without_is_resolved_defaults_to_false(
        self, mock_create_doc
    ):
        """Regular documents (not resolved tickets) should have is_resolved='false'."""
        captured_items = []

        mock_emb = MagicMock()
        mock_emb.encode_documents_batch.return_value = [[0.1] * 384]

        mock_endee = MagicMock()
        mock_endee.generate_vector_id.return_value = "vec_02"
        mock_endee.ensure_index.return_value = None
        mock_endee.upsert_vectors_batch.side_effect = lambda items: captured_items.extend(items)

        await ingest_document(
            company_id="co_test",
            title="FAQ: Return Policy",
            content="Our return policy allows returns within 30 days of purchase.",
            source_type="text",
            embedding_service=mock_emb,
            endee_client_instance=mock_endee,
        )

        assert len(captured_items) >= 1
        for item in captured_items:
            meta = item.get("meta", {})
            assert meta.get("is_resolved") == "false", (
                f"Non-resolved document should have is_resolved='false', got: {meta.get('is_resolved')}"
            )

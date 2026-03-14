# =============================================================================
# tests/test_endee_isolation.py — Multi-Tenant Data Isolation Tests
# =============================================================================
# Verifies that Company A's data does not bleed into Company B's queries
# when using metadata filters in Endee.
# =============================================================================

import pytest
from unittest.mock import MagicMock, patch
from services.endee_client import EndeeClient


class TestEndeeIsolation:
    """Test multi-tenant data isolation in vector search."""

    def test_search_applies_company_filter(self):
        """
        Verify that search always includes company_id in the filter.
        """
        client = EndeeClient()

        # Mock the index
        mock_index = MagicMock()
        mock_index.query.return_value = []

        with patch.object(client.client, "get_index", return_value=mock_index):
            results = client.search(
                query_vector=[0.1] * 384,
                top_k=3,
                filters={"company_id": "company_A"},
            )

            # Verify query was called with the company filter
            mock_index.query.assert_called_once()
            call_kwargs = mock_index.query.call_args
            assert call_kwargs.kwargs.get("filter") == [{"company_id": {"$eq": "company_A"}}]

    def test_company_b_data_not_in_company_a_results(self):
        """
        Simulate: Company A's query should NOT return Company B's vectors.
        """
        client = EndeeClient()

        # Simulate Company A results only
        mock_result_a = MagicMock()
        mock_result_a.id = "company_a_doc_1"
        mock_result_a.similarity = 0.95
        mock_result_a.meta = {
            "company_id": "company_A",
            "raw_text": "Company A FAQ",
        }

        mock_index = MagicMock()
        mock_index.query.return_value = [mock_result_a]

        with patch.object(client.client, "get_index", return_value=mock_index):
            results = client.search(
                query_vector=[0.1] * 384,
                top_k=3,
                filters={"company_id": "company_A"},
            )

            # All results should belong to Company A
            for r in results:
                assert r["meta"]["company_id"] == "company_A"

            # No Company B data
            for r in results:
                assert r["meta"]["company_id"] != "company_B"

    def test_upsert_includes_company_id_in_metadata(self):
        """
        Verify that upsert always includes company_id in the vector metadata.
        """
        client = EndeeClient()

        mock_index = MagicMock()
        with patch.object(client.client, "get_index", return_value=mock_index):
            client.upsert_vector(
                doc_id="test_doc_1",
                vector=[0.1] * 384,
                metadata={
                    "company_id": "company_A",
                    "raw_text": "Test content",
                },
            )

            # Verify upsert was called with company_id in metadata
            call_args = mock_index.upsert.call_args[0][0]
            assert call_args[0]["meta"]["company_id"] == "company_A"

    def test_generate_vector_id_is_deterministic(self):
        """Vector IDs should be deterministic for the same inputs."""
        id1 = EndeeClient.generate_vector_id("company_A", "doc_1", 0)
        id2 = EndeeClient.generate_vector_id("company_A", "doc_1", 0)
        id3 = EndeeClient.generate_vector_id("company_B", "doc_1", 0)

        assert id1 == id2  # Same inputs → same ID
        assert id1 != id3  # Different company → different ID


class TestEndeeClientMethods:
    """Test Endee client methods."""

    def test_batch_upsert(self):
        """Batch upsert should call index.upsert with all items."""
        client = EndeeClient()

        mock_index = MagicMock()
        items = [
            {"id": "v1", "vector": [0.1] * 384, "meta": {"company_id": "co_A"}},
            {"id": "v2", "vector": [0.2] * 384, "meta": {"company_id": "co_A"}},
        ]

        with patch.object(client.client, "get_index", return_value=mock_index):
            client.upsert_vectors_batch(items)

            mock_index.upsert.assert_called_once_with(items)

    def test_search_returns_empty_on_error(self):
        """Search should return empty list on any error."""
        client = EndeeClient()

        mock_index = MagicMock()
        mock_index.query.side_effect = Exception("Connection refused")

        with patch.object(client.client, "get_index", return_value=mock_index):
            results = client.search(
                query_vector=[0.1] * 384,
                top_k=3,
                filters={"company_id": "company_A"},
            )

            assert results == []

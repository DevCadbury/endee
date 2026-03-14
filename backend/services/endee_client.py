# =============================================================================
# services/endee_client.py — Endee Vector Database Client
# =============================================================================
# Wrapper around the Endee Python SDK for vector operations.
# Handles index creation, vector upsert, and similarity search with
# metadata filtering for multi-tenant isolation.
# =============================================================================

import logging
import uuid
from endee import Endee, Precision
from core.config import get_settings

logger = logging.getLogger(__name__)


class EndeeClient:
    """
    Client for interacting with the Endee vector database.
    
    Uses the official `endee` Python SDK for all operations.
    Multi-tenancy is enforced by including company_id in all metadata
    and filtering by it on every query.
    
    Attributes:
        client: The Endee SDK client instance
        default_index: Name of the default vector index
    """

    def __init__(self):
        """Initialize the Endee client with settings from environment."""
        settings = get_settings()
        self.client = Endee()
        # Point to local Endee server
        base_url = settings.ENDEE_URL.rstrip("/") + "/api/v1"
        self.client.set_base_url(base_url)
        self.default_index = settings.ENDEE_INDEX_NAME
        self._index_cache: dict = {}

    def ensure_index(
        self,
        name: str | None = None,
        dimension: int = 384,
        space_type: str = "cosine",
    ) -> None:
        """
        Create the vector index if it doesn't already exist.
        
        Args:
            name: Index name (defaults to ENDEE_INDEX_NAME from config).
            dimension: Vector dimensionality (384 for bge-small).
            space_type: Distance metric ("cosine", "l2", "dot").
        """
        index_name = name or self.default_index

        if index_name in self._index_cache:
            return

        try:
            # Try to create the index
            self.client.create_index(
                name=index_name,
                dimension=dimension,
                space_type=space_type,
                precision=Precision.INT8D,
            )
            logger.info(
                f"Created Endee index '{index_name}' "
                f"(dim={dimension}, space={space_type})"
            )
        except Exception as e:
            # Index likely already exists — this is fine
            if "already exists" in str(e).lower() or "409" in str(e):
                logger.info(f"Endee index '{index_name}' already exists.")
            else:
                logger.warning(f"Endee index creation note: {e}")

        self._index_cache[index_name] = True

    def upsert_vector(
        self,
        doc_id: str,
        vector: list[float],
        metadata: dict,
        index_name: str | None = None,
    ) -> None:
        """
        Insert or update a single vector with metadata.
        
        Args:
            doc_id: Unique identifier for this vector (e.g., chunk ID).
            vector: The dense vector (list of floats).
            metadata: Payload metadata (MUST include company_id).
            index_name: Target index (defaults to config default).
        """
        idx_name = index_name or self.default_index
        try:
            index = self.client.get_index(name=idx_name)
            index.upsert([
                {
                    "id": doc_id,
                    "vector": vector,
                    "meta": metadata,
                }
            ])
            logger.debug(f"Upserted vector '{doc_id}' into '{idx_name}'")
        except Exception as e:
            logger.error(f"Failed to upsert vector '{doc_id}': {e}")
            raise

    def upsert_vectors_batch(
        self,
        items: list[dict],
        index_name: str | None = None,
    ) -> None:
        """
        Batch upsert multiple vectors.
        
        Args:
            items: List of dicts, each with keys: id, vector, meta.
            index_name: Target index (defaults to config default).
        """
        idx_name = index_name or self.default_index
        try:
            index = self.client.get_index(name=idx_name)
            index.upsert(items)
            logger.info(
                f"Batch upserted {len(items)} vectors into '{idx_name}'"
            )
        except Exception as e:
            logger.error(f"Batch upsert failed: {e}")
            raise

    @staticmethod
    def _build_filter(filters: dict | None) -> list | None:
        """
        Convert a plain dict filter to Endee's required array format.

        Endee requires:  [{"meta.field": {"$eq": value}}, ...]
        Callers pass:    {"field": value, ...}

        The "meta." prefix is required because metadata is stored under the
        "meta" key in the Endee index, so field paths must be qualified.
        """
        if not filters:
            return None
        return [{"meta." + k: {"$eq": v}} for k, v in filters.items()]

    def search(
        self,
        query_vector: list[float],
        top_k: int = 3,
        filters: dict | None = None,
        index_name: str | None = None,
    ) -> list[dict]:
        """
        Search for nearest neighbors with optional metadata filtering.

        Args:
            query_vector: The query embedding vector.
            top_k: Number of results to return.
            filters: Metadata filter dict (e.g., {"company_id": "abc123"}).
                     Converted internally to Endee array format.
            index_name: Index to search (defaults to config default).

        Returns:
            List of result dicts with keys: id, similarity, meta.
            Results are sorted by similarity (highest first).
        """
        idx_name = index_name or self.default_index
        try:
            index = self.client.get_index(name=idx_name)
            results = index.query(
                vector=query_vector,
                top_k=top_k,
                filter=self._build_filter(filters),
            )

            # Normalize results into a consistent format
            formatted = []
            for r in results:
                formatted.append({
                    "id": r.id if hasattr(r, "id") else r.get("id", ""),
                    "similarity": (
                        r.similarity
                        if hasattr(r, "similarity")
                        else r.get("similarity", 0.0)
                    ),
                    "meta": (
                        r.meta
                        if hasattr(r, "meta")
                        else r.get("meta", {})
                    ),
                })

            logger.info(
                f"Search '{idx_name}': {len(formatted)} results "
                f"(top_k={top_k}, filter_keys={list(filters.keys()) if filters else None})"
            )
            return formatted

        except Exception as e:
            logger.error(f"Endee search failed: {e}")
            return []

    def delete_vector(
        self,
        doc_id: str,
        index_name: str | None = None,
    ) -> None:
        """
        Delete a vector by its ID.
        
        Args:
            doc_id: The vector ID to delete.
            index_name: Index to delete from.
        """
        idx_name = index_name or self.default_index
        try:
            index = self.client.get_index(name=idx_name)
            index.delete([doc_id])
            logger.debug(f"Deleted vector '{doc_id}' from '{idx_name}'")
        except Exception as e:
            logger.error(f"Failed to delete vector '{doc_id}': {e}")
            raise

    @staticmethod
    def generate_vector_id(company_id: str, doc_id: str, chunk_idx: int) -> str:
        """
        Generate a deterministic vector ID for a document chunk.
        Format: {company_id}_{doc_id}_{chunk_idx}
        """
        return f"{company_id}_{doc_id}_{chunk_idx}"


# Module-level singleton instance
endee_client = EndeeClient()

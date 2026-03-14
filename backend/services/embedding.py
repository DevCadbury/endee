# =============================================================================
# services/embedding.py — Local Embedding Service (Singleton)
# =============================================================================
# Loads the BAAI/bge-small-en-v1.5 sentence-transformer model ONCE at startup.
# Produces 384-dimensional dense vectors for text inputs.
# Thread-safe singleton pattern prevents memory leaks from multiple loads.
# =============================================================================

import logging
from sentence_transformers import SentenceTransformer
from core.config import get_settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    """
    Singleton embedding service using BAAI/bge-small-en-v1.5.
    
    The model is loaded once and reused across all requests.
    BGE models recommend prefixing queries with "Represent this sentence: "
    for optimal retrieval performance.
    
    Attributes:
        model: The loaded SentenceTransformer model instance
        dimension: Output vector dimensionality (384 for bge-small)
    """

    _instance = None
    _model = None

    def __new__(cls):
        """Enforce singleton — only one model instance in memory."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def load_model(self) -> None:
        """
        Load the embedding model into memory.
        Called once during FastAPI lifespan startup.
        """
        if self._model is None:
            settings = get_settings()
            logger.info(f"Loading embedding model: {settings.EMBEDDING_MODEL}")
            self._model = SentenceTransformer(settings.EMBEDDING_MODEL)
            self.dimension = self._model.get_sentence_embedding_dimension()
            logger.info(
                f"Embedding model loaded. Dimension: {self.dimension}"
            )

    def encode(self, text: str) -> list[float]:
        """
        Encode a single text string into a dense vector.
        
        Args:
            text: The input text to embed.
            
        Returns:
            A list of floats representing the 384-dim embedding vector.
            
        Raises:
            RuntimeError: If the model hasn't been loaded yet.
        """
        if self._model is None:
            raise RuntimeError(
                "Embedding model not loaded. Call load_model() first."
            )
        # BGE models benefit from the instruction prefix for queries
        prefixed = f"Represent this sentence: {text}"
        vector = self._model.encode(prefixed, normalize_embeddings=True)
        return vector.tolist()

    def encode_batch(self, texts: list[str]) -> list[list[float]]:
        """
        Encode multiple texts into dense vectors in a single batch.
        More efficient than calling encode() in a loop.
        
        Args:
            texts: List of text strings to embed.
            
        Returns:
            List of embedding vectors (each a list of floats).
        """
        if self._model is None:
            raise RuntimeError(
                "Embedding model not loaded. Call load_model() first."
            )
        prefixed = [f"Represent this sentence: {t}" for t in texts]
        vectors = self._model.encode(prefixed, normalize_embeddings=True)
        return [v.tolist() for v in vectors]

    def encode_document(self, text: str) -> list[float]:
        """
        Encode a document/passage (no query prefix).
        Use this for indexing KB documents into the vector store.
        
        Args:
            text: The document text to embed.
            
        Returns:
            A list of floats representing the embedding vector.
        """
        if self._model is None:
            raise RuntimeError(
                "Embedding model not loaded. Call load_model() first."
            )
        vector = self._model.encode(text, normalize_embeddings=True)
        return vector.tolist()

    def encode_documents_batch(self, texts: list[str]) -> list[list[float]]:
        """
        Batch-encode documents/passages (no query prefix).
        
        Args:
            texts: List of document texts to embed.
            
        Returns:
            List of embedding vectors.
        """
        if self._model is None:
            raise RuntimeError(
                "Embedding model not loaded. Call load_model() first."
            )
        vectors = self._model.encode(texts, normalize_embeddings=True)
        return [v.tolist() for v in vectors]


# Module-level singleton instance
embedding_service = EmbeddingService()

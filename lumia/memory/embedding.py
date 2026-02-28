"""
Embedding Service for Memory System.

This module provides text embedding functionality using sentence-transformers.

Key features:
- sentence-transformers integration (all-MiniLM-L6-v2, 384-dim)
- Model loading and caching
- Batch embedding for performance
- Async embedding support
"""

import threading
from typing import Any

import numpy as np


class EmbeddingError(Exception):
    """Base exception for embedding-related errors."""

    pass


# Global model cache
_model_cache: dict[str, Any] = {}
_model_lock = threading.Lock()


def get_model(model_name: str = "all-MiniLM-L6-v2") -> Any:
    """
    Get or load sentence-transformers model.

    Args:
        model_name: Name of the model to load

    Returns:
        Loaded model

    Raises:
        EmbeddingError: If model loading fails
    """
    with _model_lock:
        if model_name in _model_cache:
            return _model_cache[model_name]

        try:
            from sentence_transformers import SentenceTransformer

            model = SentenceTransformer(model_name)
            _model_cache[model_name] = model
            return model

        except ImportError as e:
            raise EmbeddingError(
                "sentence-transformers not installed. "
                "Install with: pip install sentence-transformers"
            ) from e
        except Exception as e:
            raise EmbeddingError(f"Failed to load model {model_name}: {e}") from e


def embed_text(text: str, model_name: str = "all-MiniLM-L6-v2") -> list[float]:
    """
    Generate embedding for a single text.

    Args:
        text: Text to embed
        model_name: Name of the model to use

    Returns:
        Embedding vector as list of floats

    Raises:
        EmbeddingError: If embedding generation fails
    """
    if not text or not text.strip():
        raise EmbeddingError("Cannot embed empty text")

    try:
        model = get_model(model_name)
        embedding = model.encode(text, convert_to_numpy=True)
        return embedding.tolist()

    except Exception as e:
        raise EmbeddingError(f"Failed to generate embedding: {e}") from e


def embed_batch(
    texts: list[str], model_name: str = "all-MiniLM-L6-v2", batch_size: int = 32
) -> list[list[float]]:
    """
    Generate embeddings for multiple texts in batches.

    Args:
        texts: List of texts to embed
        model_name: Name of the model to use
        batch_size: Batch size for processing

    Returns:
        List of embedding vectors

    Raises:
        EmbeddingError: If embedding generation fails
    """
    if not texts:
        return []

    # Filter out empty texts
    valid_texts = [text for text in texts if text and text.strip()]
    if not valid_texts:
        raise EmbeddingError("Cannot embed batch with all empty texts")

    try:
        model = get_model(model_name)
        embeddings = model.encode(
            valid_texts, batch_size=batch_size, convert_to_numpy=True
        )
        return [emb.tolist() for emb in embeddings]

    except Exception as e:
        raise EmbeddingError(f"Failed to generate batch embeddings: {e}") from e


def get_embedding_dim(model_name: str = "all-MiniLM-L6-v2") -> int:
    """
    Get embedding dimension for a model.

    Args:
        model_name: Name of the model

    Returns:
        Embedding dimension

    Raises:
        EmbeddingError: If model loading fails
    """
    try:
        model = get_model(model_name)
        return model.get_sentence_embedding_dimension()

    except Exception as e:
        raise EmbeddingError(f"Failed to get embedding dimension: {e}") from e


def cosine_similarity(emb1: list[float], emb2: list[float]) -> float:
    """
    Calculate cosine similarity between two embeddings.

    Args:
        emb1: First embedding vector
        emb2: Second embedding vector

    Returns:
        Cosine similarity score (0-1)

    Raises:
        EmbeddingError: If calculation fails
    """
    try:
        vec1 = np.array(emb1)
        vec2 = np.array(emb2)

        dot_product = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return float(dot_product / (norm1 * norm2))

    except Exception as e:
        raise EmbeddingError(f"Failed to calculate cosine similarity: {e}") from e


"""
embeddings.py – Embedding Generator
─────────────────────────────────────
Wraps sentence-transformers to produce dense vector embeddings.
Model is loaded once and cached for the process lifetime.
"""

import logging
from typing import Optional
import numpy as np

from ..config import EMBED_MODEL

logger = logging.getLogger(__name__)

_embedder_cache: dict = {}


def get_embedder(model_name: Optional[str] = None):
    """Return a cached SentenceTransformer instance."""
    name = model_name or EMBED_MODEL
    if name not in _embedder_cache:
        try:
            from sentence_transformers import SentenceTransformer
            logger.info("Loading embedding model: %s", name)
            _embedder_cache[name] = SentenceTransformer(name)
        except ImportError:
            raise ImportError(
                "sentence-transformers is not installed. "
                "Run: pip install sentence-transformers"
            )
    return _embedder_cache[name]


def embed_texts(texts: list[str], model_name: Optional[str] = None) -> np.ndarray:
    """
    Embed a list of texts into a 2-D float32 numpy array.

    Args:
        texts:      List of strings to embed.
        model_name: Override the default embedding model.

    Returns:
        np.ndarray of shape (len(texts), embedding_dim)
    """
    embedder = get_embedder(model_name)
    return embedder.encode(texts, convert_to_numpy=True, show_progress_bar=False)


def embed_single(text: str, model_name: Optional[str] = None) -> np.ndarray:
    """Embed a single string and return a 1-D float32 vector."""
    return embed_texts([text], model_name)[0]

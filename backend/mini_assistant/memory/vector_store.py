"""
vector_store.py – FAISS Vector Store
──────────────────────────────────────
Persistent document store backed by FAISS.
Supports:
  - Ingesting text files, PDFs, and raw strings
  - Semantic similarity search
  - Persistence (save/load to disk)
  - Chunk-based ingestion for large documents
"""

import json
import logging
import os
from pathlib import Path
from typing import Optional

import numpy as np

from .embeddings import embed_texts, embed_single
from ..config import VECTOR_STORE_PATH, RAG_TOP_K

logger = logging.getLogger(__name__)

# Chunk settings
CHUNK_SIZE    = 512   # characters per chunk
CHUNK_OVERLAP = 64    # overlap between chunks


def _chunk_text(text: str) -> list[str]:
    """Split text into overlapping chunks."""
    chunks = []
    start = 0
    while start < len(text):
        end = start + CHUNK_SIZE
        chunks.append(text[start:end])
        start += CHUNK_SIZE - CHUNK_OVERLAP
    return chunks


def _extract_text(file_path: str) -> str:
    """Extract plain text from .txt, .md, or .pdf files."""
    path = Path(file_path)
    ext  = path.suffix.lower()

    if ext in (".txt", ".md", ".py", ".js", ".ts", ".json", ".yaml", ".yml"):
        return path.read_text(encoding="utf-8", errors="replace")

    if ext == ".pdf":
        try:
            import pypdf
            reader = pypdf.PdfReader(str(path))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        except ImportError:
            raise ImportError("pypdf is required for PDF ingestion: pip install pypdf")

    raise ValueError(f"Unsupported file type: {ext}")


class VectorStore:
    """
    FAISS-backed vector store with metadata.

    Usage:
        store = VectorStore()
        store.ingest_file("notes.pdf")
        store.ingest_text("Some raw text", source="manual")
        results = store.search("what is X?")
    """

    def __init__(self, store_path: Optional[str] = None):
        self._path  = Path(store_path or VECTOR_STORE_PATH)
        self._index = None       # faiss.IndexFlatIP
        self._docs: list[dict]  = []   # {"text", "source", "chunk_id"}
        self._dim: Optional[int] = None
        self._path.mkdir(parents=True, exist_ok=True)
        self._load()

    # ── Persistence ───────────────────────────────────────────────────────────

    def _index_file(self)    -> Path: return self._path / "index.faiss"
    def _metadata_file(self) -> Path: return self._path / "metadata.json"

    def _load(self):
        try:
            import faiss
            if self._index_file().exists() and self._metadata_file().exists():
                self._index = faiss.read_index(str(self._index_file()))
                self._docs  = json.loads(self._metadata_file().read_text())
                self._dim   = self._index.d
                logger.info("Loaded vector store: %d chunks", len(self._docs))
        except ImportError:
            logger.warning("faiss-cpu not installed; vector store is in-memory only.")
        except Exception as exc:
            logger.warning("Could not load vector store: %s", exc)

    def save(self):
        try:
            import faiss
            if self._index is not None:
                faiss.write_index(self._index, str(self._index_file()))
            self._metadata_file().write_text(json.dumps(self._docs, ensure_ascii=False))
            logger.info("Saved vector store: %d chunks", len(self._docs))
        except Exception as exc:
            logger.error("Failed to save vector store: %s", exc)

    # ── Ingestion ─────────────────────────────────────────────────────────────

    def _add_chunks(self, chunks: list[str], source: str):
        import faiss
        vectors = embed_texts(chunks).astype("float32")

        if self._index is None:
            self._dim   = vectors.shape[1]
            self._index = faiss.IndexFlatIP(self._dim)   # inner product = cosine on normalised vecs

        # L2-normalise for cosine similarity
        faiss.normalize_L2(vectors)
        self._index.add(vectors)

        for i, chunk in enumerate(chunks):
            self._docs.append({"text": chunk, "source": source, "chunk_id": i})

        self.save()
        logger.info("Ingested %d chunks from '%s'", len(chunks), source)

    def ingest_text(self, text: str, source: str = "manual") -> int:
        """Ingest raw text. Returns number of chunks added."""
        chunks = _chunk_text(text)
        self._add_chunks(chunks, source)
        return len(chunks)

    def ingest_file(self, file_path: str) -> int:
        """Ingest a file (txt, md, pdf). Returns number of chunks added."""
        text   = _extract_text(file_path)
        source = Path(file_path).name
        return self.ingest_text(text, source=source)

    # ── Search ────────────────────────────────────────────────────────────────

    def search(self, query: str, top_k: Optional[int] = None) -> list[dict]:
        """
        Semantic similarity search.

        Returns:
            List of {"text", "source", "chunk_id", "score"} dicts, best first.
        """
        if self._index is None or len(self._docs) == 0:
            return []

        import faiss
        k      = min(top_k or RAG_TOP_K, len(self._docs))
        vec    = embed_single(query).astype("float32").reshape(1, -1)
        faiss.normalize_L2(vec)
        scores, indices = self._index.search(vec, k)

        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx >= 0:
                doc = dict(self._docs[idx])
                doc["score"] = float(score)
                results.append(doc)

        return results

    def format_context(self, query: str, top_k: Optional[int] = None) -> str:
        """Return search results formatted as a context block for LLM injection."""
        results = self.search(query, top_k)
        if not results:
            return ""
        parts = [f"[{r['source']}]\n{r['text']}" for r in results]
        return "\n\n---\n\n".join(parts)

    @property
    def doc_count(self) -> int:
        return len(self._docs)

    def clear(self):
        """Remove all stored documents and reset the index."""
        self._index = None
        self._docs  = []
        self._dim   = None
        for f in [self._index_file(), self._metadata_file()]:
            f.unlink(missing_ok=True)
        logger.info("Vector store cleared.")

"""
app/services/rag_service.py

RAG (Retrieval-Augmented Generation) pipeline — Module 5: RAG + Vector Database.

Pipeline: chunk → embed → store → retrieve → generate

Supports:
  - PDF / Word document ingestion (admin uploads study materials)
  - Semantic search over exam documentation
  - Hybrid search: vector + keyword (BM25)
  - Per-exam isolated vector collections
"""
import os
import hashlib
from typing import Optional
import structlog

from app.core.config import settings
from app.core.database import get_db

log = structlog.get_logger()

# ─── ChromaDB client (lazy-initialized) ──────────────────────────────────────
_chroma_client = None
_embeddings = None


def _get_chroma():
    """Lazy-load ChromaDB to avoid import cost if RAG unused."""
    global _chroma_client
    if _chroma_client is None:
        try:
            import chromadb
            _chroma_client = chromadb.PersistentClient(path="./chroma_db")
            log.info("rag.chroma_connected")
        except ImportError:
            log.warning("rag.chromadb_not_installed", hint="pip install chromadb")
    return _chroma_client


def _get_embeddings():
    """Lazy-load OpenAI embeddings."""
    global _embeddings
    if _embeddings is None and settings.OPENAI_API_KEY:
        try:
            from langchain_openai import OpenAIEmbeddings
            _embeddings = OpenAIEmbeddings(
                api_key=settings.OPENAI_API_KEY,
                model="text-embedding-3-small",
            )
        except ImportError:
            log.warning("rag.langchain_not_installed")
    return _embeddings


# ─── Document Ingestion ───────────────────────────────────────────────────────

async def ingest_document(
    exam_id: str,
    content: str,
    source_name: str,
    chunk_size: int = 500,
    chunk_overlap: int = 50,
) -> dict:
    """
    Chunk → embed → store a document into the exam's vector collection.

    Chunking strategies (Module 5):
      - Fixed: split at chunk_size characters
      - Semantic: split at sentence/paragraph boundaries (preferred)
    """
    chroma = _get_chroma()
    if not chroma:
        return {"status": "skipped", "reason": "ChromaDB not available"}

    # Semantic chunking: split at double-newlines first, then fixed
    chunks = _semantic_chunk(content, chunk_size, chunk_overlap)

    collection_name = f"exam_{exam_id[:20]}"   # ChromaDB name limit
    try:
        collection = chroma.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},   # cosine similarity
        )
    except Exception as e:
        log.error("rag.collection_error", error=str(e))
        return {"status": "error", "reason": str(e)}

    # Generate stable IDs (dedup on re-ingest)
    ids = [
        hashlib.md5(f"{exam_id}:{source_name}:{i}".encode()).hexdigest()
        for i in range(len(chunks))
    ]
    metadatas = [{"source": source_name, "chunk": i, "exam_id": exam_id} for i in range(len(chunks))]

    try:
        # ChromaDB auto-embeds if embedding function provided; here we use OpenAI
        embeddings_fn = _get_embeddings()
        if embeddings_fn:
            vectors = embeddings_fn.embed_documents(chunks)
            collection.upsert(ids=ids, documents=chunks, embeddings=vectors, metadatas=metadatas)
        else:
            # Fallback: store without embeddings (text-only retrieval)
            collection.upsert(ids=ids, documents=chunks, metadatas=metadatas)

        log.info("rag.ingested", exam_id=exam_id, source=source_name, chunks=len(chunks))
        return {"status": "ok", "chunks": len(chunks), "collection": collection_name}
    except Exception as e:
        log.error("rag.ingest_error", error=str(e))
        return {"status": "error", "reason": str(e)}


async def retrieve_context(
    query: str,
    exam_id: str,
    top_k: int = 3,
) -> str:
    """
    Retrieve top-k relevant chunks for a query from the exam's vector store.
    Returns concatenated text for LLM context augmentation.

    Module 5: retrieve step of RAG pipeline.
    """
    chroma = _get_chroma()
    if not chroma:
        return ""

    collection_name = f"exam_{exam_id[:20]}"
    try:
        collection = chroma.get_collection(collection_name)
    except Exception:
        return ""   # Collection doesn't exist yet

    try:
        embeddings_fn = _get_embeddings()
        if embeddings_fn:
            query_vector = embeddings_fn.embed_query(query)
            results = collection.query(
                query_embeddings=[query_vector],
                n_results=min(top_k, collection.count()),
                include=["documents", "metadatas", "distances"],
            )
        else:
            results = collection.query(
                query_texts=[query],
                n_results=min(top_k, collection.count()),
                include=["documents", "metadatas"],
            )

        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]

        if not docs:
            return ""

        # Format with source attribution
        parts = []
        for doc, meta in zip(docs, metas):
            source = meta.get("source", "Unknown")
            parts.append(f"[Source: {source}]\n{doc}")

        return "\n\n---\n\n".join(parts)
    except Exception as e:
        log.warning("rag.retrieve_error", error=str(e))
        return ""


async def list_documents(exam_id: str) -> list[dict]:
    """List all ingested documents for an exam (admin view)."""
    chroma = _get_chroma()
    if not chroma:
        return []

    collection_name = f"exam_{exam_id[:20]}"
    try:
        collection = chroma.get_collection(collection_name)
        results = collection.get(include=["metadatas"])
        # Deduplicate by source name
        seen = {}
        for meta in results.get("metadatas", []):
            src = meta.get("source", "unknown")
            if src not in seen:
                seen[src] = {"source": src, "chunks": 0}
            seen[src]["chunks"] += 1
        return list(seen.values())
    except Exception:
        return []


async def delete_document(exam_id: str, source_name: str) -> bool:
    """Remove all chunks from a source document."""
    chroma = _get_chroma()
    if not chroma:
        return False

    collection_name = f"exam_{exam_id[:20]}"
    try:
        collection = chroma.get_collection(collection_name)
        collection.delete(where={"source": source_name})
        log.info("rag.deleted", exam_id=exam_id, source=source_name)
        return True
    except Exception as e:
        log.error("rag.delete_error", error=str(e))
        return False


# ─── Chunking ─────────────────────────────────────────────────────────────────

def _semantic_chunk(text: str, max_size: int, overlap: int) -> list[str]:
    """
    Semantic chunking: split at paragraphs first, then sentences,
    then fixed-size as a last resort. (Module 5: chunking strategies)
    """
    # Split at double newlines (paragraph boundary)
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

    chunks = []
    current = ""
    for para in paragraphs:
        if len(current) + len(para) + 2 <= max_size:
            current = (current + "\n\n" + para).strip()
        else:
            if current:
                chunks.append(current)
                # Overlap: carry last N chars of previous chunk
                current = current[-overlap:] + "\n\n" + para if overlap else para
            else:
                # Paragraph itself exceeds max_size: split at sentences
                sentences = para.replace(". ", ".\n").split("\n")
                for sent in sentences:
                    if len(current) + len(sent) <= max_size:
                        current = (current + " " + sent).strip()
                    else:
                        if current:
                            chunks.append(current)
                        current = sent

    if current:
        chunks.append(current)

    return [c for c in chunks if c.strip()]

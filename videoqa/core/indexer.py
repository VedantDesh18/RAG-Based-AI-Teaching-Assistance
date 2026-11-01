import requests
import os
import json
import logging
import videoqa.config as config_module

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configurable batch size for Ollama embedding calls.
#
# The default of 16 keeps peak memory usage bounded.  Increase via the
# EMBEDDING_BATCH_SIZE env-var if the Ollama server has ample RAM.
# ---------------------------------------------------------------------------
DEFAULT_EMBEDDING_BATCH_SIZE = 16


def create_embedding(text_list):
    r = requests.post(f"{config_module.config['ollama_url']}/api/embed", json={
        "model": config_module.config['model_names']['embedding'],
        "input": text_list
    })
    r.raise_for_status()
    embedding = r.json()["embeddings"]
    return embedding

from videoqa.vectorstore.chroma import upsert_vectors
from videoqa.db.sqlite import insert_chunks, set_chunk_count


def index_chunks(chunks: list[dict]) -> None:
    """Embed and persist *chunks* incrementally in bounded batches.

    Each batch is embedded via Ollama, then persisted to **both** ChromaDB and
    SQLite before the next batch is processed.  This means:

    * Peak memory never exceeds one batch of embeddings.
    * If the process crashes mid-way, all previously persisted batches are
      durable and the same function can be retried idempotently (both stores
      use upsert semantics keyed on ``chunk_id`` / ``(video_id, chunk_index)``).
    * A partial failure leaves the source file and already-committed data
      intact.
    """
    if not chunks:
        return

    batch_size = int(os.getenv("EMBEDDING_BATCH_SIZE", str(DEFAULT_EMBEDDING_BATCH_SIZE)))
    batch_size = max(1, min(batch_size, 256))  # clamp to sane range
    video_id = chunks[0]["video_id"]
    total = len(chunks)

    logger.info(
        "Indexing %d chunks for video_id=%s in batches of %d",
        total, video_id, batch_size,
    )

    indexed_count = 0

    for batch_start in range(0, total, batch_size):
        batch_chunks = chunks[batch_start : batch_start + batch_size]
        batch_texts = [c["text"] for c in batch_chunks]

        logger.info(
            "Embedding batch %d–%d / %d for video_id=%s",
            batch_start, batch_start + len(batch_chunks) - 1, total, video_id,
        )

        batch_embeddings = create_embedding(batch_texts)

        # Attach embeddings to chunk dicts (needed by insert_chunks)
        for i, chunk in enumerate(batch_chunks):
            chunk["embedding"] = batch_embeddings[i]

        # Prepare Chroma metadata
        ids = []
        metadatas = []
        for chunk in batch_chunks:
            meta = {
                "video_id": chunk["video_id"],
                "chunk_index": chunk["chunk_index"],
                "start_seconds": chunk["start_seconds"],
                "end_seconds": chunk["end_seconds"],
                "text": chunk["text"],
                "title": chunk.get("title", ""),
            }
            ids.append(chunk["chunk_id"])
            metadatas.append(meta)

        # Persist this batch (upsert is idempotent for retries)
        upsert_vectors(ids, [chunk["embedding"] for chunk in batch_chunks], metadatas)
        insert_chunks(batch_chunks)
        indexed_count += len(batch_chunks)

        # Free the embedding references to allow GC between batches
        for chunk in batch_chunks:
            chunk.pop("embedding", None)

        logger.info(
            "Persisted batch: %d / %d chunks indexed for video_id=%s",
            indexed_count, total, video_id,
        )

    set_chunk_count(video_id, indexed_count)
    logger.info("Indexing complete: %d chunks for video_id=%s", indexed_count, video_id)

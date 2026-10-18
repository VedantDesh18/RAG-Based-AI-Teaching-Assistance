import chromadb
from chromadb.config import Settings
import os
import videoqa.config as config_module

def get_chroma_client():
    chroma_path = config_module.config.get("paths", {}).get("chroma", "data/chroma")
    os.makedirs(chroma_path, exist_ok=True)
    return chromadb.PersistentClient(path=chroma_path, settings=Settings(allow_reset=True))

def get_collection():
    client = get_chroma_client()
    return client.get_or_create_collection(
        name="videoqa_chunks",
        metadata={"hnsw:space": "cosine"}
    )

def upsert_vectors(ids: list[str], embeddings: list[list[float]], metadatas: list[dict]):
    if not ids: return
    collection = get_collection()
    # Batch upsert if needed, chroma handles small batches fine.
    # Metadata has limits on some types, ensure simple types
    clean_metadatas = []
    for meta in metadatas:
        clean_meta = {}
        for k, v in meta.items():
            if v is not None and isinstance(v, (str, int, float, bool)):
                # Chroma limit string to a certain size, e.g., 500 chars for 'text' as per plan
                if k == "text" and isinstance(v, str):
                    clean_meta[k] = v[:500]
                else:
                    clean_meta[k] = v
        clean_metadatas.append(clean_meta)
    
    collection.upsert(
        ids=ids,
        embeddings=embeddings,
        metadatas=clean_metadatas
    )

def search_vectors(query_embedding: list[float], top_k: int = 5, video_id: str = None):
    collection = get_collection()
    where = {"video_id": video_id} if video_id else None
    
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        where=where,
        include=["metadatas", "distances"]
    )
    
    ret = []
    if results['ids'] and len(results['ids']) > 0:
        for i in range(len(results['ids'][0])):
            distance = results['distances'][0][i]
            # Convert cosine distance to similarity
            similarity = 1.0 - distance
            
            item = results['metadatas'][0][i].copy()
            item['chunk_id'] = results['ids'][0][i]
            item['similarity'] = similarity
            ret.append(item)
    return ret

def delete_video_chroma(video_id: str):
    collection = get_collection()
    collection.delete(where={"video_id": video_id})

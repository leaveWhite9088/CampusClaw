"""索引编排：上传/重建时 切分 → 写切片表+FTS → 嵌入 → 写向量库。

材料原文先入关系库（第 3 课事务），索引失败时原文保留，
受影响切片标记 failed，不写入不完整的向量数据。
"""

from . import db, embedding, vectorstore
from .chunking import chunk_text


def index_entry(entry_id, strategy="auto", **params):
    """对一条知识库条目重建索引。返回 (chunk_ids, old_vector_ids, embedded)。"""
    entry = None
    conn = db.get_conn()
    try:
        entry = conn.execute(
            "SELECT * FROM knowledge_entries WHERE id = ?", (entry_id,)
        ).fetchone()
    finally:
        conn.close()
    if entry is None:
        raise KeyError(f"knowledge_entry {entry_id} 不存在")

    chunks = chunk_text(entry["body_text"], strategy=strategy, **params)
    chunk_ids, old_chunk_ids = db.replace_chunks(entry_id, chunks, strategy)

    # 先删旧向量，避免遗留过期主键
    if old_chunk_ids and vectorstore.available():
        vectorstore.delete(old_chunk_ids)

    embedded = False
    if chunks and embedding.available():
        try:
            texts = [c["chunk_text"] for c in chunks]
            vectors = embedding.embed_texts(texts)
            vectorstore.ensure_collection(len(vectors[0]))
            vectorstore.upsert([
                {
                    "id": cid,
                    "vector": vec,
                    "payload": {
                        "class_id": entry["class_id"],
                        "material_id": entry["material_id"],
                        "knowledge_entry_id": entry_id,
                        "chunk_id": cid,
                        "chunk_index": chunks[i]["chunk_index"],
                    },
                }
                for i, (cid, vec) in enumerate(zip(chunk_ids, vectors))
            ])
            embedded = True
        except (embedding.EmbeddingError, vectorstore.VectorStoreError):
            embedded = False
    db.mark_chunks(entry_id, chunk_ids, "ready" if embedded else "failed")
    return chunk_ids, old_chunk_ids, embedded


def backfill_missing():
    """启动时：为无切片的既有/种子材料按 auto 补齐索引；失败不阻塞启动。"""
    count = 0
    for entry in db.entries_without_chunks():
        try:
            index_entry(entry["id"], strategy="auto")
            count += 1
        except Exception:
            continue
    return count

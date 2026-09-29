"""检索：keyword / vector / hybrid（RRF k=60）三条路径。

班级标识仅取自会话（由路由层传入），两条路径均带班级条件，
回表查询再次核对；摘录始终取自关系库 chunk_text。
"""

from . import db, embedding, vectorstore

VECTOR_THRESHOLD = 0.35
RRF_K = 60
DEFAULT_LIMIT = 20


class VectorPathUnavailable(RuntimeError):
    """向量库或嵌入服务不可用：vector/hybrid 返回 503，不编造分数。"""


def _fts_terms(raw):
    """按空白分词；trigram 仅支持 ≥3 字符的词，短词走 LIKE 兜底。"""
    terms = [t.strip() for t in raw.split() if t.strip()]
    long_terms = [t for t in terms if len(t) >= 3]
    short_terms = [t for t in terms if len(t) < 3]
    return long_terms, short_terms


def _excerpt(text, limit=120):
    text = text.strip()
    return text if len(text) <= limit else text[:limit] + "…"


def _hit(row, **extra):
    hit = {
        "material_id": row["material_id"],
        "material_title": row["material_title"],
        "chunk_id": row["chunk_id"],
        "chunk_index": row["chunk_index"],
        "start_offset": row["start_offset"],
        "end_offset": row["end_offset"],
        "excerpt": _excerpt(row["chunk_text"]),
    }
    hit.update(extra)
    return hit


def keyword_path(class_id, query, limit=DEFAULT_LIMIT):
    """仅查 SQLite 全文索引（短词 LIKE 兜底），不调用嵌入服务，不访问 Qdrant。"""
    long_terms, short_terms = _fts_terms(query)
    if not long_terms and not short_terms:
        return []
    merged = {}
    if long_terms:
        fts = " OR ".join(f'"{t.replace(chr(34), chr(34) * 2)}"' for t in long_terms)
        for r in db.keyword_search(class_id, fts, limit):
            merged[r["chunk_id"]] = _hit(r, score=round(-r["kw_score"], 4))
    for term in short_terms:
        for r in db.like_search(class_id, term, limit):
            if r["chunk_id"] not in merged:
                merged[r["chunk_id"]] = _hit(r, score=float(r["hits"]))
    return sorted(merged.values(), key=lambda h: -h["score"])[:limit]


def vector_path(class_id, query, limit=DEFAULT_LIMIT):
    """问句嵌入 → Qdrant 按班级过滤 → 阈值过滤 → 回表取正文并再核对班级。"""
    if not embedding.available() or not vectorstore.available():
        raise VectorPathUnavailable("嵌入服务或向量库不可用")
    try:
        vector = embedding.embed_texts([query])[0]
        vectorstore.ensure_collection(len(vector))
        found = vectorstore.search(vector, class_id, limit=limit)
    except (embedding.EmbeddingError, vectorstore.VectorStoreError) as e:
        raise VectorPathUnavailable(str(e)) from e

    kept = [f for f in found if f.get("score", 0) >= VECTOR_THRESHOLD]
    rows = db.fetch_chunks_by_ids(class_id, [f["id"] for f in kept])
    by_id = {r["chunk_id"]: r for r in rows}
    hits = []
    for f in kept:
        row = by_id.get(f["id"])
        if row is None:  # 回表未命中（含班级不符）：不得出现在响应中
            continue
        hits.append(_hit(row, score=round(f["score"], 4)))
    return hits


def search(class_id, query, mode="hybrid"):
    """三种模式入口。返回 {'mode', 'hits'}；向量路径不可用抛 VectorPathUnavailable。"""
    if mode == "keyword":
        return {"mode": mode, "hits": keyword_path(class_id, query)}
    if mode == "vector":
        return {"mode": mode, "hits": vector_path(class_id, query)}
    if mode != "hybrid":
        raise ValueError(f"未知检索模式: {mode}")

    kw_hits = keyword_path(class_id, query)
    vec_hits = vector_path(class_id, query)  # 不可用则整体 503（不降级编造分数）

    # RRF（k=60）：两路先各自过滤（各路径内已完成），再按名次融合；缺席一路不贡献分数
    fused = {}
    for source, hits in (("keyword", kw_hits), ("vector", vec_hits)):
        for rank, h in enumerate(hits, start=1):
            entry = fused.setdefault(h["chunk_id"], {**h, "rrf": 0.0, "sources": []})
            entry["rrf"] += 1.0 / (RRF_K + rank)
            entry["sources"].append(source)
    hits = sorted(fused.values(), key=lambda h: -h["rrf"])
    for h in hits:
        h["score"] = round(h.pop("rrf"), 6)
    return {"mode": mode, "hits": hits[:DEFAULT_LIMIT]}

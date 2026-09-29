"""检索与问答 API。班级标识仅取自会话；请求中自带的 class_id 一律丢弃。"""

from flask import Blueprint, jsonify, request, session

from . import chat, retrieval
from .auth import login_required
from .chunking import ChunkingError
from .db import get_entry_for_material, get_material
from .indexing import index_entry

bp = Blueprint("search", __name__)

NOT_FOUND_TEXT = "资料中未找到相关内容"


def _citation(hit):
    out = {
        "material_id": hit["material_id"],
        "material_title": hit["material_title"],
        "chunk_id": hit["chunk_id"],
        "chunk_index": hit["chunk_index"],
        "start_offset": hit["start_offset"],
        "end_offset": hit["end_offset"],
        "excerpt": hit["excerpt"],
    }
    if "score" in hit:
        out["score"] = hit["score"]
    if hit.get("sources"):
        out["sources"] = hit["sources"]
    return out


@bp.get("/api/search")
@login_required
def api_search():
    query = (request.args.get("q") or "").strip()
    if not query:
        return jsonify({"error": "empty_query", "message": "查询不能为空"}), 400
    mode = request.args.get("mode") or "hybrid"
    if mode not in ("keyword", "vector", "hybrid"):
        return jsonify({"error": "invalid_mode", "message": "mode 须为 keyword/vector/hybrid"}), 400

    # class_id 只取自会话；query/body 中携带的一律无效
    class_id = session["class_id"]
    try:
        result = retrieval.search(class_id, query, mode)
    except retrieval.VectorPathUnavailable as e:
        return jsonify({"error": "vector_unavailable", "message": str(e)}), 503
    return jsonify({"mode": result["mode"], "hits": [_citation(h) for h in result["hits"]]})


@bp.post("/api/ask")
@login_required
def api_ask():
    data = request.get_json(silent=True) or {}
    question = (data.get("question") or "").strip()
    if not question:
        return jsonify({"error": "empty_query", "message": "问题不能为空"}), 400

    class_id = session["class_id"]
    try:
        result = retrieval.search(class_id, question, "hybrid")
    except retrieval.VectorPathUnavailable:
        # 向量路径不可用时问答无法完成混合检索，按无命中语义返回固定文案
        return jsonify({"answer": NOT_FOUND_TEXT, "citations": []})

    hits = result["hits"][:4]
    if not hits:
        # 无命中切片：不调用生成模型，直接返回固定文案
        return jsonify({"answer": NOT_FOUND_TEXT, "citations": []})

    try:
        answer = chat.generate_answer(question, _full_chunks(hits), data.get("history"))
    except chat.ChatError as e:
        return jsonify({"error": "chat_unavailable", "message": str(e)}), 503
    return jsonify({
        "answer": answer,
        "citations": [_citation(h) for h in hits],
    })


def _full_chunks(hits):
    """对话模块输入需要切片正文：按 chunk_id 回表取（仅限本班 ready）。"""
    from .db import fetch_chunks_by_ids
    rows = fetch_chunks_by_ids(session["class_id"], [h["chunk_id"] for h in hits])
    by_id = {r["chunk_id"]: r for r in rows}
    return [
        {
            "material_title": h["material_title"],
            "chunk_index": h["chunk_index"],
            "chunk_text": by_id[h["chunk_id"]]["chunk_text"],
        }
        for h in hits if h["chunk_id"] in by_id
    ]


@bp.post("/api/materials/<int:material_id>/reindex")
@login_required
def api_reindex(material_id):
    if session.get("role") != "teacher":
        return jsonify({"error": "forbidden", "message": "仅教师可重建索引"}), 403
    row = get_material(material_id)
    if row is None:
        return jsonify({"error": "not_found"}), 404
    if row["class_id"] != session["class_id"]:
        return jsonify({"error": "forbidden"}), 403

    entry = get_entry_for_material(material_id)
    if entry is None:
        return jsonify({"error": "no_entry", "message": "该材料无知识库条目"}), 404

    data = request.get_json(silent=True) or request.form
    strategy = data.get("strategy") or "auto"
    params = {}
    if strategy == "custom":
        if data.get("max_len"):
            params["max_len"] = int(data["max_len"])
        if data.get("overlap_ratio") is not None and data.get("overlap_ratio") != "":
            params["overlap_ratio"] = float(data["overlap_ratio"])
        params["strip_links"] = bool(data.get("strip_links"))
        params["collapse_whitespace"] = bool(data.get("collapse_whitespace"))

    try:
        chunk_ids, _, embedded = index_entry(entry["id"], strategy=strategy, **params)
    except ChunkingError as e:
        return jsonify({"error": "invalid_strategy", "message": str(e)}), 400
    return jsonify({
        "material_id": material_id,
        "strategy": strategy,
        "chunks": len(chunk_ids),
        "embedded": embedded,
    })

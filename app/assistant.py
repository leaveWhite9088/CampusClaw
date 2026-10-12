"""解题助手：提示词 / 技能 / 会话 / SSE 流式回答（第 5 课）。

一次回答的输入 = 班级提示词 + 已启用技能指令 + 本班检索切片 + 本轮提问（+ 历史）。
"""

import json
import time

from flask import (
    Blueprint, Response, jsonify, redirect, render_template, request, url_for,
)

from . import chat, retrieval
from .auth import current_user, login_required
from .db import (
    add_message, create_conversation, create_skill, enabled_skills,
    get_conversation, get_prompt, get_skill, list_conversations, list_messages,
    list_skills, recent_messages, update_skill, upsert_prompt,
)
from .search import _citation, NOT_FOUND_TEXT

bp = Blueprint("assistant", __name__)

DELTA_CHUNK = 20  # SSE 每段约 20 字


# ---------- 提示词 ----------


@bp.get("/api/prompt")
@login_required
def get_class_prompt():
    return jsonify({"content": get_prompt(current_user()["class_id"])})


@bp.put("/api/prompt")
@login_required
def put_class_prompt():
    user = current_user()
    if user["role"] != "teacher":
        return jsonify({"error": "forbidden", "message": "仅教师可修改提示词"}), 403
    data = request.get_json(silent=True) or {}
    content = (data.get("content") or "").strip()
    if not content:
        return jsonify({"error": "empty_content", "message": "提示词不能为空"}), 400
    upsert_prompt(user["class_id"], content, user["user_id"])
    return jsonify({"ok": True, "content": content})


# ---------- 技能 ----------


def _skill_json(s):
    return {
        "id": s["id"], "name": s["name"], "description": s["description"],
        "instructions": s["instructions"], "enabled": bool(s["enabled"]),
        "updated_at": s["updated_at"],
    }


@bp.get("/api/skills")
@login_required
def api_list_skills():
    return jsonify({"skills": [_skill_json(s) for s in list_skills(current_user()["class_id"])]})


@bp.post("/api/skills")
@login_required
def api_create_skill():
    user = current_user()
    if user["role"] != "teacher":
        return jsonify({"error": "forbidden", "message": "仅教师可新建技能"}), 403
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    instructions = (data.get("instructions") or "").strip()
    if not name or not instructions:
        return jsonify({"error": "invalid", "message": "名称与指令不能为空"}), 400
    skill_id = create_skill(user["class_id"], name,
                            (data.get("description") or "").strip(), instructions)
    return jsonify({"id": skill_id}), 201


@bp.patch("/api/skills/<int:skill_id>")
@login_required
def api_update_skill(skill_id):
    user = current_user()
    if user["role"] != "teacher":
        return jsonify({"error": "forbidden", "message": "仅教师可修改技能"}), 403
    skill = get_skill(skill_id)
    if skill is None:
        return jsonify({"error": "not_found"}), 404
    if skill["class_id"] != user["class_id"]:
        return jsonify({"error": "forbidden"}), 403
    data = request.get_json(silent=True) or {}
    fields = {}
    for k in ("name", "description", "instructions"):
        if data.get(k) is not None:
            fields[k] = str(data[k]).strip()
    if data.get("enabled") is not None:
        fields["enabled"] = 1 if data["enabled"] else 0
    update_skill(skill_id, **fields)
    return jsonify({"ok": True})


# ---------- 会话 ----------


def _conv_json(c):
    return {"id": c["id"], "title": c["title"], "created_at": c["created_at"]}


def _owned_conversation(conv_id):
    """返回 (conversation, error_response)；越权 403、不存在 404。"""
    conv = get_conversation(conv_id)
    if conv is None:
        return None, (jsonify({"error": "not_found"}), 404)
    user = current_user()
    if conv["user_id"] != user["user_id"] or conv["class_id"] != user["class_id"]:
        return None, (jsonify({"error": "forbidden"}), 403)
    return conv, None


@bp.post("/api/conversations")
@login_required
def api_create_conversation():
    user = current_user()
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "新对话").strip()[:50]
    conv_id = create_conversation(user["class_id"], user["user_id"], title)
    return jsonify({"id": conv_id, "title": title}), 201


@bp.get("/api/conversations")
@login_required
def api_list_conversations():
    convs = list_conversations(current_user()["user_id"])
    return jsonify({"conversations": [_conv_json(c) for c in convs]})


@bp.get("/api/conversations/<int:conv_id>/messages")
@login_required
def api_list_conv_messages(conv_id):
    conv, err = _owned_conversation(conv_id)
    if err:
        return err
    out = []
    for m in list_messages(conv_id):
        item = {"id": m["id"], "role": m["role"], "content": m["content"],
                "created_at": m["created_at"]}
        if m["citations"]:
            item["citations"] = json.loads(m["citations"])
        out.append(item)
    return jsonify({"conversation": _conv_json(conv), "messages": out})


def _sse(event):
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


@bp.post("/api/conversations/<int:conv_id>/messages")
@login_required
def api_send_message(conv_id):
    conv, err = _owned_conversation(conv_id)
    if err:
        return err
    data = request.get_json(silent=True) or {}
    question = (data.get("content") or "").strip()
    if not question:
        return jsonify({"error": "empty_content", "message": "消息不能为空"}), 400

    user = current_user()
    class_id = user["class_id"]

    history = recent_messages(conv_id, limit=6)  # 本轮之前的历史
    add_message(conv_id, "user", question)
    if conv["title"] == "新对话":
        _retitle(conv_id, question)

    # 本班混合检索前 4 条；向量路径不可用时关键字兜底
    degraded = False
    try:
        result = retrieval.search(class_id, question, "hybrid")
        hits = result["hits"][:4]
    except retrieval.VectorPathUnavailable:
        degraded = True
        hits = retrieval.keyword_path(class_id, question)[:4]

    if not hits:
        # 无命中：不调用对话网关，流式返回固定文案
        add_message(conv_id, "assistant", NOT_FOUND_TEXT, [])
        def nohit():
            yield _sse({"type": "delta", "text": NOT_FOUND_TEXT})
            yield _sse({"type": "citations", "citations": []})
            yield _sse({"type": "done"})
        return Response(nohit(), mimetype="text/event-stream",
                        headers={"Cache-Control": "no-cache",
                                 "X-Accel-Buffering": "no"})

    # 组装对话输入：班级提示词 + 启用技能指令 + 编号资料（chat.generate_answer 内组装）
    class_prompt = get_prompt(class_id)
    skill_instructions = "\n\n".join(
        f"技能「{s['name']}」：{s['instructions']}" for s in enabled_skills(class_id)
    )
    full_chunks = _full_chunks(class_id, hits)
    try:
        answer = chat.generate_answer(
            question, full_chunks, history,
            class_prompt=class_prompt, skill_instructions=skill_instructions)
    except chat.ChatError as e:
        return jsonify({"error": "chat_unavailable", "message": str(e)}), 503

    citations = [_citation(h) for h in hits]
    add_message(conv_id, "assistant", answer, citations)

    def stream():
        for i in range(0, len(answer), DELTA_CHUNK):
            yield _sse({"type": "delta", "text": answer[i:i + DELTA_CHUNK]})
            time.sleep(0.03)
        if degraded:
            yield _sse({"type": "notice", "degraded": True})
        yield _sse({"type": "citations", "citations": citations})
        yield _sse({"type": "done"})
    return Response(stream(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache",
                             "X-Accel-Buffering": "no"})


def _retitle(conv_id, question):
    from .db import get_conn
    conn = get_conn()
    try:
        with conn:
            conn.execute("UPDATE conversations SET title = ? WHERE id = ?",
                         (question[:20], conv_id))
    finally:
        conn.close()


def _full_chunks(class_id, hits):
    from .db import fetch_chunks_by_ids
    rows = fetch_chunks_by_ids(class_id, [h["chunk_id"] for h in hits])
    by_id = {r["chunk_id"]: r for r in rows}
    return [
        {
            "material_title": h["material_title"],
            "chunk_index": h["chunk_index"],
            "chunk_text": by_id[h["chunk_id"]]["chunk_text"],
        }
        for h in hits if h["chunk_id"] in by_id
    ]


# ---------- 页面 ----------


@bp.get("/ask")
@login_required
def ask_page():
    return render_template("ask.html", user=current_user())


@bp.get("/settings")
@login_required
def settings_page():
    user = current_user()
    if user["role"] != "teacher":
        return redirect(url_for("materials.list_materials"))
    return render_template("settings.html", user=user)

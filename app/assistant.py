"""解题助手：提示词 / 模板 / 技能 / 会话 / SSE 流式回答 / 调用日志（第 5、6 课）。

一次回答的输入 = 应用绑定模板（渲染）+ 选中技能完整指令 + 本班检索切片
+ 工具返回数据块 + 本轮提问（+ 历史）。无应用会话沿用第 5 课：班级提示词 + 全部启用技能。
"""

import json
import time

from flask import (
    Blueprint, Response, jsonify, redirect, render_template, request, url_for,
)

from . import chat, mcp, retrieval
from .auth import current_user, login_required
from .db import (
    add_message, create_conversation, create_skill, create_template,
    delete_template, enabled_skills, get_app, get_conversation, get_llm_log,
    get_prompt, get_skill, get_template, kb_stats, list_conversations,
    list_llm_logs, list_messages, list_skills, list_templates,
    recent_messages, update_skill, update_template, upsert_prompt,
)
from .search import _citation, NOT_FOUND_TEXT
from .skillfile import (
    SkillFileError, parse_skill_text, select_skills, parse_tool_refs,
    validate_tool_refs,
)

bp = Blueprint("assistant", __name__)

DELTA_CHUNK = 20  # SSE 每段约 20 字


def _teacher_required():
    user = current_user()
    return user if user and user["role"] == "teacher" else None


# ---------- 班级提示词 ----------


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


# ---------- 提示词模板 ----------


def _template_json(t):
    return {"id": t["id"], "name": t["name"], "content": t["content"],
            "built_in": bool(t["built_in"]), "updated_at": t["updated_at"]}


@bp.get("/api/templates")
@login_required
def api_list_templates():
    return jsonify({"templates": [_template_json(t)
                                  for t in list_templates(current_user()["class_id"])]})


@bp.post("/api/templates")
@login_required
def api_create_template():
    user = _teacher_required()
    if user is None:
        return jsonify({"error": "forbidden", "message": "仅教师可维护模板"}), 403
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    content = (data.get("content") or "").strip()
    if not name or not content:
        return jsonify({"error": "invalid", "message": "名称与内容不能为空"}), 400
    tpl_id = create_template(user["class_id"], name[:64], content)
    return jsonify({"id": tpl_id}), 201


@bp.put("/api/templates/<int:tpl_id>")
@login_required
def api_update_template(tpl_id):
    user = _teacher_required()
    if user is None:
        return jsonify({"error": "forbidden", "message": "仅教师可维护模板"}), 403
    tpl = get_template(tpl_id)
    if tpl is None or tpl["class_id"] != user["class_id"]:
        return jsonify({"error": "not_found"}), 404
    data = request.get_json(silent=True) or {}
    fields = {}
    if data.get("name") is not None and data["name"].strip():
        fields["name"] = data["name"].strip()[:64]
    if data.get("content") is not None and data["content"].strip():
        fields["content"] = data["content"].strip()
    update_template(tpl_id, **fields)
    return jsonify({"ok": True})


@bp.delete("/api/templates/<int:tpl_id>")
@login_required
def api_delete_template(tpl_id):
    user = _teacher_required()
    if user is None:
        return jsonify({"error": "forbidden", "message": "仅教师可维护模板"}), 403
    tpl = get_template(tpl_id)
    if tpl is None or tpl["class_id"] != user["class_id"]:
        return jsonify({"error": "not_found"}), 404
    if tpl["built_in"]:
        return jsonify({"error": "builtin", "message": "内置模板不可删除"}), 400
    delete_template(tpl_id)
    return jsonify({"ok": True})


# ---------- 技能 ----------


def _skill_json(s):
    return {
        "id": s["id"], "name": s["name"], "description": s["description"],
        "instructions": s["instructions"], "enabled": bool(s["enabled"]),
        "applicable": s["applicable"] if "applicable" in s.keys() else "",
        "tools": s["tools"] if "tools" in s.keys() else "knowledge_search",
        "source": s["source"] if "source" in s.keys() else "manual",
        "updated_at": s["updated_at"],
    }


def _validate_tools_field(class_id, tools_text):
    """格式 + 可达性校验；返回 (refs, error_response)。"""
    try:
        refs = parse_tool_refs(tools_text)
    except SkillFileError as e:
        return None, (jsonify({"error": "invalid_tools", "message": str(e)}), 400)
    err = validate_tool_refs(class_id, refs)
    if err:
        return None, (jsonify({"error": "invalid_tools", "message": err}), 400)
    return refs, None


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
    tools_text = (data.get("tools") or "knowledge_search").strip()
    refs, err = _validate_tools_field(user["class_id"], tools_text)
    if err:
        return err
    skill_id = create_skill(user["class_id"], name[:64],
                            (data.get("description") or "").strip()[:200], instructions,
                            applicable=(data.get("applicable") or "").strip()[:200],
                            tools=",".join(refs), source="manual")
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
    for k in ("name", "description", "instructions", "applicable"):
        if data.get(k) is not None:
            fields[k] = str(data[k]).strip()
    if data.get("tools") is not None:
        refs, err = _validate_tools_field(user["class_id"], str(data["tools"]).strip())
        if err:
            return err
        fields["tools"] = ",".join(refs)
    if data.get("enabled") is not None:
        fields["enabled"] = 1 if data["enabled"] else 0
    update_skill(skill_id, **fields)
    return jsonify({"ok": True})


@bp.post("/api/skills/upload")
@login_required
def api_upload_skill():
    user = current_user()
    if user["role"] != "teacher":
        return jsonify({"error": "forbidden", "message": "仅教师可上传技能"}), 403
    file = request.files.get("file")
    if file is None or not file.filename:
        # 兼容直接以 JSON 提交技能内容
        data = request.get_json(silent=True) or {}
        filename = (data.get("filename") or "skill.md").strip()
        text = data.get("content") or ""
    else:
        filename = file.filename
        try:
            text = file.read().decode("utf-8")
        except UnicodeDecodeError:
            return jsonify({"error": "encoding", "message": "技能文件须为 UTF-8 文本"}), 400
    try:
        parsed = parse_skill_text(filename, text)
        err = validate_tool_refs(user["class_id"], parsed["tools"])
        if err:
            return jsonify({"error": "invalid_tools", "message": err}), 400
    except SkillFileError as e:
        return jsonify({"error": "invalid_skill_file", "message": str(e)}), 400
    skill_id = create_skill(user["class_id"], parsed["name"], parsed["description"],
                            parsed["instructions"], applicable=parsed["applicable"],
                            tools=",".join(parsed["tools"]), source="uploaded")
    if parsed["enabled"]:
        update_skill(skill_id, enabled=1)
    return jsonify({"id": skill_id, "skill": parsed}), 201


# ---------- 会话 ----------


def _conv_json(c):
    return {"id": c["id"], "title": c["title"], "created_at": c["created_at"],
            "app_id": c["app_id"] if "app_id" in c.keys() else None}


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


def _parse_id_list(raw):
    try:
        ids = json.loads(raw or "[]")
        return [int(i) for i in ids] if isinstance(ids, list) else []
    except (ValueError, TypeError):
        return []


def _chat_context(class_id, conv, question):
    """会话上下文：模板内容与名称、选中技能、材料范围、应用归属。

    应用会话取应用绑定（模板/技能/材料子集）；旧会话沿用第 5 课（班级提示词 + 全部启用技能）。
    """
    app = None
    if conv["app_id"] is not None and "app_id" in conv.keys():
        candidate = get_app(conv["app_id"])
        if candidate is not None and candidate["class_id"] == class_id and candidate["enabled"]:
            app = candidate
    if app is None:
        return {
            "template_content": get_prompt(class_id),
            "template_name": "班级提示词",
            "skills": enabled_skills(class_id),
            "material_ids": None,
            "app_id": None,
            "app": None,
        }
    template = get_template(app["template_id"]) if app["template_id"] else None
    bound = [get_skill(i) for i in _parse_id_list(app["skill_ids"])]
    skills = [s for s in bound
              if s is not None and s["class_id"] == class_id and s["enabled"]]
    material_ids = _parse_id_list(app["material_ids"]) or None
    return {
        "template_content": template["content"] if template else get_prompt(class_id),
        "template_name": template["name"] if template else "班级提示词",
        "skills": skills,
        "material_ids": material_ids,
        "app_id": app["id"],
        "app": app,
    }


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

    ctx = _chat_context(class_id, conv, question)
    skills = select_skills(ctx["skills"], question)

    # 本班（或应用绑定材料范围）混合检索前 4 条；向量路径不可用时关键字兜底
    degraded = False
    try:
        result = retrieval.search(class_id, question, "hybrid")
        hits = result["hits"]
    except retrieval.VectorPathUnavailable:
        degraded = True
        hits = retrieval.keyword_path(class_id, question)
    if ctx["material_ids"]:
        allowed = set(ctx["material_ids"])
        hits = [h for h in hits if h["material_id"] in allowed]
    hits = hits[:4]

    if not hits:
        # 无命中：不调用工具与生成网关，流式返回固定文案
        add_message(conv_id, "assistant", NOT_FOUND_TEXT, [])

        def nohit():
            yield _sse({"type": "meta", "app_id": ctx["app_id"],
                        "skills": [s["name"] for s in skills]})
            yield _sse({"type": "delta", "text": NOT_FOUND_TEXT})
            yield _sse({"type": "citations", "citations": []})
            yield _sse({"type": "done"})
        return Response(nohit(), mimetype="text/event-stream",
                        headers={"Cache-Control": "no-cache",
                                 "X-Accel-Buffering": "no"})

    # 命中技能的白名单工具调用（确定性：代码决定，不由模型决定）
    tool_meta, tool_blocks = mcp.run_skill_tools(
        class_id, user["user_id"], conv_id, skills, question)

    full_chunks = _full_chunks(class_id, hits, ctx["material_ids"])
    kb = kb_stats(class_id, ctx["material_ids"])
    log_context = {
        "class_id": class_id,
        "user_id": user["user_id"],
        "conversation_id": conv_id,
        "app_id": ctx["app_id"],
        "source": "conversation",
        "template_name": ctx["template_name"],
        "skill_names": [s["name"] for s in skills],
        "tool_calls": tool_meta or None,
        "kb_total_chunks": kb["total_chunks"],
        "kb_total_chars": kb["total_chars"],
        "kb_passed_chunks": len(full_chunks),
        "kb_passed_chars": sum(len(c["chunk_text"]) for c in full_chunks),
    }
    try:
        answer = chat.generate_answer(
            question, full_chunks, history,
            template_content=ctx["template_content"], skills=skills,
            log_context=log_context, extra_user_blocks=tool_blocks)
    except chat.ChatError as e:
        return jsonify({"error": "chat_unavailable", "message": str(e)}), 503

    citations = [_citation(h) for h in hits]
    add_message(conv_id, "assistant", answer, citations)

    meta_event = {"type": "meta", "app_id": ctx["app_id"],
                  "template": ctx["template_name"],
                  "skills": [s["name"] for s in skills],
                  "citations": citations}
    if tool_meta:
        meta_event["tool_calls"] = tool_meta

    def stream():
        yield _sse(meta_event)
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


def _full_chunks(class_id, hits, material_ids=None):
    from .db import fetch_chunks_by_ids
    rows = fetch_chunks_by_ids(class_id, [h["chunk_id"] for h in hits])
    by_id = {r["chunk_id"]: r for r in rows}
    allowed = set(material_ids) if material_ids else None
    return [
        {
            "material_title": h["material_title"],
            "chunk_index": h["chunk_index"],
            "chunk_text": by_id[h["chunk_id"]]["chunk_text"],
        }
        for h in hits
        if h["chunk_id"] in by_id and (allowed is None or h["material_id"] in allowed)
    ]


# ---------- LLM 调用日志（教师可查，本班隔离） ----------


@bp.get("/api/llm-logs")
@login_required
def api_list_llm_logs():
    user = current_user()
    if user["role"] != "teacher":
        return jsonify({"error": "forbidden", "message": "仅教师可查看调用日志"}), 403
    limit = min(int(request.args.get("limit") or 50), 200)
    rows = list_llm_logs(user["class_id"], limit)
    return jsonify({"logs": [dict(r) for r in rows]})


@bp.get("/api/llm-logs/<int:log_id>")
@login_required
def api_get_llm_log(log_id):
    user = current_user()
    if user["role"] != "teacher":
        return jsonify({"error": "forbidden", "message": "仅教师可查看调用日志"}), 403
    row = get_llm_log(log_id, user["class_id"])
    if row is None:
        return jsonify({"error": "not_found"}), 404
    out = dict(row)
    if out.get("tool_calls"):
        out["tool_calls"] = json.loads(out["tool_calls"])
    return jsonify({"log": out})


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

"""AI 应用：内置多个应用，绑定提示词模板、技能与材料子集（第 6 课平台化）。

班级是数据边界：应用/模板/技能/材料的绑定校验均在服务端完成。
"""

import json

from flask import Blueprint, jsonify, redirect, render_template, request, url_for

from .auth import current_user, login_required
from .db import (
    create_app_row, create_conversation, delete_app_row, get_app, get_material,
    get_skill, get_template, list_apps, list_materials, update_app_row,
)

bp = Blueprint("apps", __name__)


def _parse_id_list(raw):
    try:
        ids = json.loads(raw or "[]")
        return [int(i) for i in ids] if isinstance(ids, list) else []
    except (ValueError, TypeError):
        return []


def _app_json(a):
    template = get_template(a["template_id"]) if a["template_id"] else None
    skills = [s for s in (get_skill(i) for i in _parse_id_list(a["skill_ids"]))
              if s is not None]
    material_ids = _parse_id_list(a["material_ids"])
    return {
        "id": a["id"], "name": a["name"], "description": a["description"],
        "template_id": a["template_id"],
        "template_name": template["name"] if template else "班级提示词",
        "skill_ids": _parse_id_list(a["skill_ids"]),
        "skill_names": [s["name"] for s in skills],
        "material_ids": material_ids,
        "material_scope": "指定材料 %d 份" % len(material_ids) if material_ids else "本班全部材料",
        "built_in": bool(a["built_in"]),
        "enabled": bool(a["enabled"]),
    }


def _validate_bindings(class_id, data):
    """校验模板/技能/材料绑定均属于本班；返回错误信息或 None。"""
    template_id = data.get("template_id")
    if template_id:
        tpl = get_template(int(template_id))
        if tpl is None or tpl["class_id"] != class_id:
            return "提示词模板不存在或不属于本班"
    for sid in data.get("skill_ids") or []:
        skill = get_skill(int(sid))
        if skill is None or skill["class_id"] != class_id:
            return "技能不存在或不属于本班"
    for mid in data.get("material_ids") or []:
        material = get_material(int(mid))
        if material is None or material["class_id"] != class_id:
            return "材料不存在或不属于本班"
    return None


@bp.get("/api/apps")
@login_required
def api_list_apps():
    user = current_user()
    apps = [_app_json(a) for a in list_apps(user["class_id"])]
    return jsonify({"apps": apps})


@bp.post("/api/apps")
@login_required
def api_create_app():
    user = current_user()
    if user["role"] != "teacher":
        return jsonify({"error": "forbidden", "message": "仅教师可维护应用"}), 403
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "invalid", "message": "应用名称不能为空"}), 400
    err = _validate_bindings(user["class_id"], data)
    if err:
        return jsonify({"error": "invalid_binding", "message": err}), 400
    app_id = create_app_row(
        user["class_id"], name[:64], (data.get("description") or "").strip()[:200],
        int(data["template_id"]) if data.get("template_id") else None,
        [int(i) for i in (data.get("skill_ids") or [])],
        [int(i) for i in (data.get("material_ids") or [])],
        built_in=0, enabled=1 if data.get("enabled", True) else 0,
    )
    return jsonify({"id": app_id}), 201


@bp.put("/api/apps/<int:app_id>")
@login_required
def api_update_app(app_id):
    user = current_user()
    if user["role"] != "teacher":
        return jsonify({"error": "forbidden", "message": "仅教师可维护应用"}), 403
    app = get_app(app_id)
    if app is None or app["class_id"] != user["class_id"]:
        return jsonify({"error": "not_found"}), 404
    data = request.get_json(silent=True) or {}
    err = _validate_bindings(user["class_id"], data)
    if err:
        return jsonify({"error": "invalid_binding", "message": err}), 400
    fields = {}
    if data.get("name") is not None and data["name"].strip():
        fields["name"] = data["name"].strip()[:64]
    if data.get("description") is not None:
        fields["description"] = data["description"].strip()[:200]
    if "template_id" in data:
        fields["template_id"] = int(data["template_id"]) if data["template_id"] else None
    if "skill_ids" in data:
        fields["skill_ids"] = [int(i) for i in (data["skill_ids"] or [])]
    if "material_ids" in data:
        fields["material_ids"] = [int(i) for i in (data["material_ids"] or [])]
    if "enabled" in data:
        fields["enabled"] = 1 if data["enabled"] else 0
    update_app_row(app_id, **fields)
    return jsonify({"ok": True})


@bp.delete("/api/apps/<int:app_id>")
@login_required
def api_delete_app(app_id):
    user = current_user()
    if user["role"] != "teacher":
        return jsonify({"error": "forbidden", "message": "仅教师可维护应用"}), 403
    app = get_app(app_id)
    if app is None or app["class_id"] != user["class_id"]:
        return jsonify({"error": "not_found"}), 404
    if app["built_in"]:
        return jsonify({"error": "builtin", "message": "内置应用不可删除"}), 400
    delete_app_row(app_id)
    return jsonify({"ok": True})


@bp.post("/api/apps/<int:app_id>/conversations")
@login_required
def api_create_app_conversation(app_id):
    user = current_user()
    app = get_app(app_id)
    if app is None or app["class_id"] != user["class_id"]:
        return jsonify({"error": "not_found"}), 404
    if not app["enabled"]:
        return jsonify({"error": "disabled", "message": "该应用已停用"}), 400
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "新对话").strip()[:50]
    conv_id = create_conversation(user["class_id"], user["user_id"], title, app_id=app_id)
    return jsonify({"id": conv_id, "title": title, "app_id": app_id}), 201


# ---------- 页面 ----------


@bp.get("/apps")
@login_required
def apps_page():
    return render_template("apps.html", user=current_user())


@bp.get("/apps/<int:app_id>")
@login_required
def app_chat_page(app_id):
    user = current_user()
    app = get_app(app_id)
    if app is None or app["class_id"] != user["class_id"]:
        return redirect(url_for("apps.apps_page"))
    return render_template("app_chat.html", user=user, app=_app_json(app))

import os
import uuid

from flask import (
    Blueprint, abort, current_app, redirect, render_template, request, session, url_for,
)

from .auth import login_required
from .db import (
    get_material,
    insert_material_with_knowledge,
    list_materials as query_materials,
)
from .knowledge import parse_file

bp = Blueprint("materials", __name__)

ALLOWED_EXTENSIONS = {".txt", ".md"}


@bp.get("/materials")
@login_required
def list_materials():
    rows = query_materials(session["class_id"])
    return render_template(
        "materials.html",
        materials=rows,
        username=session.get("username"),
        role=session.get("role"),
        class_id=session.get("class_id"),
    )


@bp.get("/materials/<int:material_id>")
@login_required
def material_detail(material_id):
    row = get_material(material_id)
    if row is None:
        abort(404)
    if row["class_id"] != session["class_id"]:
        # 跨班访问：403，响应不含他班标题/正文/路径
        abort(403)
    return render_template("material_detail.html", material=row)


@bp.post("/materials/upload")
@login_required
def upload():
    if session.get("role") != "teacher":
        abort(403)

    file = request.files.get("file")
    if file is None or not file.filename:
        return "未选择文件", 400

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return "仅支持 .txt / .md 文件", 400

    class_id = session["class_id"]  # class_id 只取自 session
    safe_name = os.path.basename(file.filename).replace("..", "_")
    rel_dir = str(class_id)
    abs_dir = os.path.join(current_app.config["UPLOAD_DIR"], rel_dir)
    os.makedirs(abs_dir, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex}_{safe_name}"
    abs_path = os.path.join(abs_dir, stored_name)
    file.save(abs_path)

    body_text = parse_file(abs_path)
    if body_text is None:
        os.remove(abs_path)  # 解析失败：清理文件，不写 DB 行
        return "文件解析失败", 400

    title = request.form.get("title") or os.path.splitext(safe_name)[0]
    insert_material_with_knowledge(
        class_id=class_id,
        title=title,
        filename=safe_name,
        file_path=os.path.join(rel_dir, stored_name),
        uploaded_by=session["user_id"],
        body_text=body_text,
    )
    return redirect(url_for("materials.list_materials"))

import os

from flask import Flask


def create_app():
    app = Flask(__name__)

    secret = os.environ.get("SECRET_KEY")
    if not secret:
        # 文档明确禁止的不安全默认值：仅限本地开发，Compose/生产必须通过环境变量注入
        secret = "dev-insecure-secret-do-not-use-in-prod"
    app.config["SECRET_KEY"] = secret
    app.config["DATABASE"] = os.environ.get(
        "DATABASE", os.path.join(app.root_path, "..", "data", "app.db")
    )
    app.config["UPLOAD_DIR"] = os.environ.get(
        "UPLOAD_DIR", os.path.join(app.root_path, "..", "uploads")
    )
    app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # 5 MB

    os.makedirs(os.path.dirname(os.path.abspath(app.config["DATABASE"])), exist_ok=True)
    os.makedirs(app.config["UPLOAD_DIR"], exist_ok=True)

    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

    from . import apps, assistant, auth, materials, mcp_api, search

    app.register_blueprint(auth.bp)
    app.register_blueprint(materials.bp)
    app.register_blueprint(search.bp)
    app.register_blueprint(assistant.bp)
    app.register_blueprint(apps.bp)
    app.register_blueprint(mcp_api.bp)

    # 第 4 课：启动迁移（既有库补切片表）+ 为无切片材料按 auto 补齐索引
    from .db import (
        ensure_assistant_schema, ensure_platform_schema, ensure_retrieval_schema,
        seed_assistant_defaults, seed_platform_defaults,
    )
    from .indexing import backfill_missing

    ensure_retrieval_schema(app.config["DATABASE"])
    ensure_assistant_schema(app.config["DATABASE"])
    ensure_platform_schema(app.config["DATABASE"])
    seed_assistant_defaults(app.config["DATABASE"])
    seed_platform_defaults(app.config["DATABASE"])
    with app.app_context():
        try:
            backfill_missing()
        except Exception:
            pass  # 嵌入/向量库不可用不阻塞启动

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/openapi.json")
    def openapi_spec():
        from flask import send_from_directory

        return send_from_directory(
            app.static_folder, "openapi.json", mimetype="application/json"
        )

    @app.get("/swagger")
    def swagger():
        from flask import render_template

        return render_template("swagger.html")

    @app.get("/")
    def index():
        from flask import redirect, session, url_for

        if "user_id" in session:
            return redirect(url_for("materials.list_materials"))
        return redirect(url_for("auth.login"))

    return app

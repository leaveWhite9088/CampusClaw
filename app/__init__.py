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

    from . import auth, materials

    app.register_blueprint(auth.bp)
    app.register_blueprint(materials.bp)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/")
    def index():
        from flask import redirect, session, url_for

        if "user_id" in session:
            return redirect(url_for("materials.list_materials"))
        return redirect(url_for("auth.login"))

    return app

import functools

from flask import (
    Blueprint, jsonify, redirect, render_template, request, session, url_for,
)
from werkzeug.security import check_password_hash

from .db import find_user_by_username

bp = Blueprint("auth", __name__)


def login_required(view):
    """页面请求 302 到登录页；API 请求返回 401 JSON。"""

    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            if request.path.startswith("/api/"):
                return jsonify({"error": "unauthorized"}), 401
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)

    return wrapped


@bp.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        user = find_user_by_username(username)
        if user is None or not check_password_hash(user["password_hash"], password):
            error = "用户名或密码错误"
        else:
            session.clear()
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["role"] = user["role"]
            session["class_id"] = user["class_id"]
            return redirect(url_for("materials.list_materials"))
    return render_template("login.html", error=error)


@bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))

import functools

from flask import (
    Blueprint, current_app, g, jsonify, redirect, render_template, request,
    session, url_for,
)
from werkzeug.security import check_password_hash

from .db import find_user_by_username
from .token_auth import TokenError, issue_token, verify_token

bp = Blueprint("auth", __name__)


def current_user():
    """当前请求的已验证身份（Bearer 声明或会话字段），未认证返回 None。"""
    if "auth_claims" in g:
        return g.auth_claims
    if "user_id" in session:
        return {
            "user_id": session["user_id"],
            "username": session.get("username"),
            "role": session.get("role"),
            "class_id": session.get("class_id"),
        }
    return None


def _bearer_claims():
    """解析 Authorization: Bearer 令牌；有效返回声明 dict，无头返回 None，无效抛 TokenError。"""
    header = request.headers.get("Authorization", "")
    if not header:
        return None
    if not header.startswith("Bearer "):
        raise TokenError("Authorization 头格式错误")
    payload = verify_token(header[len("Bearer "):], current_app.config["SECRET_KEY"])
    return {
        "user_id": payload["sub"],
        "username": payload.get("username"),
        "role": payload.get("role"),
        "class_id": payload.get("class_id"),
    }


def login_required(view):
    """Bearer 与 Cookie 会话双凭证（Bearer 优先）；页面 302 登录页，API 401。"""

    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        try:
            claims = _bearer_claims()
        except TokenError:
            return jsonify({"error": "invalid_token"}), 401
        if claims is not None:
            g.auth_claims = claims
            return view(*args, **kwargs)
        if "user_id" not in session:
            if request.path.startswith("/api/"):
                return jsonify({"error": "unauthorized"}), 401
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)

    return wrapped


def _establish_session(user):
    session.clear()
    session["user_id"] = user["id"]
    session["username"] = user["username"]
    session["role"] = user["role"]
    session["class_id"] = user["class_id"]


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
            _establish_session(user)
            return redirect(url_for("materials.list_materials"))
    return render_template("login.html", error=error)


@bp.post("/api/login")
def api_login():
    """JSON 登录：成功返回角色与班级；失败 401。对应规约「用户登录」Scenario。"""
    data = request.get_json(silent=True) or request.form
    username = data.get("username", "")
    password = data.get("password", "")
    user = find_user_by_username(username)
    if user is None or not check_password_hash(user["password_hash"], password):
        return jsonify({"error": "invalid_credentials"}), 401
    _establish_session(user)
    return jsonify({
        "username": user["username"],
        "role": user["role"],
        "class_id": user["class_id"],
        "access_token": issue_token(user, current_app.config["SECRET_KEY"]),
        "token_type": "bearer",
    })


@bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))

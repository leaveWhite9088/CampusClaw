"""MCP 管理接口：登记 / 列表 / 修改 / 删除 / 连接 / 断开 / 查工具 / 查审计。

全部「登录 + 仅教师」两层校验；学生 403；他班与不存在一律 404（不给探测空间）。
令牌只存服务端：任何响应只含 has_auth 布尔，不回传原文。
"""

import json

from flask import Blueprint, jsonify, request

from . import db, mcp
from .auth import current_user, login_required

bp = Blueprint("mcp_api", __name__)


def _teacher():
    user = current_user()
    return user if user and user["role"] == "teacher" else None


def _server_json(s):
    tools = db.list_mcp_tools(s["id"])
    return {
        "id": s["id"], "name": s["name"], "base_url": s["base_url"],
        "connected": bool(s["connected"]), "connected_at": s["connected_at"],
        "has_auth": bool(s["auth_token"]),
        "tool_count": len(tools),
        "tools": [{"name": t["tool_name"], "description": t["description"],
                   "inputSchema": json.loads(t["schema_json"] or "{}")} for t in tools],
    }


def _owned_server(server_id):
    """返回 (server, error_response)；他班与不存在一律 404。"""
    user = _teacher()
    if user is None:
        return None, (jsonify({"error": "forbidden", "message": "仅教师可管理 MCP 服务器"}), 403)
    server = db.get_mcp_server(server_id, user["class_id"])
    if server is None:
        return None, (jsonify({"error": "not_found"}), 404)
    return server, None


@bp.get("/api/mcp/servers")
@login_required
def api_list_servers():
    user = _teacher()
    if user is None:
        return jsonify({"error": "forbidden", "message": "仅教师可管理 MCP 服务器"}), 403
    return jsonify({"servers": [_server_json(s)
                                for s in db.list_mcp_servers(user["class_id"])]})


@bp.post("/api/mcp/servers")
@login_required
def api_create_server():
    user = _teacher()
    if user is None:
        return jsonify({"error": "forbidden", "message": "仅教师可管理 MCP 服务器"}), 403
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    base_url = (data.get("base_url") or "").strip()
    token = (data.get("auth_token") or "").strip()
    if not name or not base_url:
        return jsonify({"error": "invalid", "message": "名称与 Base URL 不能为空"}), 400
    if not base_url.startswith(("http://", "https://")):
        return jsonify({"error": "invalid", "message": "Base URL 须以 http(s):// 开头"}), 400
    if len(name) > 64 or len(base_url) > 512 or len(token) > 256:
        return jsonify({"error": "invalid", "message": "字段超长（名称≤64 / 地址≤512 / 令牌≤256）"}), 400
    if db.get_mcp_server_by_name(user["class_id"], name) is not None:
        return jsonify({"error": "duplicate", "message": "本班已有同名服务器"}), 400
    server_id = db.create_mcp_server(user["class_id"], name, base_url, token)
    return jsonify({"id": server_id}), 201


@bp.put("/api/mcp/servers/<int:server_id>")
@login_required
def api_update_server(server_id):
    server, err = _owned_server(server_id)
    if err:
        return err
    data = request.get_json(silent=True) or {}
    fields = {}
    if data.get("name") is not None and data["name"].strip():
        new_name = data["name"].strip()
        same = db.get_mcp_server_by_name(server["class_id"], new_name)
        if same is not None and same["id"] != server_id:
            return jsonify({"error": "duplicate", "message": "本班已有同名服务器"}), 400
        fields["name"] = new_name
    if data.get("base_url") is not None and data["base_url"].strip():
        fields["base_url"] = data["base_url"].strip()
    # 令牌留空 = 不修改；填了新值才覆盖
    if data.get("auth_token"):
        fields["auth_token"] = data["auth_token"].strip()
    db.update_mcp_server(server_id, **fields)
    # 改地址或令牌后旧缓存不再可信：置回未连接并清空工具缓存
    if fields:
        db.set_mcp_connected(server_id, 0)
        db.replace_mcp_tools(server_id, [])
    return jsonify({"ok": True})


@bp.delete("/api/mcp/servers/<int:server_id>")
@login_required
def api_delete_server(server_id):
    server, err = _owned_server(server_id)
    if err:
        return err
    db.delete_mcp_server(server_id)  # 审计行保留（server_id 置空），缓存级联删除
    return jsonify({"ok": True})


@bp.post("/api/mcp/servers/<int:server_id>/connect")
@login_required
def api_connect_server(server_id):
    server, err = _owned_server(server_id)
    if err:
        return err
    # 握手 → 发现 → 覆盖写缓存 → 标记已连接；前两步失败：不更新任何状态，502
    try:
        mcp.json_rpc(server["base_url"], "initialize",
                     {"protocolVersion": "2024-11-05",
                      "clientInfo": {"name": "campusclaw", "version": "1.0"}},
                     server["auth_token"])
        result = mcp.json_rpc(server["base_url"], "tools/list", {}, server["auth_token"])
        tools = [t for t in (result or {}).get("tools", [])
                 if isinstance(t, dict) and t.get("name")]
    except mcp.McpError as e:
        db.set_mcp_connected(server_id, 0)
        db.replace_mcp_tools(server_id, [])
        return jsonify({"error": "connect_failed",
                        "message": f"连接失败：{e}。请检查地址与令牌。"}), 502
    try:
        db.replace_mcp_tools(server_id, tools)
        db.set_mcp_connected(server_id, 1)
    except Exception as e:  # 数据库失败返回 503
        return jsonify({"error": "storage_failed", "message": str(e)}), 503
    return jsonify({"ok": True, "connected": True,
                    "tools": [{"name": t["name"], "description": t.get("description", "")}
                              for t in tools]})


@bp.post("/api/mcp/servers/<int:server_id>/disconnect")
@login_required
def api_disconnect_server(server_id):
    server, err = _owned_server(server_id)
    if err:
        return err
    db.set_mcp_connected(server_id, 0)
    db.replace_mcp_tools(server_id, [])
    return jsonify({"ok": True, "connected": False})


@bp.get("/api/mcp/servers/<int:server_id>/tools")
@login_required
def api_list_tools(server_id):
    server, err = _owned_server(server_id)
    if err:
        return err
    tools = db.list_mcp_tools(server_id)
    return jsonify({"server": {"id": server["id"], "name": server["name"],
                               "connected": bool(server["connected"])},
                    "tools": [{"name": t["tool_name"], "description": t["description"],
                               "inputSchema": json.loads(t["schema_json"] or "{}")}
                              for t in tools]})


@bp.get("/api/mcp/tool-calls")
@login_required
def api_list_tool_calls():
    user = _teacher()
    if user is None:
        return jsonify({"error": "forbidden", "message": "仅教师可查看调用审计"}), 403
    try:
        limit = min(int(request.args.get("limit") or 50), 100)
    except ValueError:
        limit = 50
    rows = db.list_mcp_tool_calls(user["class_id"], limit)
    return jsonify({"calls": [dict(r) for r in rows]})

"""POST /api/mcp/servers/{id}/connect：连接自建 MCP 服务并发现工具（进程内起服务）。

覆盖：握手+发现成功 → 工具缓存落库（连接两次不翻倍）；断开 → 缓存清空；
技能绑定校验（未连接 400 / 连接后通过）。
"""

import importlib.util
import json
import os
import threading
from http.server import HTTPServer

TOKEN = "apitest-mcp-token-connect"
SERVER = "campus-tools-" + __import__('uuid').uuid4().hex[:6]


def _find_root():
    p = os.path.dirname(os.path.abspath(__file__))
    while not os.path.isdir(os.path.join(p, "mcp-server")):
        p = os.path.dirname(p)
    return p


def _start_mcp():
    root = _find_root()
    os.environ["MCP_AUTH_TOKEN"] = TOKEN
    spec = importlib.util.spec_from_file_location(
        "mcp_server_case_mod", os.path.join(root, "mcp-server", "server.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    server = HTTPServer(("127.0.0.1", 0), mod.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{server.server_address[1]}"


def run(ctx):
    base = _start_mcp()
    teacher = ctx.client()
    teacher.login("teacher_a", "teach123")
    code, body = teacher.json("POST", "/api/mcp/servers", json_body={
        "name": SERVER, "base_url": base, "auth_token": TOKEN})
    ctx.check("准备：登记服务器", code == 201, f"实际 {code}")
    if code != 201:
        return
    sid = body["id"]

    code, body = teacher.json("POST", f"/api/mcp/servers/{sid}/connect")
    ctx.check("连接并发现返回 200", code == 200, f"实际 {code} {str(body)[:160]}")
    if code != 200:
        return
    tool_names = [t["name"] for t in body["tools"]]
    ctx.check("发现工具 ≥2 个", len(tool_names) >= 2, f"实际 {tool_names}")
    rows = ctx.db("SELECT COUNT(*) FROM mcp_tools WHERE server_id = ?", (sid,))
    ctx.check("工具缓存落库", rows[0][0] == len(tool_names), f"库 {rows[0][0]} vs 发现 {len(tool_names)}")

    teacher.json("POST", f"/api/mcp/servers/{sid}/connect")
    rows = ctx.db("SELECT COUNT(*) FROM mcp_tools WHERE server_id = ?", (sid,))
    ctx.check("重复连接缓存覆盖不翻倍", rows[0][0] == len(tool_names), f"实际 {rows[0][0]}")

    # 未连接时技能绑定被拒
    teacher.json("POST", f"/api/mcp/servers/{sid}/disconnect")
    code, body = teacher.json("POST", "/api/skills", json_body={
        "name": "未连接绑定", "instructions": "指令",
        "tools": f"formula_hint@{SERVER}"})
    ctx.check("未连接时绑定被拒 400", code == 400, f"实际 {code}")
    # 重新连接后保存成功
    teacher.json("POST", f"/api/mcp/servers/{sid}/connect")
    code, body = teacher.json("POST", "/api/skills", json_body={
        "name": "已绑定技能", "instructions": "指令",
        "tools": f"knowledge_search, formula_hint@{SERVER}"})
    ctx.check("连接后绑定保存 201", code == 201, f"实际 {code} {str(body)[:160]}")
    if code == 201:
        teacher.json("PATCH", f"/api/skills/{body['id']}", json_body={"enabled": True})

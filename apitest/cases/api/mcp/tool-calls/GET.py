"""GET /api/mcp/tool-calls：E2E——连接 MCP → 绑定技能的技能被提问命中 → 审计出现 ok；断开后 denied。"""

import importlib.util
import json
import os
import threading
from http.server import HTTPServer

TOKEN = "apitest-mcp-token-audit"
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
        "mcp_server_audit_mod", os.path.join(root, "mcp-server", "server.py"))
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
    if not ctx.check("准备：登记并连接 MCP 服务器", code == 201, f"实际 {code}"):
        return
    sid = body["id"]
    code, body = teacher.json("POST", f"/api/mcp/servers/{sid}/connect")
    if not ctx.check("准备：连接成功", code == 200, f"实际 {code} {str(body)[:120]}"):
        return

    code, skill = teacher.json("POST", "/api/skills", json_body={
        "name": "审计E2E技能", "instructions": "审计E2E标记：只引导。",
        "applicable": "生字词,课文",
        "tools": f"knowledge_search, formula_hint@{SERVER}"})
    if not ctx.check("准备：保存含 MCP 引用的技能", code == 201, f"实际 {code} {str(skill)[:160]}"):
        return
    teacher.json("PATCH", f"/api/skills/{skill['id']}", json_body={"enabled": True})

    student = ctx.client()
    student.login("student_a1", "stu123")
    code, conv = student.json("POST", "/api/conversations", json_body={})
    code, raw, _ = student.request("POST", f"/api/conversations/{conv['id']}/messages",
                                   json_body={"content": "生字词 课文导读"})
    events = [json.loads(l[6:]) for l in raw.decode("utf-8").split("\n\n")
              if l.startswith("data: ")]
    meta = next((e for e in events if e["type"] == "meta"), {})
    mine = next((t for t in (meta.get("tool_calls") or [])
                 if t["ref"] == f"formula_hint@{SERVER}"), None)
    ctx.check("meta.tool_calls 出现且状态 ok",
              mine is not None and mine["status"] == "ok",
              f"实际 {str(meta.get('tool_calls'))[:200]}")

    code, body = teacher.json("GET", "/api/mcp/tool-calls")
    ok_calls = [c for c in body.get("calls", []) if c["status"] == "ok"
                and c["tool_ref"] == f"formula_hint@{SERVER}"]
    ctx.check("审计表出现 ok 记录（含工具引用与服务器）", bool(ok_calls))
    if ok_calls:
        ctx.check("审计记录含服务器名与用户", bool(ok_calls[0]["server_name"])
                  and bool(ok_calls[0]["username"]))

    # 断开后同一技能提问：denied 且有审计行；主路径不中断
    teacher.json("POST", f"/api/mcp/servers/{sid}/disconnect")
    code, raw, _ = student.request("POST", f"/api/conversations/{conv['id']}/messages",
                                   json_body={"content": "生字词 课文导读"})
    ctx.check("断开后提问仍返回 200", code == 200, f"实际 {code}")
    events = [json.loads(l[6:]) for l in raw.decode("utf-8").split("\n\n")
              if l.startswith("data: ")]
    meta = next((e for e in events if e["type"] == "meta"), {})
    mine = next((t for t in (meta.get("tool_calls") or [])
                 if t["ref"] == f"formula_hint@{SERVER}"), None)
    ctx.check("断开后 tool_calls 为 denied",
              mine is not None and mine["status"] == "denied",
              f"实际 {str(meta.get('tool_calls'))[:200]}")
    code, body = teacher.json("GET", "/api/mcp/tool-calls")
    ctx.check("审计出现 denied 记录", any(c["status"] == "denied" for c in body.get("calls", [])))

    # 调用日志联动：日志里 tool_calls 与用户消息数据块一致
    code, body = teacher.json("GET", "/api/llm-logs")
    with_tool = [l for l in body.get("logs", []) if l.get("source") == "conversation"][:5]
    found = False
    for l in with_tool:
        code, detail = teacher.json("GET", f"/api/llm-logs/{l['id']}")
        log = detail.get("log", {})
        if log.get("tool_calls"):
            request = json.loads(log["request_json"])
            user_msg = request["messages"][-1]["content"]
            if f"[工具 formula_hint@{SERVER} 返回的数据]" in user_msg:
                found = True
                break
    ctx.check("调用日志记录 tool_calls 且用户消息含工具数据块", found)

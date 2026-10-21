"""POST /api/mcp/servers：登记服务器；令牌不回传（只有 has_auth）；同班同名 400；学生 403。"""

TOKEN = "apitest-mcp-token-123"


def run(ctx):
    student = ctx.client()
    student.login("student_a1", "stu123")
    code, _ = student.json("GET", "/api/mcp/servers")
    ctx.check("学生列出服务器 403", code == 403, f"实际 {code}")
    code, _ = student.json("POST", "/api/mcp/servers",
                           json_body={"name": "x", "base_url": "http://mcp-server:8090"})
    ctx.check("学生登记服务器 403", code == 403, f"实际 {code}")

    teacher = ctx.client()
    teacher.login("teacher_a", "teach123")
    code, body = teacher.json("POST", "/api/mcp/servers", json_body={
        "name": "campus-tools", "base_url": "http://127.0.0.1:1", "auth_token": TOKEN})
    ctx.check("教师登记服务器 201", code == 201, f"实际 {code}")
    if code != 201:
        return
    sid = body["id"]

    code, _ = teacher.json("POST", "/api/mcp/servers", json_body={
        "name": "campus-tools", "base_url": "http://127.0.0.1:1", "auth_token": TOKEN})
    ctx.check("同班同名登记 400", code == 400, f"实际 {code}")

    code, body = teacher.json("GET", "/api/mcp/servers")
    raw = str(body)
    ctx.check("列表含 has_auth 且不含令牌原文", "has_auth" in raw and TOKEN not in raw)
    mine = next(s for s in body["servers"] if s["id"] == sid)
    ctx.check("新服务器未连接、has_auth 为真", not mine["connected"] and mine["has_auth"])

    # 连接失败路径（地址不可达）：502 且状态未连接
    code, body = teacher.json("POST", f"/api/mcp/servers/{sid}/connect")
    ctx.check("不可达地址连接 502", code == 502, f"实际 {code}")
    rows = ctx.db("SELECT connected FROM mcp_servers WHERE id = ?", (sid,))
    ctx.check("连接失败后状态仍为未连接", bool(rows) and rows[0][0] == 0)
    code, _ = teacher.json("DELETE", f"/api/mcp/servers/{sid}")
    ctx.check("教师删除服务器 200", code == 200, f"实际 {code}")

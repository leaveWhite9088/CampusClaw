"""POST /api/login：登录签发 JWT + Cookie 会话；错误密码 401；令牌声明与库一致。"""


def run(ctx):
    c = ctx.client()
    code, body, headers = c.request("POST", "/api/login",
                                    json_body={"username": "teacher_a",
                                               "password": "teach123"})
    ctx.check("登录返回 200", code == 200, f"实际 {code}")
    if code != 200:
        return
    data = __import__("json").loads(body)
    ctx.check("响应含 username/role/class_id",
              all(k in data for k in ("username", "role", "class_id")))
    ctx.check("响应含 access_token 且 token_type=bearer",
              data.get("token_type") == "bearer" and bool(data.get("access_token")))
    ctx.check("响应 Set-Cookie 建立会话（HttpOnly）",
              "httponly" in str(headers.get("Set-Cookie", "")).lower())

    from apitest.lib import jwt_payload
    payload = jwt_payload(data["access_token"])
    ctx.check("令牌 payload 含 role/class_id/exp",
              all(k in payload for k in ("role", "class_id", "exp")))
    rows = ctx.db("SELECT role, class_id FROM users WHERE username = 'teacher_a'")
    ctx.check("令牌声明与数据库 users 行一致",
              bool(rows) and payload["role"] == rows[0][0]
              and payload["class_id"] == rows[0][1],
              f"payload={payload.get('role')}/{payload.get('class_id')} db={rows}")

    c2 = ctx.client()
    code2, _ = c2.json("POST", "/api/login",
                       json_body={"username": "teacher_a", "password": "wrong"})
    ctx.check("错误密码返回 401", code2 == 401, f"实际 {code2}")

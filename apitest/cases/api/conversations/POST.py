"""POST /api/conversations：学生新建会话，归属本人本班，与库一致。"""


def run(ctx):
    student = ctx.client()
    student.login("student_a1", "stu123")
    code, body = student.json("POST", "/api/conversations", json_body={})
    ctx.check("新建会话返回 201", code == 201, f"实际 {code}")
    if code != 201:
        return
    cid = body["id"]
    uid = ctx.db("SELECT id FROM users WHERE username = 'student_a1'")[0][0]
    rows = ctx.db("SELECT user_id, class_id FROM conversations WHERE id = ?", (cid,))
    ctx.check("会话归属 student_a1 且为班级 1",
              bool(rows) and rows[0][0] == uid and rows[0][1] == 1,
              f"db={rows}")

    code, body = student.json("GET", "/api/conversations")
    ctx.check("会话列表含新会话",
              code == 200 and any(c["id"] == cid for c in body.get("conversations", [])))

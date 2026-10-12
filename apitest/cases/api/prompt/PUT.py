"""PUT /api/prompt：教师保存提示词并与库一致；学生 403 且库不变。"""

CONTENT = "接口测试提示词：你是解题助手，只引导不给答案。"


def run(ctx):
    teacher = ctx.client()
    teacher.login("teacher_a", "teach123")
    code, body = teacher.json("PUT", "/api/prompt", json_body={"content": CONTENT})
    ctx.check("教师保存提示词返回 200", code == 200, f"实际 {code}")

    code, body = teacher.json("GET", "/api/prompt")
    ctx.check("GET 读回一致", code == 200 and body.get("content") == CONTENT)
    rows = ctx.db("SELECT content FROM class_prompts WHERE class_id = 1")
    ctx.check("数据库 class_prompts 与提交一致",
              bool(rows) and rows[0][0] == CONTENT)

    student = ctx.client()
    student.login("student_a1", "stu123")
    code, _ = student.json("PUT", "/api/prompt", json_body={"content": "学生篡改"})
    ctx.check("学生保存提示词返回 403", code == 403, f"实际 {code}")
    rows2 = ctx.db("SELECT content FROM class_prompts WHERE class_id = 1")
    ctx.check("学生被拒后库中提示词未变", bool(rows2) and rows2[0][0] == CONTENT)

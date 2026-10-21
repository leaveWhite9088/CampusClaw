"""GET /api/llm-logs：调用日志列表/详情；字段完整；学生 403；班级隔离。"""

QUESTION = "生字词 课文导读"


def run(ctx):
    student = ctx.client()
    student.login("student_a1", "stu123")
    code, body = student.json("POST", "/api/conversations", json_body={})
    if code != 201:
        ctx.check("准备：学生会话创建", False, f"实际 {code}")
        return
    cid = body["id"]
    student.request("POST", f"/api/conversations/{cid}/messages",
                    json_body={"content": QUESTION})

    teacher = ctx.client()
    teacher.login("teacher_a", "teach123")
    code, body = teacher.json("GET", "/api/llm-logs")
    ctx.check("教师读取日志 200 且非空", code == 200 and bool(body["logs"]), f"实际 {code}")
    if not body.get("logs"):
        return
    latest = body["logs"][0]
    ctx.check("日志含知识库统计字段",
              latest["kb_total_chunks"] >= latest["kb_passed_chunks"] >= 1,
              f"total={latest['kb_total_chunks']} passed={latest['kb_passed_chunks']}")
    code, detail = teacher.json("GET", f"/api/llm-logs/{latest['id']}")
    ctx.check("详情返回 200", code == 200)
    request = json_parse(detail["log"]["request_json"]) if detail else None
    ctx.check("request_json 含 model 与 messages",
              bool(request) and "model" in request and isinstance(request["messages"], list))
    ctx.check("messages 首条为 system、末条为 user",
              request["messages"][0]["role"] == "system"
              and request["messages"][-1]["role"] == "user")
    ctx.check("template_name 已记录", bool(detail["log"]["template_name"]))

    code, _ = student.json("GET", "/api/llm-logs")
    ctx.check("学生读取日志 403", code == 403, f"实际 {code}")
    # 班级隔离：他班日志按 id 访问不可见
    other = ctx.db("SELECT l.id FROM llm_call_logs l JOIN conversations c "
                   "ON c.id = l.conversation_id WHERE c.class_id != "
                   "(SELECT class_id FROM users WHERE username='teacher_a') LIMIT 1")
    if other:
        code, _ = teacher.json("GET", f"/api/llm-logs/{other[0][0]}")
        ctx.check("他班日志按 id 访问 404", code == 404, f"实际 {code}")


def json_parse(text):
    import json
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return None

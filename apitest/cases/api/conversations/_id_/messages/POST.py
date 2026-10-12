"""POST /api/conversations/<id>/messages：SSE 流式回答；事件序列、落库一致、越权 403。"""

from apitest.lib import parse_sse


def run(ctx):
    student = ctx.client()
    student.login("student_a1", "stu123")
    code, body = student.json("POST", "/api/conversations", json_body={})
    ctx.check("准备：新建会话", code == 201, f"实际 {code}")
    if code != 201:
        return
    cid = body["id"]

    # 提问命中 A 班种子材料（语文讲义：生字词与课文导读）
    code, raw, headers = student.request(
        "POST", f"/api/conversations/{cid}/messages",
        json_body={"content": "生字词 课文导读"})
    ctx.check("发消息返回 200", code == 200, f"实际 {code}")
    ctx.check("Content-Type 为 text/event-stream",
              "text/event-stream" in str(headers.get("Content-Type", "")))
    if code != 200:
        return

    events = parse_sse(raw)
    types = [e["type"] for e in events]
    ctx.check("事件序列：delta… → citations → done",
              "delta" in types and "citations" in types and types[-1] == "done"
              and types.index("citations") > types.index("delta"),
              f"实际 {types}")
    answer = "".join(e["text"] for e in events if e["type"] == "delta")
    citations = next((e["citations"] for e in events if e["type"] == "citations"), [])
    ctx.check("回答非空", bool(answer))
    ctx.check("citations 非空且含材料标题",
              bool(citations) and bool(citations[0].get("material_title")))

    # 数据库一致性：user/assistant 各一条，assistant 内容与 SSE 拼接一致
    msgs = ctx.db(
        "SELECT role, content, citations FROM messages WHERE conversation_id = ? "
        "ORDER BY id", (cid,))
    ctx.check("库中 user/assistant 各一条",
              len(msgs) == 2 and msgs[0][0] == "user" and msgs[1][0] == "assistant",
              f"实际 {len(msgs)} 条")
    if len(msgs) == 2:
        ctx.check("assistant 落库内容 == SSE 拼接", msgs[1][1] == answer)
        import json
        db_cits = json.loads(msgs[1][2] or "[]")
        ctx.check("assistant 落库 citations 非空", bool(db_cits))

    # 历史接口可读且一致
    code, body = student.json("GET", f"/api/conversations/{cid}/messages")
    ctx.check("历史消息接口返回两条",
              code == 200 and len(body.get("messages", [])) == 2)

    # 无命中问题：固定文案、空 citations
    code, raw, _ = student.request(
        "POST", f"/api/conversations/{cid}/messages",
        json_body={"content": "今天天气怎么样"})
    events = parse_sse(raw)
    answer2 = "".join(e["text"] for e in events if e["type"] == "delta")
    cits2 = next((e["citations"] for e in events if e["type"] == "citations"), None)
    ctx.check("无命中返回固定文案", answer2 == "资料中未找到相关内容", answer2[:30])
    ctx.check("无命中 citations 为空", cits2 == [])

    # 越权：教师（非会话主人）访问被拒
    teacher = ctx.client()
    teacher.login("teacher_a", "teach123")
    code, _ = teacher.json("GET", f"/api/conversations/{cid}/messages")
    ctx.check("非本人会话返回 403", code == 403, f"实际 {code}")

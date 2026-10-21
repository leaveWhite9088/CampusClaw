"""POST /api/skills/upload：上传课程技能文件格式；解析入库；非法 400；学生 403。"""

MD_SKILL = """名称：朗读指导技能
适用条件：朗读,背诵
工具：knowledge_search
启用：是

你是朗读指导助手。先示范断句，再让学生自己读，不直接评价最终成绩。"""


def run(ctx):
    teacher = ctx.client()
    teacher.login("teacher_a", "teach123")
    code, raw, _ = teacher.request("POST", "/api/skills/upload",
                                   files={"file": ("skill.md", MD_SKILL.encode("utf-8"),
                                                   "text/markdown")})
    body = json_load(raw)
    ctx.check("教师上传技能返回 201", code == 201, f"实际 {code} {str(body)[:120]}")
    if code != 201:
        return
    rows = ctx.db("SELECT name, applicable, enabled, source FROM skills WHERE id = ?",
                  (body["id"],))
    ctx.check("解析入库：名称/适用条件/启用/来源",
              bool(rows) and rows[0][0] == "朗读指导技能"
              and rows[0][1] == "朗读,背诵" and rows[0][2] == 1 and rows[0][3] == "uploaded")

    # 非法：缺名称
    code, raw, _ = teacher.request("POST", "/api/skills/upload",
                                   files={"file": ("bad.md", "没有头部的正文".encode(), "text/markdown")})
    ctx.check("缺名称的文件返回 400", code == 400, f"实际 {code}")
    # 非法：工具引用格式
    bad = "名称：坏技能\n工具：Formula_Hint@x\n\n正文"
    code, raw, _ = teacher.request("POST", "/api/skills/upload",
                                   files={"file": ("bad.md", bad.encode(), "text/markdown")})
    ctx.check("工具引用非法返回 400", code == 400 and "工具引用格式非法" in json_load(raw).get("message", ""), f"实际 {code}")

    student = ctx.client()
    student.login("student_a1", "stu123")
    code, _, _ = student.request("POST", "/api/skills/upload",
                                 files={"file": ("s.md", "名称：x\n\n正文".encode(), "text/markdown")})
    ctx.check("学生上传技能 403", code == 403, f"实际 {code}")


def json_load(raw):
    import json
    try:
        return json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError, AttributeError):
        return {}

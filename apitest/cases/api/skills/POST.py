"""POST /api/skills（+ PATCH 启用）：教师新建/开关技能并与库一致；学生写操作 403。"""

NAME = "接口测试技能"


def run(ctx):
    teacher = ctx.client()
    teacher.login("teacher_a", "teach123")
    code, body = teacher.json("POST", "/api/skills", json_body={
        "name": NAME, "description": "接口测试用技能简介",
        "instructions": "接口测试用完整指令：只引导，不给答案。",
    })
    ctx.check("教师新建技能返回 201", code == 201, f"实际 {code}")
    if code != 201:
        return
    sid = body["id"]
    rows = ctx.db("SELECT enabled, instructions FROM skills WHERE id = ?", (sid,))
    ctx.check("技能已入库且默认停用",
              bool(rows) and rows[0][0] == 0 and rows[0][1] != "")

    code, _ = teacher.json("PATCH", f"/api/skills/{sid}", json_body={"enabled": True})
    ctx.check("教师启用技能返回 200", code == 200, f"实际 {code}")
    rows = ctx.db("SELECT enabled FROM skills WHERE id = ?", (sid,))
    ctx.check("数据库 enabled=1", bool(rows) and rows[0][0] == 1)

    student = ctx.client()
    student.login("student_a1", "stu123")
    code, _ = student.json("POST", "/api/skills",
                           json_body={"name": "x", "instructions": "y"})
    ctx.check("学生新建技能返回 403", code == 403, f"实际 {code}")
    code, _ = student.json("PATCH", f"/api/skills/{sid}", json_body={"enabled": False})
    ctx.check("学生开关技能返回 403", code == 403, f"实际 {code}")
    rows = ctx.db("SELECT enabled FROM skills WHERE id = ?", (sid,))
    ctx.check("学生被拒后技能仍启用", bool(rows) and rows[0][0] == 1)

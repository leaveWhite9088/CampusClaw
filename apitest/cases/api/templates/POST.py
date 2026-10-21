"""POST /api/templates：教师维护提示词模板；学生 403；内置模板不可删。"""

NAME = "接口测试模板"


def run(ctx):
    teacher = ctx.client()
    teacher.login("teacher_a", "teach123")
    code, body = teacher.json("POST", "/api/templates", json_body={
        "name": NAME, "content": "接口模板正文 {{knowledge}}"})
    ctx.check("教师新建模板返回 201", code == 201, f"实际 {code}")
    if code != 201:
        return
    tid = body["id"]
    rows = ctx.db("SELECT name, content, built_in FROM prompt_templates WHERE id = ?", (tid,))
    ctx.check("模板入库且 built_in=0", bool(rows) and rows[0][0] == NAME
              and rows[0][2] == 0)

    code, body = teacher.json("GET", "/api/templates")
    ctx.check("列表含新模板", any(t["id"] == tid for t in body["templates"]))
    ctx.check("内置模板已预置（≥3）",
              sum(1 for t in body["templates"] if t["built_in"]) >= 3)

    code, _ = teacher.json("DELETE", f"/api/templates/{tid}")
    ctx.check("教师删除自定义模板 200", code == 200, f"实际 {code}")
    builtin = next(t for t in body["templates"] if t["built_in"])
    code, _ = teacher.json("DELETE", f"/api/templates/{builtin['id']}")
    ctx.check("内置模板删除被拒 400", code == 400, f"实际 {code}")

    student = ctx.client()
    student.login("student_a1", "stu123")
    code, _ = student.json("POST", "/api/templates",
                           json_body={"name": "x", "content": "y"})
    ctx.check("学生新建模板 403", code == 403, f"实际 {code}")

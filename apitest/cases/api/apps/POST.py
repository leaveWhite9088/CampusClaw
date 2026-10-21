"""POST /api/apps：教师创建应用并绑定；跨班绑定 400；学生 403；内置不可删。"""


def run(ctx):
    teacher = ctx.client()
    teacher.login("teacher_a", "teach123")
    _, tpls = teacher.json("GET", "/api/templates")
    _, skills = teacher.json("GET", "/api/skills")
    code, body = teacher.json("POST", "/api/apps", json_body={
        "name": "接口测试应用", "description": "简介",
        "template_id": tpls["templates"][0]["id"],
        "skill_ids": [skills["skills"][0]["id"]],
    })
    ctx.check("教师新建应用返回 201", code == 201, f"实际 {code}")
    if code != 201:
        return
    app_id = body["id"]
    rows = ctx.db("SELECT name, built_in FROM ai_apps WHERE id = ?", (app_id,))
    ctx.check("应用入库且 built_in=0", bool(rows) and rows[0][1] == 0)

    # 跨班材料绑定被拒
    b_mat = ctx.db("SELECT id FROM materials WHERE class_id != "
                   "(SELECT class_id FROM users WHERE username='teacher_a') LIMIT 1")
    if b_mat:
        code, _ = teacher.json("POST", "/api/apps", json_body={
            "name": "越权绑定", "material_ids": [b_mat[0][0]]})
        ctx.check("绑定他班材料返回 400", code == 400, f"实际 {code}")

    code, body = teacher.json("GET", "/api/apps")
    mine = next(a for a in body["apps"] if a["id"] == app_id)
    ctx.check("应用列表含绑定信息", mine["template_name"] and isinstance(mine["skill_names"], list))
    ctx.check("内置应用已预置（≥3）", sum(1 for a in body["apps"] if a["built_in"]) >= 3)

    builtin = next(a for a in body["apps"] if a["built_in"])
    code, _ = teacher.json("DELETE", f"/api/apps/{builtin['id']}")
    ctx.check("内置应用删除被拒 400", code == 400, f"实际 {code}")
    code, _ = teacher.json("DELETE", f"/api/apps/{app_id}")
    ctx.check("自定义应用删除 200", code == 200, f"实际 {code}")

    student = ctx.client()
    student.login("student_a1", "stu123")
    code, _ = student.json("POST", "/api/apps", json_body={"name": "x"})
    ctx.check("学生新建应用 403", code == 403, f"实际 {code}")
    code, body = student.json("GET", "/api/apps")
    ctx.check("学生可读应用列表", code == 200 and len(body["apps"]) >= 3)

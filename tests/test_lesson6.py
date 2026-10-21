"""第 6 课测试：AI 应用 / 提示词模板 / 技能上传 / LLM 调用日志。

运行方式（仓库根目录）：
    python tests/test_lesson6.py

数据相关用例需要可达的 Qdrant（同第 4 课）；嵌入/对话由内置 stub 网关扮演。
MCP 相关见 tests/test_mcp.py。
"""

import io
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

_TMP = tempfile.mkdtemp(prefix="campusclaw-test6-")
os.environ["DATABASE"] = os.path.join(_TMP, "app.db")
os.environ["UPLOAD_DIR"] = os.path.join(_TMP, "uploads")
os.environ["SECRET_KEY"] = "test-secret"

from test_lesson4 import QDRANT_UP, _start_stub, _StubHandler  # noqa: E402

_STUB = _start_stub()
os.environ.update({
    "EMBEDDING_API_BASE": _STUB, "EMBEDDING_API_KEY": "test-key",
    "EMBEDDING_MODEL": "stub-embed", "CHAT_API_BASE": _STUB,
    "CHAT_API_KEY": "test-key", "CHAT_MODEL": "stub-chat",
})


def _parse_sse(text):
    return [json.loads(l[6:]) for l in text.split("\n\n") if l.startswith("data: ")]


MATH_NOTES = """# 数学自习笔记

## 去括号

去括号法则：括号前是加号，去括号后各项不变号；括号前是减号，去括号后每一项都要变号。
例：(3a + 2b) - (a - b) = 2a + 3b。

## 单位换算

1 米 = 100 厘米，1 千米 = 1000 米，1 千克 = 1000 克。
大单位化小单位乘进率，小单位化大单位除以进率。
"""


class Lesson6Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import scripts.init_db as init_db
        init_db.main()
        from app import create_app
        cls.app = create_app()
        cls.app.config["TESTING"] = True

    def setUp(self):
        self.client = self.app.test_client()

    def login(self, username, password):
        resp = self.client.post("/api/login", json={"username": username, "password": password})
        self.assertEqual(resp.status_code, 200)
        return resp.get_json()["access_token"]

    def bearer(self, token):
        return {"Authorization": f"Bearer {token}"}

    def upload_material(self, token, title, body, filename="notes.md"):
        data = {"title": title,
                "file": (io.BytesIO(body.encode("utf-8")), filename)}
        return self.client.post("/materials/upload", data=data,
                                headers=self.bearer(token))


class TemplateTest(Lesson6Base):
    def test_seed_templates_builtin(self):
        t = self.login("teacher_a", "teach123")
        data = self.client.get("/api/templates", headers=self.bearer(t)).get_json()
        names = [x["name"] for x in data["templates"]]
        self.assertGreaterEqual(len(names), 3)
        self.assertTrue(all(x["built_in"] for x in data["templates"][:3]))
        self.assertIn("解题引导模板", names)

    def test_teacher_crud_student_403(self):
        t = self.login("teacher_a", "teach123")
        resp = self.client.post("/api/templates", json={
            "name": "测试模板", "content": "模板正文 {{knowledge}}"}, headers=self.bearer(t))
        self.assertEqual(resp.status_code, 201)
        tid = resp.get_json()["id"]
        resp = self.client.put(f"/api/templates/{tid}", json={"content": "改"},
                               headers=self.bearer(t))
        self.assertEqual(resp.status_code, 200)
        data = self.client.get("/api/templates", headers=self.bearer(t)).get_json()
        self.assertTrue(any(x["content"] == "改" for x in data["templates"]))
        # 自定义模板可删
        self.assertEqual(self.client.delete(f"/api/templates/{tid}",
                                            headers=self.bearer(t)).status_code, 200)

        s = self.login("student_a1", "stu123")
        self.assertEqual(self.client.post("/api/templates", json={"name": "x", "content": "y"},
                                          headers=self.bearer(s)).status_code, 403)
        t = self.login("teacher_a", "teach123")
        builtin = next(x for x in self.client.get(
            "/api/templates", headers=self.bearer(t)).get_json()["templates"] if x["built_in"])
        self.assertEqual(self.client.delete(f"/api/templates/{builtin['id']}",
                                            headers=self.bearer(t)).status_code, 400)


class AppTest(Lesson6Base):
    def test_seed_apps(self):
        t = self.login("teacher_a", "teach123")
        data = self.client.get("/api/apps", headers=self.bearer(t)).get_json()
        names = [a["name"] for a in data["apps"]]
        self.assertGreaterEqual(len(names), 3)
        for expected in ("资料问答助手", "解题引导助手", "作文点评助手"):
            self.assertIn(expected, names)
        self.assertTrue(all(a["built_in"] for a in data["apps"][:3]))

    def test_create_app_with_bindings_and_cross_class_400(self):
        t = self.login("teacher_a", "teach123")
        tpls = self.client.get("/api/templates", headers=self.bearer(t)).get_json()["templates"]
        skills = self.client.get("/api/skills", headers=self.bearer(t)).get_json()["skills"]
        resp = self.client.post("/api/apps", json={
            "name": "测试应用", "description": "简介",
            "template_id": tpls[0]["id"],
            "skill_ids": [skills[0]["id"]],
        }, headers=self.bearer(t))
        self.assertEqual(resp.status_code, 201)
        app_id = resp.get_json()["id"]
        # B 班材料不属于 A 班：绑定校验拒绝
        b_mat = self.client.get("/api/materials/list",
                                headers=self.bearer(self.login("student_b1", "stu123")))
        # student_b1 的材料列表属于 B 班，用 teacher_a 绑定应 400
        mats_b = self.client.get("/api/materials/list",
                                 headers=self.bearer(t))  # A 班列表
        # 构造他班材料 id：直接查库取 B 班材料
        import sqlite3
        conn = sqlite3.connect(os.environ["DATABASE"])
        try:
            b_material_id = conn.execute(
                "SELECT id FROM materials WHERE title LIKE 'B 班%'").fetchone()[0]
        finally:
            conn.close()
        resp = self.client.post("/api/apps", json={
            "name": "越权绑定", "material_ids": [b_material_id]}, headers=self.bearer(t))
        self.assertEqual(resp.status_code, 400)

        # 学生写 403；学生可读
        s = self.login("student_a1", "stu123")
        self.assertEqual(self.client.post("/api/apps", json={"name": "x"},
                                          headers=self.bearer(s)).status_code, 403)
        apps = self.client.get("/api/apps", headers=self.bearer(s)).get_json()["apps"]
        self.assertTrue(any(a["id"] == app_id for a in apps))
        # 内置应用不可删；自定义可删
        t = self.login("teacher_a", "teach123")
        builtin = next(a for a in self.client.get(
            "/api/apps", headers=self.bearer(t)).get_json()["apps"] if a["built_in"])
        self.assertEqual(self.client.delete(f"/api/apps/{builtin['id']}",
                                            headers=self.bearer(t)).status_code, 400)
        self.assertEqual(self.client.delete(f"/api/apps/{app_id}",
                                            headers=self.bearer(t)).status_code, 200)


@unittest.skipUnless(QDRANT_UP, "Qdrant 不可达")
class AppChatOrchestrationTest(Lesson6Base):
    def test_app_conversation_uses_template_and_skill(self):
        t = self.login("teacher_a", "teach123")
        # 上传第二份材料，验证绑定材料子集生效
        self.upload_material(t, "A 班·数学自习笔记", MATH_NOTES)
        tpl = self.client.post("/api/templates", json={
            "name": "标记模板T6", "content": "模板标记TEMPLATE_T6 {{knowledge}}"},
            headers=self.bearer(t)).get_json()
        skill = self.client.post("/api/skills", json={
            "name": "标记技能S6", "instructions": "技能标记SKILL_T6"},
            headers=self.bearer(t)).get_json()
        self.client.patch(f"/api/skills/{skill['id']}", json={"enabled": True},
                          headers=self.bearer(t))
        # 绑定材料子集：只绑数学笔记
        mats = [m for m in self.client.get("/api/materials/list",
                                           headers=self.bearer(t)).get_json()["materials"]
                if "数学" in m["title"]]
        app_id = self.client.post("/api/apps", json={
            "name": "编排测试应用", "template_id": tpl["id"],
            "skill_ids": [skill["id"]], "material_ids": [mats[0]["id"]],
        }, headers=self.bearer(t)).get_json()["id"]

        s = self.login("student_a1", "stu123")
        conv = self.client.post(f"/api/apps/{app_id}/conversations", json={},
                                headers=self.bearer(s)).get_json()
        self.assertEqual(conv["app_id"], app_id)
        before = len(_StubHandler.chat_calls)
        resp = self.client.post(f"/api/conversations/{conv['id']}/messages",
                                json={"content": "去括号法则是什么"},
                                headers=self.bearer(s))
        events = _parse_sse(resp.get_data(as_text=True))
        types = [e["type"] for e in events]
        self.assertEqual(types[-1], "done")
        meta = next(e for e in events if e["type"] == "meta")
        self.assertEqual(meta["app_id"], app_id)

        system = _StubHandler.chat_calls[-1][0]["content"]
        self.assertIn("模板标记TEMPLATE_T6", system)   # 模板正文随请求传给 LLM
        self.assertIn("技能标记SKILL_T6", system)      # 技能完整指令注入
        self.assertIn("[1] 材料《A 班·数学自习笔记》", system)  # 编号资料（限定范围内）
        self.assertNotIn("语文第一单元", system)       # 绑定材料子集之外的资料不出现
        # 旧会话（无应用）不受影响：走班级提示词路径
        conv2 = self.client.post("/api/conversations", json={},
                                 headers=self.bearer(s)).get_json()
        self.client.post(f"/api/conversations/{conv2['id']}/messages",
                         json={"content": "生字词 课文导读"}, headers=self.bearer(s))
        system2 = _StubHandler.chat_calls[-1][0]["content"]
        self.assertNotIn("模板标记TEMPLATE_T6", system2)

    def test_applicable_keyword_gates_skill(self):
        t = self.login("teacher_a", "teach123")
        skill = self.client.post("/api/skills", json={
            "name": "仅作文技能", "instructions": "作文标记ZUOWEN_T6",
            "applicable": "作文,写作"}, headers=self.bearer(t)).get_json()
        self.client.patch(f"/api/skills/{skill['id']}", json={"enabled": True},
                          headers=self.bearer(t))
        app_id = self.client.post("/api/apps", json={
            "name": "适用条件应用", "skill_ids": [skill["id"]]},
            headers=self.bearer(t)).get_json()["id"]
        s = self.login("student_a1", "stu123")
        conv = self.client.post(f"/api/apps/{app_id}/conversations", json={},
                                headers=self.bearer(s)).get_json()
        # 未命中关键词：技能不注入
        self.client.post(f"/api/conversations/{conv['id']}/messages",
                         json={"content": "生字词 课文导读"}, headers=self.bearer(s))
        system = _StubHandler.chat_calls[-1][0]["content"]
        self.assertNotIn("作文标记ZUOWEN_T6", system)
        # 命中关键词（且提问同时命中材料，走到生成路径）：注入
        self.client.post(f"/api/conversations/{conv['id']}/messages",
                         json={"content": "作文 生字词 课文导读"}, headers=self.bearer(s))
        system = _StubHandler.chat_calls[-1][0]["content"]
        self.assertIn("作文标记ZUOWEN_T6", system)


class SkillUploadTest(Lesson6Base):
    def test_upload_md_skill(self):
        t = self.login("teacher_a", "teach123")
        content = ("名称：古诗鉴赏引导\n适用条件：古诗,唐诗\n工具：knowledge_search\n启用：是\n"
                   "\n你是古诗鉴赏引导助手。先讲意象，再让学生自己品。")
        resp = self.client.post(
            "/api/skills/upload",
            data={"file": (io.BytesIO(content.encode("utf-8")), "skill.md")},
            headers=self.bearer(t),
            content_type="multipart/form-data")
        self.assertEqual(resp.status_code, 201, resp.get_data(as_text=True))
        parsed = resp.get_json()["skill"]
        self.assertEqual(parsed["name"], "古诗鉴赏引导")
        self.assertEqual(parsed["applicable"], "古诗,唐诗")
        self.assertTrue(parsed["enabled"])
        skills = self.client.get("/api/skills", headers=self.bearer(t)).get_json()["skills"]
        row = next(x for x in skills if x["name"] == "古诗鉴赏引导")
        self.assertEqual(row["source"], "uploaded")
        self.assertTrue(row["enabled"])

    def test_upload_json_skill(self):
        t = self.login("teacher_a", "teach123")
        body = json.dumps({"name": "朗读指导", "instructions": "先示范断句，再让学生读。",
                           "applicable": ["朗读", "背诵"], "enabled": True})
        resp = self.client.post("/api/skills/upload", json={
            "filename": "skill.json", "content": body}, headers=self.bearer(t))
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.get_json()["skill"]["applicable"], "朗读,背诵")

    def test_upload_invalid_rejected(self):
        t = self.login("teacher_a", "teach123")
        # 缺名称
        resp = self.client.post("/api/skills/upload", json={
            "filename": "s.md", "content": "只有正文没有头部"}, headers=self.bearer(t))
        self.assertEqual(resp.status_code, 400)
        # 工具引用格式非法
        bad = "名称：坏技能\n工具：Formula_Hint@x\n\n正文指令"
        resp = self.client.post("/api/skills/upload", json={
            "filename": "s.md", "content": bad}, headers=self.bearer(t))
        self.assertEqual(resp.status_code, 400)
        self.assertIn("工具引用格式非法", resp.get_json()["message"])
        # 学生 403
        s = self.login("student_a1", "stu123")
        resp = self.client.post("/api/skills/upload", json={
            "filename": "s.md", "content": "名称：x\n\n正文"}, headers=self.bearer(s))
        self.assertEqual(resp.status_code, 403)


@unittest.skipUnless(QDRANT_UP, "Qdrant 不可达")
class LlmLogTest(Lesson6Base):
    def test_log_written_with_full_request(self):
        t = self.login("teacher_a", "teach123")
        skills = self.client.get("/api/skills", headers=self.bearer(t)).get_json()["skills"]
        seed = next(s for s in skills if s["name"] == "解题引导")
        self.client.patch(f"/api/skills/{seed['id']}", json={"enabled": True},
                          headers=self.bearer(t))
        s = self.login("student_a1", "stu123")
        conv = self.client.post("/api/conversations", json={},
                                headers=self.bearer(s)).get_json()
        self.client.post(f"/api/conversations/{conv['id']}/messages",
                         json={"content": "生字词 课文导读"}, headers=self.bearer(s))

        resp = self.client.get("/api/llm-logs", headers=self.bearer(t))
        self.assertEqual(resp.status_code, 200)
        logs = resp.get_json()["logs"]
        self.assertTrue(logs)
        latest = logs[0]
        self.assertLessEqual(latest["kb_passed_chunks"], latest["kb_total_chunks"])
        detail = self.client.get(f"/api/llm-logs/{latest['id']}",
                                 headers=self.bearer(t)).get_json()["log"]
        request = json.loads(detail["request_json"])
        self.assertIn("model", request)
        self.assertIn("messages", request)
        self.assertEqual(request["messages"][0]["role"], "system")
        self.assertEqual(request["messages"][-1]["role"], "user")
        self.assertEqual(request["stream"], False)
        self.assertIn("不直接给出最终答案", request["messages"][0]["content"])  # 技能完整指令
        self.assertEqual(detail["status"], "ok")

        # 学生 403；班级隔离：B 班产生的日志，A 班教师按 id 访问得到 404
        self.assertEqual(self.client.get("/api/llm-logs",
                                         headers=self.bearer(s)).status_code, 403)
        b = self.login("student_b1", "stu123")
        conv_b = self.client.post("/api/conversations", json={},
                                  headers=self.bearer(b)).get_json()
        self.client.post(f"/api/conversations/{conv_b['id']}/messages",
                         json={"content": "集合与常用逻辑用语"}, headers=self.bearer(b))
        import sqlite3
        conn = sqlite3.connect(os.environ["DATABASE"])
        try:
            b_log_id = conn.execute(
                "SELECT l.id FROM llm_call_logs l JOIN conversations c "
                "ON c.id = l.conversation_id WHERE c.class_id != ?",
                (1,)).fetchone()
        finally:
            conn.close()
        if b_log_id is not None:
            resp = self.client.get(f"/api/llm-logs/{b_log_id[0]}",
                                   headers=self.bearer(t))
            self.assertIn(resp.status_code, (403, 404))

    def test_ask_writes_log_too(self):
        s = self.login("student_a1", "stu123")
        self.client.post("/api/ask", json={"question": "生字词 课文导读"},
                         headers=self.bearer(s))
        t = self.login("teacher_a", "teach123")
        logs = self.client.get("/api/llm-logs", headers=self.bearer(t)).get_json()["logs"]
        self.assertTrue(any(l["source"] == "ask" for l in logs))


if __name__ == "__main__":
    unittest.main(verbosity=2)

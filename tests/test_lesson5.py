"""第 5 课测试：提示词/技能权限与注入、会话归属、SSE 事件序列、OpenAPI/Swagger。

运行方式（仓库根目录）：
    python tests/test_lesson5.py

数据相关用例需要可达的 Qdrant（同第 4 课）；嵌入/对话由内置 stub 网关扮演。
"""

import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.request
from http.server import HTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

_TMP = tempfile.mkdtemp(prefix="campusclaw-test5-")
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


class Lesson5Base(unittest.TestCase):
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


class PromptSkillTest(Lesson5Base):
    def test_teacher_put_prompt_and_readback(self):
        t = self.login("teacher_a", "teach123")
        resp = self.client.put("/api/prompt", json={"content": "测试提示词：只引导"},
                               headers=self.bearer(t))
        self.assertEqual(resp.status_code, 200)
        resp = self.client.get("/api/prompt", headers=self.bearer(t))
        self.assertEqual(resp.get_json()["content"], "测试提示词：只引导")

    def test_student_cannot_put_prompt(self):
        s = self.login("student_a1", "stu123")
        before = self.client.get("/api/prompt", headers=self.bearer(s)).get_json()["content"]
        resp = self.client.put("/api/prompt", json={"content": "篡改"},
                               headers=self.bearer(s))
        self.assertEqual(resp.status_code, 403)
        after = self.client.get("/api/prompt", headers=self.bearer(s)).get_json()["content"]
        self.assertEqual(before, after)

    def test_skill_crud_and_student_403(self):
        t = self.login("teacher_a", "teach123")
        resp = self.client.post("/api/skills", json={
            "name": "测试技能", "description": "简介", "instructions": "指令全文",
        }, headers=self.bearer(t))
        self.assertEqual(resp.status_code, 201)
        sid = resp.get_json()["id"]
        resp = self.client.patch(f"/api/skills/{sid}", json={"enabled": True},
                                 headers=self.bearer(t))
        self.assertEqual(resp.status_code, 200)
        skills = self.client.get("/api/skills", headers=self.bearer(t)).get_json()["skills"]
        self.assertTrue(any(s["id"] == sid and s["enabled"] for s in skills))

        s = self.login("student_a1", "stu123")
        self.assertEqual(self.client.post(
            "/api/skills", json={"name": "x", "instructions": "y"},
            headers=self.bearer(s)).status_code, 403)
        self.assertEqual(self.client.patch(
            f"/api/skills/{sid}", json={"enabled": False},
            headers=self.bearer(s)).status_code, 403)

    def test_seed_skill_exists(self):
        t = self.login("teacher_a", "teach123")
        skills = self.client.get("/api/skills", headers=self.bearer(t)).get_json()["skills"]
        seed = [s for s in skills if s["name"] == "解题引导"]
        self.assertTrue(seed, "种子技能「解题引导」应存在")
        self.assertIn("不直接给出最终答案", seed[0]["instructions"])


@unittest.skipUnless(QDRANT_UP, "Qdrant 不可达")
class ConversationSseTest(Lesson5Base):
    def _new_conv(self, token):
        resp = self.client.post("/api/conversations", json={},
                                headers=self.bearer(token))
        self.assertEqual(resp.status_code, 201)
        return resp.get_json()["id"]

    def test_sse_event_sequence_and_persistence(self):
        s = self.login("student_a1", "stu123")
        cid = self._new_conv(s)
        resp = self.client.post(f"/api/conversations/{cid}/messages",
                                json={"content": "生字词 课文导读"},
                                headers=self.bearer(s))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/event-stream", resp.content_type)
        events = _parse_sse(resp.get_data(as_text=True))
        types = [e["type"] for e in events]
        self.assertIn("delta", types)
        self.assertIn("citations", types)
        self.assertEqual(types[-1], "done")
        self.assertLess(types.index("delta"), types.index("citations"))

        answer = "".join(e["text"] for e in events if e["type"] == "delta")
        self.assertTrue(answer)
        # 落库一致：拼接 delta == assistant 消息内容
        msgs = self.client.get(f"/api/conversations/{cid}/messages",
                               headers=self.bearer(s)).get_json()["messages"]
        self.assertEqual([m["role"] for m in msgs], ["user", "assistant"])
        self.assertEqual(msgs[1]["content"], answer)
        self.assertTrue(msgs[1]["citations"])

    def test_no_hit_fixed_text_no_model_call(self):
        s = self.login("student_a1", "stu123")
        cid = self._new_conv(s)
        before = len(_StubHandler.chat_calls)
        resp = self.client.post(f"/api/conversations/{cid}/messages",
                                json={"content": "今天天气怎么样"},
                                headers=self.bearer(s))
        events = _parse_sse(resp.get_data(as_text=True))
        answer = "".join(e["text"] for e in events if e["type"] == "delta")
        self.assertEqual(answer, "资料中未找到相关内容")
        cits = next(e["citations"] for e in events if e["type"] == "citations")
        self.assertEqual(cits, [])
        self.assertEqual(len(_StubHandler.chat_calls), before, "无命中时不得调用生成模型")

    def test_prompt_and_skill_injected(self):
        t = self.login("teacher_a", "teach123")
        self.client.put("/api/prompt", json={"content": "注入标记PROMPT123"},
                        headers=self.bearer(t))
        skills = self.client.get("/api/skills", headers=self.bearer(t)).get_json()["skills"]
        seed = next(s0 for s0 in skills if s0["name"] == "解题引导")
        original_instructions = seed["instructions"]
        self.client.patch(f"/api/skills/{seed['id']}",
                          json={"enabled": True, "instructions": "注入标记SKILL456"},
                          headers=self.bearer(t))

        s = self.login("student_a1", "stu123")
        cid = self._new_conv(s)
        self.client.post(f"/api/conversations/{cid}/messages",
                         json={"content": "生字词 课文导读"}, headers=self.bearer(s))
        sent_system = _StubHandler.chat_calls[-1][0]["content"]
        self.assertIn("注入标记PROMPT123", sent_system)
        self.assertIn("注入标记SKILL456", sent_system)
        self.assertIn("[1]", sent_system)  # 编号资料
        # 还原：停用技能、恢复指令与提示词，避免影响其他用例
        self.client.patch(f"/api/skills/{seed['id']}",
                          json={"enabled": False, "instructions": original_instructions},
                          headers=self.bearer(t))
        self.client.put("/api/prompt", json={"content": "默认"}, headers=self.bearer(t))

    def test_conversation_ownership(self):
        s = self.login("student_a1", "stu123")
        cid = self._new_conv(s)
        t = self.login("teacher_a", "teach123")
        self.assertEqual(self.client.get(
            f"/api/conversations/{cid}/messages", headers=self.bearer(t)).status_code, 403)
        self.assertEqual(self.client.post(
            f"/api/conversations/{cid}/messages", json={"content": "hi"},
            headers=self.bearer(t)).status_code, 403)
        # 自己的列表仅含本人会话
        convs = self.client.get("/api/conversations",
                                headers=self.bearer(s)).get_json()["conversations"]
        self.assertTrue(any(c["id"] == cid for c in convs))

    def test_empty_message_400(self):
        s = self.login("student_a1", "stu123")
        cid = self._new_conv(s)
        resp = self.client.post(f"/api/conversations/{cid}/messages",
                                json={"content": "  "}, headers=self.bearer(s))
        self.assertEqual(resp.status_code, 400)


class OpenApiDocTest(Lesson5Base):
    def test_openapi_json_valid_and_covers(self):
        resp = self.client.get("/openapi.json")
        self.assertEqual(resp.status_code, 200)
        doc = json.loads(resp.get_data(as_text=True))
        self.assertTrue(doc["openapi"].startswith("3."))
        paths = doc["paths"]
        for p in ("/api/login", "/api/search", "/api/ask", "/api/prompt",
                  "/api/skills", "/api/conversations",
                  "/api/conversations/{conv_id}/messages"):
            self.assertIn(p, paths, p)
        self.assertIn("bearerAuth", doc["components"]["securitySchemes"])
        self.assertIn("cookieAuth", doc["components"]["securitySchemes"])
        # 受保护接口声明了 security
        get_prompt = paths["/api/prompt"]["get"]
        self.assertTrue(get_prompt.get("security"))

    def test_swagger_page_offline(self):
        resp = self.client.get("/swagger")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn("swagger-ui", html)
        # 引用的是本地 vendor，不是 CDN
        self.assertIn("/static/vendor/swagger-ui/", html)
        self.assertNotIn("cdn.", html)
        # vendor 资源真实可取
        for f in ("swagger-ui.css", "swagger-ui-bundle.js"):
            r = self.client.get(f"/static/vendor/swagger-ui/{f}")
            self.assertEqual(r.status_code, 200, f)


if __name__ == "__main__":
    unittest.main(verbosity=2)

"""GET /api/search：教师上传 → 关键字检索命中 → 命中内容与数据库切片一致。"""

MARKER = "接口测试专用词组甲乙丙"
TITLE = "接口测试材料"


def run(ctx):
    teacher = ctx.client()
    code, _ = teacher.login("teacher_a", "teach123")
    ctx.check("教师登录", code == 200, f"实际 {code}")

    # 准备：上传一份含独特词组的材料（ multipart，标题中文经 UTF-8 编码）
    content = f"# 接口测试\n{MARKER}：这是一段用于接口测试的正文，描述接口测试的步骤与断言方法。"
    code, _, _ = teacher.request(
        "POST", "/materials/upload",
        form={"title": TITLE},
        files={"file": ("apitest.md", content.encode("utf-8"), "text/markdown")})
    ctx.check("上传材料成功（302 或 200）", code in (200, 302), f"实际 {code}")

    mat = ctx.db("SELECT id, title FROM materials WHERE title = ?", (TITLE,))
    ctx.check("数据库 materials 有该记录", bool(mat))
    if not mat:
        return
    chunks = ctx.db(
        "SELECT chunk_text FROM knowledge_chunks WHERE material_id = ? "
        "AND index_status = 'ready'", (mat[0][0],))
    ctx.check("切片已入库且 ready", bool(chunks),
              "嵌入/向量库可用时应为 ready")

    import urllib.parse
    code, body = teacher.json(
        "GET", f"/api/search?q={urllib.parse.quote(MARKER)}&mode=keyword")
    ctx.check("检索返回 200", code == 200, f"实际 {code}")
    hits = (body or {}).get("hits", [])
    ctx.check("命中列表非空", bool(hits))
    if hits:
        h = hits[0]
        ctx.check("命中标题与库一致", h["material_title"] == TITLE)
        ctx.check("命中含出处字段（切片序号/字符区间/摘录）",
                  all(k in h for k in ("chunk_index", "start_offset", "end_offset", "excerpt")))
        if chunks:
            ctx.check("摘录取自数据库切片正文",
                      h["excerpt"].rstrip("…") in chunks[0][0])

import json
import sqlite3

from flask import current_app

RETRIEVAL_SCHEMA = """
CREATE TABLE IF NOT EXISTS knowledge_chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    knowledge_entry_id INTEGER NOT NULL REFERENCES knowledge_entries(id),
    material_id INTEGER NOT NULL REFERENCES materials(id),
    class_id INTEGER NOT NULL REFERENCES classes(id),
    chunk_index INTEGER NOT NULL,
    chunk_text TEXT NOT NULL,
    start_offset INTEGER NOT NULL,
    end_offset INTEGER NOT NULL,
    strategy TEXT NOT NULL DEFAULT 'auto',
    index_status TEXT NOT NULL DEFAULT 'pending' CHECK (index_status IN ('pending', 'ready', 'failed')),
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_chunks_entry ON knowledge_chunks(knowledge_entry_id);
CREATE INDEX IF NOT EXISTS idx_chunks_class ON knowledge_chunks(class_id, index_status);
"""

FTS_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_chunks_fts
USING fts5(chunk_text, tokenize='trigram');
"""

ASSISTANT_SCHEMA = """
CREATE TABLE IF NOT EXISTS class_prompts (
    class_id INTEGER PRIMARY KEY REFERENCES classes(id),
    content TEXT NOT NULL,
    updated_by INTEGER REFERENCES users(id),
    updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    class_id INTEGER NOT NULL REFERENCES classes(id),
    user_id INTEGER NOT NULL REFERENCES users(id),
    title TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL REFERENCES conversations(id),
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    citations TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id, id);
"""

# skills 表（第 3 课占位）扩展列：简介、完整指令、启用开关 + 第 6 课：适用条件/工具白名单/来源
SKILL_COLUMNS = {
    "description": "TEXT NOT NULL DEFAULT ''",
    "instructions": "TEXT NOT NULL DEFAULT ''",
    "enabled": "INTEGER NOT NULL DEFAULT 0",
    "updated_at": "TEXT NOT NULL DEFAULT ''",
    "applicable": "TEXT NOT NULL DEFAULT ''",
    "tools": "TEXT NOT NULL DEFAULT 'knowledge_search'",
    "source": "TEXT NOT NULL DEFAULT 'manual'",
}

PLATFORM_SCHEMA = """
CREATE TABLE IF NOT EXISTS prompt_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    class_id INTEGER NOT NULL REFERENCES classes(id),
    name TEXT NOT NULL,
    content TEXT NOT NULL,
    built_in INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE TABLE IF NOT EXISTS ai_apps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    class_id INTEGER NOT NULL REFERENCES classes(id),
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    template_id INTEGER REFERENCES prompt_templates(id),
    skill_ids TEXT NOT NULL DEFAULT '[]',
    material_ids TEXT NOT NULL DEFAULT '[]',
    built_in INTEGER NOT NULL DEFAULT 0,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE TABLE IF NOT EXISTS llm_call_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    class_id INTEGER NOT NULL REFERENCES classes(id),
    user_id INTEGER REFERENCES users(id),
    conversation_id INTEGER REFERENCES conversations(id),
    app_id INTEGER REFERENCES ai_apps(id),
    source TEXT NOT NULL DEFAULT 'conversation',
    model TEXT NOT NULL DEFAULT '',
    request_json TEXT NOT NULL,
    response_text TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'ok' CHECK (status IN ('ok', 'error')),
    error TEXT NOT NULL DEFAULT '',
    template_name TEXT NOT NULL DEFAULT '',
    skill_names TEXT NOT NULL DEFAULT '[]',
    tool_calls TEXT,
    kb_total_chunks INTEGER NOT NULL DEFAULT 0,
    kb_total_chars INTEGER NOT NULL DEFAULT 0,
    kb_passed_chunks INTEGER NOT NULL DEFAULT 0,
    kb_passed_chars INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_logs_class ON llm_call_logs(class_id, id);
"""

MCP_SCHEMA = """
CREATE TABLE IF NOT EXISTS mcp_servers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    class_id INTEGER NOT NULL REFERENCES classes(id),
    name TEXT NOT NULL,
    base_url TEXT NOT NULL,
    auth_token TEXT NOT NULL DEFAULT '',
    connected INTEGER NOT NULL DEFAULT 0 CHECK (connected IN (0, 1)),
    connected_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    UNIQUE(class_id, name)
);
CREATE TABLE IF NOT EXISTS mcp_tools (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    server_id INTEGER NOT NULL REFERENCES mcp_servers(id) ON DELETE CASCADE,
    tool_name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    schema_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(server_id, tool_name)
);
CREATE TABLE IF NOT EXISTS mcp_tool_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    class_id INTEGER NOT NULL REFERENCES classes(id),
    server_id INTEGER REFERENCES mcp_servers(id),
    tool_ref TEXT NOT NULL,
    user_id INTEGER REFERENCES users(id),
    conversation_id INTEGER REFERENCES conversations(id),
    status TEXT NOT NULL CHECK (status IN ('ok', 'denied', 'error')),
    detail TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
"""


def get_conn():
    conn = sqlite3.connect(current_app.config["DATABASE"])
    conn.row_factory = sqlite3.Row
    return conn


def ensure_retrieval_schema(db_path):
    """启动迁移：既有库补齐切片表与 FTS5 虚表（幂等）。"""
    conn = sqlite3.connect(db_path)
    try:
        with conn:
            conn.executescript(RETRIEVAL_SCHEMA)
            conn.executescript(FTS_SCHEMA)
    finally:
        conn.close()


def ensure_assistant_schema(db_path):
    """启动迁移：提示词/会话/消息表 + skills 扩展列（幂等）。"""
    conn = sqlite3.connect(db_path)
    try:
        with conn:
            conn.executescript(ASSISTANT_SCHEMA)
            existing = {r[1] for r in conn.execute("PRAGMA table_info(skills)")}
            for col, decl in SKILL_COLUMNS.items():
                if col not in existing:
                    conn.execute(f"ALTER TABLE skills ADD COLUMN {col} {decl}")
    finally:
        conn.close()


def ensure_platform_schema(db_path):
    """启动迁移：应用/模板/调用日志/MCP 表 + conversations.app_id 列（幂等）。"""
    conn = sqlite3.connect(db_path)
    try:
        with conn:
            conn.executescript(PLATFORM_SCHEMA)
            conn.executescript(MCP_SCHEMA)
            existing = {r[1] for r in conn.execute("PRAGMA table_info(conversations)")}
            if "app_id" not in existing:
                conn.execute("ALTER TABLE conversations ADD COLUMN app_id INTEGER")
    finally:
        conn.close()


def find_user_by_username(username):
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
    finally:
        conn.close()


def list_materials(class_id):
    """材料列表：强制按会话班级过滤，不接受客户端传入的 class_id。"""
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT id, title, filename, created_at FROM materials "
            "WHERE class_id = ? ORDER BY id DESC",
            (class_id,),
        ).fetchall()
    finally:
        conn.close()


def get_material(material_id):
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT * FROM materials WHERE id = ?", (material_id,)
        ).fetchone()
    finally:
        conn.close()


def get_knowledge_body(material_id):
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT body_text FROM knowledge_entries WHERE material_id = ? "
            "ORDER BY id LIMIT 1",
            (material_id,),
        ).fetchone()
        return row["body_text"] if row else None
    finally:
        conn.close()


def insert_material_with_knowledge(class_id, title, filename, file_path, uploaded_by, body_text):
    """落盘解析成功后，同事务写入 materials 与 knowledge_entries。"""
    conn = get_conn()
    try:
        with conn:
            cur = conn.execute(
                "INSERT INTO materials (title, class_id, filename, file_path, uploaded_by) "
                "VALUES (?, ?, ?, ?, ?)",
                (title, class_id, filename, file_path, uploaded_by),
            )
            material_id = cur.lastrowid
            conn.execute(
                "INSERT INTO knowledge_entries (material_id, class_id, body_text) "
                "VALUES (?, ?, ?)",
                (material_id, class_id, body_text),
            )
        return material_id
    finally:
        conn.close()


# ---- 第 4 课：切片与索引 ----


def get_entry_for_material(material_id):
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT * FROM knowledge_entries WHERE material_id = ? ORDER BY id LIMIT 1",
            (material_id,),
        ).fetchone()
    finally:
        conn.close()


def entries_without_chunks():
    """已入库但尚无切片的条目（启动时按 auto 补齐索引用）。"""
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT e.* FROM knowledge_entries e "
            "WHERE NOT EXISTS ("
            "  SELECT 1 FROM knowledge_chunks c WHERE c.knowledge_entry_id = e.id"
            ")"
        ).fetchall()
    finally:
        conn.close()


def replace_chunks(entry_id, chunks, strategy):
    """先删旧切片（含 FTS 行）再写新记录，单事务。返回新切片 id 列表。"""
    conn = get_conn()
    try:
        with conn:
            old_ids = [
                r[0] for r in conn.execute(
                    "SELECT id FROM knowledge_chunks WHERE knowledge_entry_id = ?",
                    (entry_id,),
                ).fetchall()
            ]
            if old_ids:
                conn.execute(
                    f"DELETE FROM knowledge_chunks WHERE knowledge_entry_id = ?", (entry_id,)
                )
                conn.executemany(
                    "DELETE FROM knowledge_chunks_fts WHERE rowid = ?",
                    [(i,) for i in old_ids],
                )
            new_ids = []
            for ch in chunks:
                cur = conn.execute(
                    "INSERT INTO knowledge_chunks (knowledge_entry_id, material_id, class_id, "
                    "chunk_index, chunk_text, start_offset, end_offset, strategy, index_status) "
                    "SELECT ?, material_id, class_id, ?, ?, ?, ?, ?, 'pending' "
                    "FROM knowledge_entries WHERE id = ?",
                    (entry_id, ch["chunk_index"], ch["chunk_text"],
                     ch["start_offset"], ch["end_offset"], strategy, entry_id),
                )
                chunk_id = cur.lastrowid
                conn.execute(
                    "INSERT INTO knowledge_chunks_fts (rowid, chunk_text) VALUES (?, ?)",
                    (chunk_id, ch["chunk_text"]),
                )
                new_ids.append(chunk_id)
        return new_ids, old_ids
    finally:
        conn.close()


def mark_chunks(entry_id, chunk_ids, status):
    conn = get_conn()
    try:
        with conn:
            conn.executemany(
                "UPDATE knowledge_chunks SET index_status = ? WHERE id = ?",
                [(status, i) for i in chunk_ids],
            )
    finally:
        conn.close()


def list_chunks(entry_id):
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT * FROM knowledge_chunks WHERE knowledge_entry_id = ? "
            "ORDER BY chunk_index",
            (entry_id,),
        ).fetchall()
    finally:
        conn.close()


def keyword_search(class_id, fts_query, limit=20):
    """关键字检索：仅查本班 ready 切片的 FTS5 索引，按 bm25 相关度升序（越小越相关）。"""
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT c.id AS chunk_id, c.chunk_index, c.chunk_text, c.start_offset, "
            "       c.end_offset, c.material_id, m.title AS material_title, "
            "       bm25(knowledge_chunks_fts) AS kw_score "
            "FROM knowledge_chunks_fts f "
            "JOIN knowledge_chunks c ON c.id = f.rowid "
            "JOIN materials m ON m.id = c.material_id "
            "WHERE knowledge_chunks_fts MATCH ? "
            "  AND c.class_id = ? AND c.index_status = 'ready' "
            "ORDER BY kw_score ASC LIMIT ?",
            (fts_query, class_id, limit),
        ).fetchall()
    finally:
        conn.close()


def like_search(class_id, term, limit=20):
    """短词（<3 字符）兜底：trigram 无法索引，用 LIKE 子串匹配，按出现次数排序。"""
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT c.id AS chunk_id, c.chunk_index, c.chunk_text, c.start_offset, "
            "       c.end_offset, c.material_id, m.title AS material_title, "
            "       (length(c.chunk_text) - length(replace(c.chunk_text, ?, ''))) "
            "       / max(length(?), 1) AS hits "
            "FROM knowledge_chunks c "
            "JOIN materials m ON m.id = c.material_id "
            "WHERE c.class_id = ? AND c.index_status = 'ready' "
            "  AND c.chunk_text LIKE '%' || ? || '%' ESCAPE '\\' "
            "ORDER BY hits DESC LIMIT ?",
            (term, term, class_id, escaped, limit),
        ).fetchall()
    finally:
        conn.close()


def fetch_chunks_by_ids(class_id, chunk_ids):
    """回表取正文：强制同一会话班级 + ready，向量主键不得单独作为正文来源。"""
    if not chunk_ids:
        return []
    placeholders = ",".join("?" for _ in chunk_ids)
    conn = get_conn()
    try:
        return conn.execute(
            f"SELECT c.id AS chunk_id, c.chunk_index, c.chunk_text, c.start_offset, "
            f"       c.end_offset, c.material_id, m.title AS material_title "
            f"FROM knowledge_chunks c "
            f"JOIN materials m ON m.id = c.material_id "
            f"WHERE c.id IN ({placeholders}) "
            f"  AND c.class_id = ? AND c.index_status = 'ready'",
            (*chunk_ids, class_id),
        ).fetchall()
    finally:
        conn.close()



# ---- 第 5 课：提示词 / 技能 / 会话 ----


def get_prompt(class_id):
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM class_prompts WHERE class_id = ?", (class_id,)
        ).fetchone()
        return row["content"] if row else ""
    finally:
        conn.close()


def upsert_prompt(class_id, content, updated_by):
    conn = get_conn()
    try:
        with conn:
            conn.execute(
                "INSERT INTO class_prompts (class_id, content, updated_by, updated_at) "
                "VALUES (?, ?, ?, datetime('now', 'localtime')) "
                "ON CONFLICT(class_id) DO UPDATE SET content = excluded.content, "
                "updated_by = excluded.updated_by, updated_at = excluded.updated_at",
                (class_id, content, updated_by),
            )
    finally:
        conn.close()


def list_skills(class_id):
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT * FROM skills WHERE class_id = ? ORDER BY id", (class_id,)
        ).fetchall()
    finally:
        conn.close()


def get_skill(skill_id):
    conn = get_conn()
    try:
        return conn.execute("SELECT * FROM skills WHERE id = ?", (skill_id,)).fetchone()
    finally:
        conn.close()


def create_skill(class_id, name, description, instructions,
                 applicable="", tools="knowledge_search", source="manual"):
    conn = get_conn()
    try:
        with conn:
            cur = conn.execute(
                "INSERT INTO skills (class_id, name, description, instructions, enabled, "
                "updated_at, applicable, tools, source) "
                "VALUES (?, ?, ?, ?, 0, datetime('now', 'localtime'), ?, ?, ?)",
                (class_id, name, description, instructions, applicable, tools, source),
            )
            return cur.lastrowid
    finally:
        conn.close()


def update_skill(skill_id, **fields):
    allowed = {"name", "description", "instructions", "enabled",
               "applicable", "tools", "source"}
    sets = {k: v for k, v in fields.items() if k in allowed}
    if not sets:
        return
    clause = ", ".join(f"{k} = ?" for k in sets)
    conn = get_conn()
    try:
        with conn:
            conn.execute(
                f"UPDATE skills SET {clause}, "
                f"updated_at = datetime('now', 'localtime') WHERE id = ?",
                (*sets.values(), skill_id),
            )
    finally:
        conn.close()


def enabled_skills(class_id):
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT * FROM skills WHERE class_id = ? AND enabled = 1 ORDER BY id",
            (class_id,),
        ).fetchall()
    finally:
        conn.close()


def create_conversation(class_id, user_id, title, app_id=None):
    conn = get_conn()
    try:
        with conn:
            cur = conn.execute(
                "INSERT INTO conversations (class_id, user_id, title, app_id) "
                "VALUES (?, ?, ?, ?)", (class_id, user_id, title, app_id),
            )
            return cur.lastrowid
    finally:
        conn.close()


def list_conversations(user_id):
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT * FROM conversations WHERE user_id = ? ORDER BY id DESC", (user_id,)
        ).fetchall()
    finally:
        conn.close()


def get_conversation(conv_id):
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT * FROM conversations WHERE id = ?", (conv_id,)
        ).fetchone()
    finally:
        conn.close()


def add_message(conversation_id, role, content, citations=None):
    import json
    conn = get_conn()
    try:
        with conn:
            cur = conn.execute(
                "INSERT INTO messages (conversation_id, role, content, citations) "
                "VALUES (?, ?, ?, ?)",
                (conversation_id, role, content,
                 json.dumps(citations, ensure_ascii=False) if citations is not None else None),
            )
            return cur.lastrowid
    finally:
        conn.close()


def list_messages(conversation_id):
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT * FROM messages WHERE conversation_id = ? ORDER BY id",
            (conversation_id,),
        ).fetchall()
    finally:
        conn.close()


def recent_messages(conversation_id, limit=6):
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT role, content FROM messages WHERE conversation_id = ? "
            "ORDER BY id DESC LIMIT ?",
            (conversation_id, limit),
        ).fetchall()
        return list(reversed(rows))
    finally:
        conn.close()


SEED_SKILL = {
    "name": "解题引导",
    "description": "引导学生一步步解题：给思路、引用本班材料的标题与位置，不直接给出最终答案",
    "instructions": (
        "你是解题引导助手。规则：1) 不直接给出最终答案或完整解答；"
        "2) 先指出题目考查的知识点，再给出一到两个引导性问题，让学生自己推导；"
        "3) 若回答依据来自本班材料，注明材料标题与切片位置（用 [编号] 标注）；"
        "4) 学生要求直接给答案时，仍只给下一步提示，并鼓励其先尝试。"
    ),
}


def seed_assistant_defaults(db_path):
    """既有库补齐默认技能：每个班至少一条「解题引导」（幂等）。"""
    conn = sqlite3.connect(db_path)
    try:
        with conn:
            for (cid,) in conn.execute("SELECT id FROM classes").fetchall():
                row = conn.execute(
                    "SELECT 1 FROM skills WHERE class_id = ? AND name = ? AND instructions != ''",
                    (cid, SEED_SKILL["name"]),
                ).fetchone()
                if row is None:
                    conn.execute(
                        "INSERT INTO skills (class_id, name, description, instructions, "
                        "enabled, updated_at, applicable, tools, source) "
                        "VALUES (?, ?, ?, ?, 0, datetime('now', 'localtime'), "
                        "'', 'knowledge_search', 'built_in')",
                        (cid, SEED_SKILL["name"], SEED_SKILL["description"],
                         SEED_SKILL["instructions"]),
                    )
    finally:
        conn.close()


# ---- 第 6 课平台化：模板 / 应用 / 调用日志 / MCP ----

SEED_TEMPLATES = [
    {
        "name": "默认教研模板",
        "content": (
            "你是本班的教研助手，回答须简短、准确、面向中小学教学场景。\n"
            "{{skills}}\n{{knowledge}}"
        ),
    },
    {
        "name": "解题引导模板",
        "content": (
            "你是本班的解题引导老师，语气温和有耐心。\n"
            "要求：一次只指出下一步该检查什么，不代替学生完成整道题。\n"
            "{{skills}}\n{{knowledge}}"
        ),
    },
    {
        "name": "作文点评模板",
        "content": (
            "你是本班的语文作文点评助手。\n"
            "要求：先肯定优点，再按「选材 / 结构 / 语言」三条各给一条具体修改建议。\n"
            "{{skills}}\n{{knowledge}}"
        ),
    },
]

SEED_SKILLS_EXTRA = [
    {
        "name": "概念讲解",
        "description": "面向中小学生的概念讲解：先定义，再举一个本班材料里的例子",
        "instructions": (
            "你是概念讲解助手。规则：1) 先用一句话给出概念定义；"
            "2) 再从本班材料中举一个具体例子（用 [编号] 标注出处）；"
            "3) 最后用一个生活化的类比帮助理解；4) 讲解不超过 200 字。"
        ),
        "applicable": "概念,定义,什么意思,是什么,解释",
        "tools": "knowledge_search",
    },
    {
        "name": "作文点评",
        "description": "点评学生作文：先优点后建议，按选材/结构/语言三条展开",
        "instructions": (
            "你是作文点评助手。规则：1) 先肯定作文最突出的一条优点；"
            "2) 再从选材、结构、语言三个角度各给一条具体可操作的修改建议；"
            "3) 引用本班材料中的范文或写作方法时用 [编号] 标注出处；"
            "4) 语气鼓励，不直接替学生改写全文。"
        ),
        "applicable": "作文,点评,写作,范文,修改",
        "tools": "knowledge_search",
    },
]

SEED_APPS = [
    {
        "name": "资料问答助手",
        "description": "基于本班材料的问答：先检索再回答，回答带出处标注",
        "template": "默认教研模板",
        "skills": [],
        "materials": [],
    },
    {
        "name": "解题引导助手",
        "description": "只引导思路不给答案的解题助手，引用本班材料出处",
        "template": "解题引导模板",
        "skills": ["解题引导"],
        "materials": [],
    },
    {
        "name": "作文点评助手",
        "description": "按选材/结构/语言三条点评作文，可引用范文",
        "template": "作文点评模板",
        "skills": ["作文点评"],
        "materials": [],
    },
]


def seed_platform_defaults(db_path):
    """既有库补齐内置模板、技能与应用（幂等，按名称判重）。"""
    conn = sqlite3.connect(db_path)
    try:
        with conn:
            for (cid,) in conn.execute("SELECT id FROM classes").fetchall():
                for tpl in SEED_TEMPLATES:
                    row = conn.execute(
                        "SELECT 1 FROM prompt_templates WHERE class_id = ? AND name = ?",
                        (cid, tpl["name"]),
                    ).fetchone()
                    if row is None:
                        conn.execute(
                            "INSERT INTO prompt_templates (class_id, name, content, built_in) "
                            "VALUES (?, ?, ?, 1)", (cid, tpl["name"], tpl["content"]),
                        )
                for skill in SEED_SKILLS_EXTRA:
                    row = conn.execute(
                        "SELECT 1 FROM skills WHERE class_id = ? AND name = ? "
                        "AND instructions != ''", (cid, skill["name"]),
                    ).fetchone()
                    if row is None:
                        conn.execute(
                            "INSERT INTO skills (class_id, name, description, instructions, "
                            "enabled, updated_at, applicable, tools, source) "
                            "VALUES (?, ?, ?, ?, 0, datetime('now', 'localtime'), ?, ?, 'built_in')",
                            (cid, skill["name"], skill["description"],
                             skill["instructions"], skill["applicable"], skill["tools"]),
                        )
                for app in SEED_APPS:
                    row = conn.execute(
                        "SELECT 1 FROM ai_apps WHERE class_id = ? AND name = ?",
                        (cid, app["name"]),
                    ).fetchone()
                    if row is not None:
                        continue
                    tpl_id = conn.execute(
                        "SELECT id FROM prompt_templates WHERE class_id = ? AND name = ?",
                        (cid, app["template"]),
                    ).fetchone()
                    skill_ids = [
                        r[0] for name in app["skills"] for r in conn.execute(
                            "SELECT id FROM skills WHERE class_id = ? AND name = ?",
                            (cid, name),
                        ).fetchall()
                    ]
                    conn.execute(
                        "INSERT INTO ai_apps (class_id, name, description, template_id, "
                        "skill_ids, material_ids, built_in, enabled) "
                        "VALUES (?, ?, ?, ?, ?, '[]', 1, 1)",
                        (cid, app["name"], app["description"],
                         tpl_id[0] if tpl_id else None,
                         json.dumps(skill_ids)),
                    )
    finally:
        conn.close()


# ---- 提示词模板 ----


def list_templates(class_id):
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT * FROM prompt_templates WHERE class_id = ? ORDER BY id", (class_id,)
        ).fetchall()
    finally:
        conn.close()


def get_template(template_id):
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT * FROM prompt_templates WHERE id = ?", (template_id,)
        ).fetchone()
    finally:
        conn.close()


def create_template(class_id, name, content, built_in=0):
    conn = get_conn()
    try:
        with conn:
            cur = conn.execute(
                "INSERT INTO prompt_templates (class_id, name, content, built_in) "
                "VALUES (?, ?, ?, ?)", (class_id, name, content, built_in),
            )
            return cur.lastrowid
    finally:
        conn.close()


def update_template(template_id, **fields):
    allowed = {"name", "content"}
    sets = {k: v for k, v in fields.items() if k in allowed}
    if not sets:
        return
    clause = ", ".join(f"{k} = ?" for k in sets)
    conn = get_conn()
    try:
        with conn:
            conn.execute(
                f"UPDATE prompt_templates SET {clause}, "
                f"updated_at = datetime('now', 'localtime') WHERE id = ?",
                (*sets.values(), template_id),
            )
    finally:
        conn.close()


def delete_template(template_id):
    conn = get_conn()
    try:
        with conn:
            conn.execute(
                "UPDATE ai_apps SET template_id = NULL WHERE template_id = ?",
                (template_id,),
            )
            conn.execute("DELETE FROM prompt_templates WHERE id = ?", (template_id,))
    finally:
        conn.close()


# ---- AI 应用 ----


def list_apps(class_id):
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT * FROM ai_apps WHERE class_id = ? ORDER BY id", (class_id,)
        ).fetchall()
    finally:
        conn.close()


def get_app(app_id):
    conn = get_conn()
    try:
        return conn.execute("SELECT * FROM ai_apps WHERE id = ?", (app_id,)).fetchone()
    finally:
        conn.close()


def create_app_row(class_id, name, description, template_id, skill_ids, material_ids,
                   built_in=0, enabled=1):
    conn = get_conn()
    try:
        with conn:
            cur = conn.execute(
                "INSERT INTO ai_apps (class_id, name, description, template_id, "
                "skill_ids, material_ids, built_in, enabled) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (class_id, name, description, template_id,
                 json.dumps(skill_ids), json.dumps(material_ids), built_in, enabled),
            )
            return cur.lastrowid
    finally:
        conn.close()


def update_app_row(app_id, **fields):
    allowed = {"name", "description", "template_id", "enabled"}
    sets = {k: v for k, v in fields.items() if k in allowed}
    if "skill_ids" in fields:
        sets["skill_ids"] = json.dumps(fields["skill_ids"])
    if "material_ids" in fields:
        sets["material_ids"] = json.dumps(fields["material_ids"])
    if not sets:
        return
    clause = ", ".join(f"{k} = ?" for k in sets)
    conn = get_conn()
    try:
        with conn:
            conn.execute(
                f"UPDATE ai_apps SET {clause}, "
                f"updated_at = datetime('now', 'localtime') WHERE id = ?",
                (*sets.values(), app_id),
            )
    finally:
        conn.close()


def delete_app_row(app_id):
    conn = get_conn()
    try:
        with conn:
            conn.execute("UPDATE conversations SET app_id = NULL WHERE app_id = ?", (app_id,))
            conn.execute("DELETE FROM ai_apps WHERE id = ?", (app_id,))
    finally:
        conn.close()


# ---- LLM 调用日志 ----


def insert_llm_log(**fields):
    conn = get_conn()
    try:
        with conn:
            cols = ", ".join(fields.keys())
            marks = ", ".join("?" for _ in fields)
            cur = conn.execute(
                f"INSERT INTO llm_call_logs ({cols}) VALUES ({marks})",
                tuple(fields.values()),
            )
            return cur.lastrowid
    finally:
        conn.close()


def list_llm_logs(class_id, limit=50):
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT id, source, model, status, template_name, app_id, conversation_id, "
            "       kb_total_chunks, kb_total_chars, kb_passed_chunks, kb_passed_chars, "
            "       created_at "
            "FROM llm_call_logs WHERE class_id = ? ORDER BY id DESC LIMIT ?",
            (class_id, limit),
        ).fetchall()
    finally:
        conn.close()


def get_llm_log(log_id, class_id):
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT * FROM llm_call_logs WHERE id = ? AND class_id = ?",
            (log_id, class_id),
        ).fetchone()
    finally:
        conn.close()


# ---- 知识库统计（验证 2：全库 vs 实际传入） ----


def kb_stats(class_id, material_ids=None):
    """本班（或指定材料子集）ready 切片总量与字符总量。"""
    conn = get_conn()
    try:
        if material_ids:
            marks = ",".join("?" for _ in material_ids)
            row = conn.execute(
                f"SELECT COUNT(*) AS n, COALESCE(SUM(LENGTH(chunk_text)), 0) AS chars "
                f"FROM knowledge_chunks WHERE class_id = ? AND index_status = 'ready' "
                f"AND material_id IN ({marks})", (class_id, *material_ids),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT COUNT(*) AS n, COALESCE(SUM(LENGTH(chunk_text)), 0) AS chars "
                "FROM knowledge_chunks WHERE class_id = ? AND index_status = 'ready'",
                (class_id,),
            ).fetchone()
        return {"total_chunks": row["n"], "total_chars": row["chars"]}
    finally:
        conn.close()


# ---- MCP：服务器 / 工具缓存 / 审计 ----


def list_mcp_servers(class_id):
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT * FROM mcp_servers WHERE class_id = ? ORDER BY id", (class_id,)
        ).fetchall()
    finally:
        conn.close()


def get_mcp_server(server_id, class_id=None):
    conn = get_conn()
    try:
        if class_id is None:
            return conn.execute(
                "SELECT * FROM mcp_servers WHERE id = ?", (server_id,)
            ).fetchone()
        return conn.execute(
            "SELECT * FROM mcp_servers WHERE id = ? AND class_id = ?",
            (server_id, class_id),
        ).fetchone()
    finally:
        conn.close()


def get_mcp_server_by_name(class_id, name):
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT * FROM mcp_servers WHERE class_id = ? AND name = ?", (class_id, name)
        ).fetchone()
    finally:
        conn.close()


def create_mcp_server(class_id, name, base_url, auth_token):
    conn = get_conn()
    try:
        with conn:
            cur = conn.execute(
                "INSERT INTO mcp_servers (class_id, name, base_url, auth_token) "
                "VALUES (?, ?, ?, ?)", (class_id, name, base_url, auth_token),
            )
            return cur.lastrowid
    finally:
        conn.close()


def update_mcp_server(server_id, **fields):
    allowed = {"name", "base_url", "auth_token"}
    sets = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not sets:
        return
    clause = ", ".join(f"{k} = ?" for k in sets)
    conn = get_conn()
    try:
        with conn:
            conn.execute(
                f"UPDATE mcp_servers SET {clause} WHERE id = ?", (*sets.values(), server_id)
            )
    finally:
        conn.close()


def delete_mcp_server(server_id):
    """删除服务器：缓存级联删除；审计行保留证据，server_id 置空、tool_ref 保留。"""
    conn = get_conn()
    try:
        with conn:
            conn.execute(
                "UPDATE mcp_tool_calls SET server_id = NULL WHERE server_id = ?",
                (server_id,),
            )
            conn.execute("DELETE FROM mcp_tools WHERE server_id = ?", (server_id,))
            conn.execute("DELETE FROM mcp_servers WHERE id = ?", (server_id,))
    finally:
        conn.close()


def set_mcp_connected(server_id, connected):
    conn = get_conn()
    try:
        with conn:
            conn.execute(
                "UPDATE mcp_servers SET connected = ?, connected_at = CASE WHEN ? = 1 "
                "THEN datetime('now', 'localtime') ELSE NULL END WHERE id = ?",
                (connected, connected, server_id),
            )
    finally:
        conn.close()


def replace_mcp_tools(server_id, tools):
    """覆盖写工具缓存：事务内先删旧再插新。tools: [{name, description, inputSchema}]。"""
    import json as _json
    conn = get_conn()
    try:
        with conn:
            conn.execute("DELETE FROM mcp_tools WHERE server_id = ?", (server_id,))
            for t in tools:
                conn.execute(
                    "INSERT INTO mcp_tools (server_id, tool_name, description, schema_json) "
                    "VALUES (?, ?, ?, ?)",
                    (server_id, t["name"], t.get("description", ""),
                     _json.dumps(t.get("inputSchema", {}), ensure_ascii=False)),
                )
    finally:
        conn.close()


def list_mcp_tools(server_id):
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT id, tool_name, description, schema_json FROM mcp_tools "
            "WHERE server_id = ? ORDER BY id", (server_id,),
        ).fetchall()
    finally:
        conn.close()


def list_mcp_tool_calls(class_id, limit=50):
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT c.id, c.tool_ref, c.status, c.detail, c.created_at, "
            "       s.name AS server_name, u.username, c.conversation_id "
            "FROM mcp_tool_calls c "
            "LEFT JOIN mcp_servers s ON s.id = c.server_id "
            "LEFT JOIN users u ON u.id = c.user_id "
            "WHERE c.class_id = ? ORDER BY c.id DESC LIMIT ?", (class_id, limit),
        ).fetchall()
    finally:
        conn.close()


def insert_mcp_tool_call(class_id, server_id, tool_ref, user_id, conversation_id,
                         status, detail):
    conn = get_conn()
    try:
        with conn:
            conn.execute(
                "INSERT INTO mcp_tool_calls (class_id, server_id, tool_ref, user_id, "
                "conversation_id, status, detail) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (class_id, server_id, tool_ref, user_id, conversation_id, status, detail),
            )
    finally:
        conn.close()

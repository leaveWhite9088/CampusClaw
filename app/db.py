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


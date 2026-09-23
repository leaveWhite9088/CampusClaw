import sqlite3

from flask import current_app


def get_conn():
    conn = sqlite3.connect(current_app.config["DATABASE"])
    conn.row_factory = sqlite3.Row
    return conn


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

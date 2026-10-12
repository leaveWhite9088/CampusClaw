"""建表 + 种子数据：班级 A/B、教师 A、学生 A1/B1、两班可区分标题的材料。"""

import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from werkzeug.security import generate_password_hash

from app.db import (
    ASSISTANT_SCHEMA, FTS_SCHEMA, RETRIEVAL_SCHEMA, SKILL_COLUMNS,
)

SKILL_SEED = {
    "name": "解题引导",
    "description": "引导学生一步步解题：给思路、引用本班材料的标题与位置，不直接给出最终答案",
    "instructions": (
        "你是解题引导助手。规则：1) 不直接给出最终答案或完整解答；"
        "2) 先指出题目考查的知识点，再给出一到两个引导性问题，让学生自己推导；"
        "3) 若回答依据来自本班材料，注明材料标题与切片位置（用 [编号] 标注）；"
        "4) 学生要求直接给答案时，仍只给下一步提示，并鼓励其先尝试。"
    ),
}

DB_PATH = os.environ.get(
    "DATABASE", os.path.join(os.path.dirname(__file__), "..", "data", "app.db")
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS classes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('teacher', 'student')),
    class_id INTEGER NOT NULL REFERENCES classes(id)
);
CREATE TABLE IF NOT EXISTS lectures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    class_id INTEGER NOT NULL REFERENCES classes(id),
    title TEXT
);
CREATE TABLE IF NOT EXISTS assignments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    class_id INTEGER NOT NULL REFERENCES classes(id),
    title TEXT
);
CREATE TABLE IF NOT EXISTS assistants (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    class_id INTEGER NOT NULL REFERENCES classes(id),
    name TEXT
);
CREATE TABLE IF NOT EXISTS skills (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    class_id INTEGER NOT NULL REFERENCES classes(id),
    name TEXT
);
CREATE TABLE IF NOT EXISTS materials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    class_id INTEGER NOT NULL REFERENCES classes(id),
    filename TEXT,
    file_path TEXT,
    uploaded_by INTEGER REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE TABLE IF NOT EXISTS knowledge_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    material_id INTEGER NOT NULL REFERENCES materials(id),
    class_id INTEGER NOT NULL REFERENCES classes(id),
    body_text TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
"""

SEED_PASSWORDS = {
    "teacher_a": "teach123",
    "student_a1": "stu123",
    "student_b1": "stu123",
}


def main():
    os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    try:
        with conn:
            conn.executescript(SCHEMA)
            conn.executescript(RETRIEVAL_SCHEMA)
            conn.executescript(FTS_SCHEMA)
            conn.executescript(ASSISTANT_SCHEMA)
            # skills 扩展列（与启动迁移同一组规则，保证新库列齐全）
            existing = {r[1] for r in conn.execute("PRAGMA table_info(skills)")}
            for col, decl in SKILL_COLUMNS.items():
                if col not in existing:
                    conn.execute(f"ALTER TABLE skills ADD COLUMN {col} {decl}")

            if conn.execute("SELECT COUNT(*) FROM classes").fetchone()[0]:
                print("数据库已初始化，跳过种子。")
                return

            cur = conn.execute("INSERT INTO classes (name) VALUES ('班级 A')")
            class_a = cur.lastrowid
            cur = conn.execute("INSERT INTO classes (name) VALUES ('班级 B')")
            class_b = cur.lastrowid

            def add_user(username, role, class_id):
                cur = conn.execute(
                    "INSERT INTO users (username, password_hash, role, class_id) "
                    "VALUES (?, ?, ?, ?)",
                    (username, generate_password_hash(SEED_PASSWORDS[username]), role, class_id),
                )
                return cur.lastrowid

            teacher_a = add_user("teacher_a", "teacher", class_a)
            add_user("student_a1", "student", class_a)
            add_user("student_b1", "student", class_b)

            def add_material(title, class_id, filename, body):
                cur = conn.execute(
                    "INSERT INTO materials (title, class_id, filename, file_path, uploaded_by) "
                    "VALUES (?, ?, ?, NULL, ?)",
                    (title, class_id, filename, teacher_a),
                )
                conn.execute(
                    "INSERT INTO knowledge_entries (material_id, class_id, body_text) "
                    "VALUES (?, ?, ?)",
                    (cur.lastrowid, class_id, body),
                )

            add_material("A 班·语文第一单元讲义", class_a, "a_chinese_unit1.md",
                         "A 班语文第一单元：生字词与课文导读。")
            add_material("B 班·数学第一章习题课", class_b, "b_math_ch1.md",
                         "B 班数学第一章：集合与常用逻辑用语。")

            # 六类核心结构的占位行（讲义/作业/助手本 change 不验收业务功能）
            conn.execute("INSERT INTO lectures (class_id, title) VALUES (?, '占位讲义')", (class_a,))
            conn.execute("INSERT INTO assignments (class_id, title) VALUES (?, '占位作业')", (class_a,))
            conn.execute("INSERT INTO assistants (class_id, name) VALUES (?, '占位助手')", (class_a,))
            # 第 5 课：两班各种子一条「解题引导」技能（默认停用，教师上课时启用）
            for cid in (class_a, class_b):
                conn.execute(
                    "INSERT INTO skills (class_id, name, description, instructions, enabled, "
                    "updated_at) VALUES (?, ?, ?, ?, 0, datetime('now', 'localtime'))",
                    (cid, SKILL_SEED["name"], SKILL_SEED["description"],
                     SKILL_SEED["instructions"]),
                )

        print(f"初始化完成：{DB_PATH}")
        print("预置账号：teacher_a / teach123（教师·A 班），student_a1 / stu123，student_b1 / stu123")
    finally:
        conn.close()


if __name__ == "__main__":
    main()

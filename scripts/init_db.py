"""建表 + 种子数据：班级 A/B、教师 A、学生 A1/B1、两班可区分标题的材料。"""

import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from werkzeug.security import generate_password_hash

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

            # 六类核心结构的占位行（讲义/作业/助手/技能本 change 不验收业务功能）
            conn.execute("INSERT INTO lectures (class_id, title) VALUES (?, '占位讲义')", (class_a,))
            conn.execute("INSERT INTO assignments (class_id, title) VALUES (?, '占位作业')", (class_a,))
            conn.execute("INSERT INTO assistants (class_id, name) VALUES (?, '占位助手')", (class_a,))
            conn.execute("INSERT INTO skills (class_id, name) VALUES (?, '占位技能')", (class_a,))

        print(f"初始化完成：{DB_PATH}")
        print("预置账号：teacher_a / teach123（教师·A 班），student_a1 / stu123，student_b1 / stu123")
    finally:
        conn.close()


if __name__ == "__main__":
    main()

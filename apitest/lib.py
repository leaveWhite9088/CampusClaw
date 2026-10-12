"""apitest 公共库：HTTP 客户端（Cookie + Bearer）、multipart 编码、DB 断言、SSE 解析。"""

import base64
import http.cookiejar
import json
import sqlite3
import urllib.error
import urllib.request
import uuid


def encode_multipart(fields, files):
    """fields: {k: v}；files: {name: (filename, bytes, content_type)}"""
    boundary = "----apitest" + uuid.uuid4().hex
    body = b""
    for k, v in fields.items():
        body += (f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n'
                 f'{v}\r\n').encode("utf-8")
    for name, (filename, content, ctype) in files.items():
        body += (f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; '
                 f'filename="{filename}"\r\nContent-Type: {ctype}\r\n\r\n').encode("utf-8")
        body += content + b"\r\n"
    body += f"--{boundary}--\r\n".encode("utf-8")
    return body, f"multipart/form-data; boundary={boundary}"


class Client:
    """带 Cookie 罐与可选 Bearer 令牌的最小 HTTP 客户端。"""

    def __init__(self, base_url):
        self.base = base_url.rstrip("/")
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar))
        self.token = None

    def request(self, method, path, json_body=None, form=None, files=None,
                headers=None, timeout=60):
        url = self.base + path
        hdrs = dict(headers or {})
        data = None
        if json_body is not None:
            data = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
            hdrs["Content-Type"] = "application/json; charset=utf-8"
        elif form is not None or files is not None:
            data, hdrs["Content-Type"] = encode_multipart(form or {}, files or {})
        if self.token:
            hdrs["Authorization"] = "Bearer " + self.token
        req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
        try:
            resp = self.opener.open(req, timeout=timeout)
            return resp.status, resp.read(), resp.headers
        except urllib.error.HTTPError as e:
            return e.code, e.read(), e.headers

    def json(self, method, path, **kw):
        code, body, _ = self.request(method, path, **kw)
        try:
            return code, json.loads(body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return code, None

    def login(self, username, password, use_bearer=True):
        code, body = self.json("POST", "/api/login",
                               json_body={"username": username, "password": password})
        if code == 200 and use_bearer:
            self.token = body["access_token"]
        return code, body


def jwt_payload(token):
    part = token.split(".")[1]
    part += "=" * (-len(part) % 4)
    return json.loads(base64.urlsafe_b64decode(part))


def db_rows(db_path, sql, params=()):
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def parse_sse(body):
    """解析 text/event-stream 响应体为事件列表。"""
    text = body.decode("utf-8") if isinstance(body, bytes) else body
    return [json.loads(line[6:]) for line in text.split("\n\n")
            if line.strip().startswith("data: ")]


class Ctx:
    """用例上下文：base_url / db_path / 结果收集。"""

    def __init__(self, base_url, db_path):
        self.base_url = base_url
        self.db_path = db_path
        self.checks = []  # (desc, ok, detail)

    def client(self):
        return Client(self.base_url)

    def check(self, desc, cond, detail=""):
        self.checks.append((desc, bool(cond), detail))
        return bool(cond)

    def db(self, sql, params=()):
        return db_rows(self.db_path, sql, params)

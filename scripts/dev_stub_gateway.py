"""开发/演示用 stub 网关：无真实密钥时替代嵌入与对话网关。

仅供本地开发与演示，不参与生产部署。用法：
    python scripts/dev_stub_gateway.py [端口]   # 默认 9700
然后在 .env 中配置：
    EMBEDDING_API_BASE=http://host.docker.internal:9700   # Compose 内 app 访问宿主机
    EMBEDDING_API_KEY=dev-stub
    EMBEDDING_MODEL=stub-embed
    CHAT_API_BASE=http://host.docker.internal:9700
    CHAT_API_KEY=dev-stub
    CHAT_MODEL=stub-chat
本地开发（非 Compose）则用 http://localhost:9700。

对话接口为抽取式 stub：从服务端传入的编号资料中找出与问题
字面重叠最多的句子作为回答，并按资料编号追加 [i] 出处标注。
"""

import json
import re
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

_REF_RE = re.compile(r"\[(\d+)\] 材料《(.+?)》第 (\d+) 节：\n(.*?)(?=\n\n\[\d+\] 材料《|\Z)", re.S)
_SENT_SPLIT = re.compile(r"(?<=[。！？!?；;])|\n+")


def _embed(text, dim=1024):
    vec = [0.0] * dim
    grams = set()
    for n in (1, 2, 3):
        for i in range(max(len(text) - n + 1, 1)):
            grams.add(text[i:i + n])
    for g in grams:
        vec[hash(g) % dim] += 1.0
    norm = sum(v * v for v in vec) ** 0.5 or 1.0
    return [v / norm for v in vec]


def _bigrams(text):
    return {text[i:i + 2] for i in range(len(text) - 1)}


def _extractive_answer(messages):
    """从 system 消息的编号资料中抽取与问题最相关的句子。"""
    system = next((m["content"] for m in messages if m["role"] == "system"), "")
    question = next((m["content"] for m in reversed(messages)
                     if m["role"] == "user"), "")
    refs = _REF_RE.search(system) and list(_REF_RE.finditer(system)) or []
    if not refs or not question:
        return "资料中未找到相关内容。"

    q_grams = _bigrams(question)
    best = None  # (score, ref_no, sentence)
    for m in refs:
        ref_no, chunk = m.group(1), m.group(4)
        for sent in _SENT_SPLIT.split(chunk):
            sent = sent.strip()
            if len(sent) < 4:
                continue
            score = len(q_grams & _bigrams(sent))
            if best is None or score > best[0]:
                best = (score, ref_no, sent)
    if not best or best[0] == 0:
        return "资料中未找到相关内容。"
    return f"{best[2]}[{best[1]}]"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path == "/embeddings":
            data = [{"index": i, "embedding": _embed(t)}
                    for i, t in enumerate(body["input"])]
            self._send({"data": data})
        elif self.path == "/chat/completions":
            self._send({"choices": [{"message": {"role": "assistant",
                                                 "content": _extractive_answer(body["messages"])}}]})
        else:
            self._send({"error": "not found"}, 404)

    def _send(self, obj, code=200):
        raw = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 9700
    print(f"stub 网关监听 http://0.0.0.0:{port} （/embeddings, /chat/completions）")
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()

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
"""

import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer


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
            refs = sum(1 for m in body["messages"] if m["role"] == "system")
            self._send({"choices": [{"message": {"role": "assistant", "content":
                f"[stub] 已依据服务端提供的 {refs} 组资料作答，出处标注 [1]。"}}]})
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

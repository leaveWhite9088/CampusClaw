"""嵌入网关：仅在服务端调用 OpenAI 兼容 /embeddings 接口，密钥不出服务端。"""

import json
import os
import urllib.error
import urllib.request


class EmbeddingError(RuntimeError):
    pass


def _config():
    base = os.environ.get("EMBEDDING_API_BASE", "").rstrip("/")
    key = os.environ.get("EMBEDDING_API_KEY", "")
    model = os.environ.get("EMBEDDING_MODEL", "")
    return base, key, model


def available():
    base, key, model = _config()
    return bool(base and key and model)


def embed_texts(texts, timeout=30):
    """将若干文本转换为向量；网关未配置或调用失败时抛 EmbeddingError。"""
    base, key, model = _config()
    if not (base and key and model):
        raise EmbeddingError("嵌入网关未配置（EMBEDDING_API_BASE/KEY/MODEL）")

    req = urllib.request.Request(
        f"{base}/embeddings",
        data=json.dumps({"model": model, "input": texts}).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as e:
        raise EmbeddingError(f"嵌入网关调用失败: {e}") from e

    try:
        data = sorted(payload["data"], key=lambda d: d["index"])
        vectors = [d["embedding"] for d in data]
    except (KeyError, TypeError) as e:
        raise EmbeddingError(f"嵌入网关响应格式异常: {e}") from e
    if len(vectors) != len(texts):
        raise EmbeddingError("嵌入网关返回向量数量与输入不符")
    return vectors

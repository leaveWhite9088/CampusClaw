"""Qdrant 向量库客户端（REST，标准库实现）。

向量库仅存向量与标识：向量主键 = knowledge_chunks.id = payload.chunk_id；
payload 不含正文。服务仅 Compose 内部网络可达，不对宿主机/浏览器暴露。
"""

import json
import os
import urllib.error
import urllib.request

COLLECTION = "campusclaw_chunks"
DISTANCE = "Cosine"


class VectorStoreError(RuntimeError):
    pass


def _base():
    return (os.environ.get("QDRANT_URL") or "http://localhost:6333").rstrip("/")


def _request(method, path, body=None, timeout=10):
    req = urllib.request.Request(
        f"{_base()}{path}",
        data=json.dumps(body).encode("utf-8") if body is not None else None,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise
        raise VectorStoreError(f"Qdrant {method} {path} 失败: HTTP {e.code}") from e
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as e:
        raise VectorStoreError(f"Qdrant 不可达: {e}") from e


def available():
    try:
        _request("GET", "/collections", timeout=3)
        return True
    except (VectorStoreError, urllib.error.HTTPError):
        return False


def ensure_collection(dim):
    """collection 不存在时按所给维度创建（余弦度量）。"""
    try:
        _request("GET", f"/collections/{COLLECTION}")
        return
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise VectorStoreError(str(e)) from e
    except VectorStoreError:
        raise
    _request("PUT", f"/collections/{COLLECTION}", {
        "vectors": {"size": dim, "distance": DISTANCE},
    })


def upsert(points):
    """points: [{'id': int, 'vector': [...], 'payload': {...}}]"""
    if not points:
        return
    _request("PUT", f"/collections/{COLLECTION}/points?wait=true", {
        "points": points,
    })


def search(vector, class_id, limit=20):
    """按 class_id 过滤的余弦检索，返回 [{'id', 'score', 'payload'}]。"""
    result = _request("POST", f"/collections/{COLLECTION}/points/search", {
        "vector": vector,
        "limit": limit,
        "with_payload": True,
        "filter": {
            "must": [{"key": "class_id", "match": {"value": class_id}}],
        },
    })
    return result.get("result", [])


def delete(point_ids):
    if not point_ids:
        return
    _request("POST", f"/collections/{COLLECTION}/points/delete?wait=true", {
        "points": point_ids,
    })

"""对话网关：仅在检索命中切片后调用；system 提示由服务端写入。

输入由检索模块组装：材料标题、切片序号、切片正文与用户最新提问。
不向其传递向量分量、Qdrant 原始点数据或其他班级切片。
"""

import json
import os
import urllib.error
import urllib.request

SYSTEM_PROMPT = (
    "你是教研助手。仅依据下列编号资料回答用户问题，回答须简短；"
    "引用资料时在句末以 [编号] 标注出处，编号与资料列表一致；"
    "资料中没有依据时不要作答，直接说明资料中未找到相关内容。"
)


class ChatError(RuntimeError):
    pass


def available():
    base = os.environ.get("CHAT_API_BASE", "").rstrip("/")
    return bool(base and os.environ.get("CHAT_API_KEY") and os.environ.get("CHAT_MODEL"))


def generate_answer(question, hits, history=None, timeout=60):
    """依据命中切片生成带 [1]/[2] 标注的简短回答；失败抛 ChatError。"""
    base = os.environ.get("CHAT_API_BASE", "").rstrip("/")
    key = os.environ.get("CHAT_API_KEY", "")
    model = os.environ.get("CHAT_MODEL", "")
    if not (base and key and model):
        raise ChatError("对话网关未配置（CHAT_API_BASE/KEY/MODEL）")

    refs = "\n\n".join(
        f"[{i + 1}] 材料《{h['material_title']}》第 {h['chunk_index']} 节：\n{h['chunk_text']}"
        for i, h in enumerate(hits)
    )
    messages = [{"role": "system", "content": f"{SYSTEM_PROMPT}\n\n{refs}"}]
    for msg in (history or [])[-6:]:
        # 客户端注入的 system 消息一律丢弃
        if msg.get("role") in ("user", "assistant") and msg.get("content"):
            messages.append({"role": msg["role"], "content": str(msg["content"])})
    messages.append({"role": "user", "content": question})

    req = urllib.request.Request(
        f"{base}/chat/completions",
        data=json.dumps({
            "model": model,
            "messages": messages,
            "stream": False,
        }).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        return payload["choices"][0]["message"]["content"]
    except (OSError, urllib.error.URLError, json.JSONDecodeError, KeyError, IndexError) as e:
        raise ChatError(f"对话网关调用失败: {e}") from e

"""MCP 客户端（JSON-RPC 2.0 over HTTP）与对话中的确定性工具调用。

调用时机与参数由代码决定（技能工具白名单 → 逐个 tools/call，参数只含提问原文），
不由模型决定；返回先过安全校验，再作为数据拼进用户消息；每次调用写审计。
"""

import json
import re
import urllib.error
import urllib.request

TIMEOUT = 10
MAX_TOOL_TEXT = 1200

# 指令式句式：命中即整条丢弃（挡住最直白的载荷；主力防线是「数据只进用户消息」这一位置边界）
_INJECTION_RE = re.compile(
    r"忽略前述|忽略之前|无视前述|ignore previous|disregard (all )?(previous|above)"
    r"|你现在是|你不再是你|system\s*:", re.I)


class McpError(RuntimeError):
    """MCP 调用失败（网络/HTTP/协议层），message 面向教师可读。"""


def _endpoint(base_url):
    base = (base_url or "").rstrip("/")
    return base + ("" if base.endswith("/mcp") else "/mcp")


def json_rpc(base_url, method, params, token, timeout=TIMEOUT, req_id=1):
    """发送一条 JSON-RPC 2.0 请求，返回 result；失败抛 McpError。"""
    body = json.dumps({"jsonrpc": "2.0", "id": req_id,
                       "method": method, "params": params or {}}).encode("utf-8")
    req = urllib.request.Request(
        _endpoint(base_url), data=body, method="POST",
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {token or ''}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise McpError("鉴权失败：令牌缺失或错误（401）") from e
        raise McpError(f"MCP 服务返回 HTTP {e.code}") from e
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as e:
        raise McpError(f"MCP 服务不可达或响应异常: {e}") from e

    if not isinstance(payload, dict) or payload.get("jsonrpc") != "2.0":
        raise McpError("MCP 响应不是合法的 JSON-RPC 2.0 报文")
    if "error" in payload:
        err = payload["error"]
        raise McpError(f"MCP 错误 {err.get('code')}: {err.get('message')}")
    if "result" not in payload:
        raise McpError("MCP 响应缺少 result")
    return payload["result"]


def sanitize_tool_text(text):
    """工具返回安全校验：命中指令式句式或超长正文 → 整条丢弃（返回 None）。"""
    text = (text or "").strip()
    if not text:
        return None
    if len(text) > MAX_TOOL_TEXT:
        return None
    if _INJECTION_RE.search(text):
        return None
    return text


def _tool_text(result):
    """从 tools/call 的 result 里取文本正文；工具自报错误按失败处理。"""
    if result.get("isError"):
        return None
    parts = []
    for item in result.get("content") or []:
        if isinstance(item, dict) and item.get("type") == "text":
            parts.append(str(item.get("text", "")))
    return "\n".join(parts).strip() or None


def run_skill_tools(class_id, user_id, conversation_id, skills, question):
    """按技能工具白名单逐个调用 MCP 工具（跳过 knowledge_search）。

    返回 (tool_calls_meta, data_blocks)：
      tool_calls_meta: [{ref, status, text(仅 ok 时前 200 字)}]
      data_blocks: 通过安全校验的文本块，调用方拼进用户消息。
    服务器不存在 → denied 且不写审计；未连接 → denied 写审计；调用失败 → error 写审计。
    """
    from . import db

    meta, blocks = [], []
    seen = set()
    for skill in skills:
        for ref in (skill["tools"] or "").split(","):
            ref = ref.strip()
            if not ref or ref == "knowledge_search" or ref in seen:
                continue
            seen.add(ref)
            tool_name, server_name = ref.split("@", 1)
            server = db.get_mcp_server_by_name(class_id, server_name)
            if server is None:
                meta.append({"ref": ref, "status": "denied", "text": ""})
                continue
            if not server["connected"]:
                db.insert_mcp_tool_call(class_id, server["id"], ref, user_id,
                                        conversation_id, "denied", "服务器未连接")
                meta.append({"ref": ref, "status": "denied", "text": ""})
                continue
            try:
                result = json_rpc(server["base_url"], "tools/call",
                                  {"name": tool_name, "arguments": {"query": question}},
                                  server["auth_token"])
                text = _tool_text(result)
                if text is None:
                    raise McpError("工具自报错误或返回空内容")
                clean = sanitize_tool_text(text)
                detail = text[:200]
                if clean is None:
                    meta.append({"ref": ref, "status": "error",
                                 "text": "返回未通过安全校验，已丢弃"})
                    db.insert_mcp_tool_call(class_id, server["id"], ref, user_id,
                                            conversation_id, "error",
                                            "返回未通过安全校验，已丢弃")
                    continue
                blocks.append(f"[工具 {ref} 返回的数据]\n{clean}")
                meta.append({"ref": ref, "status": "ok", "text": clean[:200]})
                db.insert_mcp_tool_call(class_id, server["id"], ref, user_id,
                                        conversation_id, "ok", detail)
            except McpError as e:
                meta.append({"ref": ref, "status": "error", "text": ""})
                db.insert_mcp_tool_call(class_id, server["id"], ref, user_id,
                                        conversation_id, "error", str(e)[:500])
    return meta, blocks

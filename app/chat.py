"""对话网关：仅在检索命中切片后调用；system 提示由服务端写入。

一次调用的输入由服务端组装：应用绑定的提示词模板（渲染技能与资料占位符）、
选中技能的完整指令、编号资料切片与用户最新提问（+ 工具返回数据块）。
每次调用完整留痕 llm_call_logs（请求 JSON、返回内容、知识库/技能注入统计），
作为验收取证依据；不向其传递向量分量、Qdrant 原始点数据或其他班级切片。
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

DEFAULT_TEMPLATE = "你是本班的教研助手，回答须简短、准确、面向中小学教学场景。"


class ChatError(RuntimeError):
    pass


def available():
    base = os.environ.get("CHAT_API_BASE", "").rstrip("/")
    return bool(base and os.environ.get("CHAT_API_KEY") and os.environ.get("CHAT_MODEL"))


def render_system(template_content, skills_block="", refs_block=""):
    """模板渲染：{{skills}}/{{knowledge}} 占位替换，缺占位符时按「技能→资料」追加；末尾固定边界句。"""
    text = (template_content or "").strip() or DEFAULT_TEMPLATE
    has_skills_slot = "{{skills}}" in text
    has_knowledge_slot = "{{knowledge}}" in text
    out = text.replace("{{skills}}", skills_block).replace("{{knowledge}}", refs_block)
    tail = []
    if not has_skills_slot and skills_block:
        tail.append(skills_block)
    if not has_knowledge_slot and refs_block:
        tail.append(refs_block)
    if tail:
        out = out.rstrip() + "\n\n" + "\n\n".join(tail)
    return out.rstrip() + "\n\n" + SYSTEM_PROMPT


def _write_log(context, request_body, response_text, status, error=""):
    from .db import insert_llm_log

    try:
        insert_llm_log(
            class_id=context["class_id"],
            user_id=context.get("user_id"),
            conversation_id=context.get("conversation_id"),
            app_id=context.get("app_id"),
            source=context.get("source", "conversation"),
            model=request_body.get("model", ""),
            request_json=json.dumps(request_body, ensure_ascii=False),
            response_text=response_text or "",
            status=status,
            error=error or "",
            template_name=context.get("template_name", ""),
            skill_names=json.dumps(context.get("skill_names", []), ensure_ascii=False),
            tool_calls=(json.dumps(context["tool_calls"], ensure_ascii=False)
                        if context.get("tool_calls") else None),
            kb_total_chunks=int(context.get("kb_total_chunks", 0)),
            kb_total_chars=int(context.get("kb_total_chars", 0)),
            kb_passed_chunks=int(context.get("kb_passed_chunks", 0)),
            kb_passed_chars=int(context.get("kb_passed_chars", 0)),
        )
    except Exception:
        pass  # 日志失败不阻塞回答主路径


def generate_answer(question, hits, history=None, timeout=60,
                    template_content="", skills=None, log_context=None,
                    extra_user_blocks=None):
    """依据命中切片生成带 [1]/[2] 标注的简短回答；失败抛 ChatError。

    skills: 选中技能行列表（dict，含 name/instructions）——完整指令全部注入 system。
    extra_user_blocks: 工具返回等外部数据块列表，作为数据拼进用户消息（不进 system）。
    log_context 提供时，本次调用的完整请求/返回写入 llm_call_logs。
    """
    base = os.environ.get("CHAT_API_BASE", "").rstrip("/")
    key = os.environ.get("CHAT_API_KEY", "")
    model = os.environ.get("CHAT_MODEL", "")
    if not (base and key and model):
        raise ChatError("对话网关未配置（CHAT_API_BASE/KEY/MODEL）")

    refs = "\n\n".join(
        f"[{i + 1}] 材料《{h['material_title']}》第 {h['chunk_index']} 节：\n{h['chunk_text']}"
        for i, h in enumerate(hits)
    )
    skills_block = "\n\n".join(
        f"技能「{s['name']}」：{s['instructions']}" for s in (skills or [])
    )
    system = render_system(template_content, skills_block, refs)
    messages = [{"role": "system", "content": system}]
    for msg in (history or [])[-6:]:
        # 历史可能来自库（sqlite3.Row）或客户端 JSON（dict）；客户端注入的 system 一律丢弃
        if isinstance(msg, dict):
            role, content = msg.get("role"), msg.get("content")
        else:
            role, content = msg["role"], msg["content"]
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": str(content)})
    user_content = question
    if extra_user_blocks:
        user_content = question + "\n\n" + "\n\n".join(extra_user_blocks)
    messages.append({"role": "user", "content": user_content})

    request_body = {"model": model, "messages": messages, "stream": False}
    req = urllib.request.Request(
        f"{base}/chat/completions",
        data=json.dumps(request_body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        answer = payload["choices"][0]["message"]["content"]
    except (OSError, urllib.error.URLError, json.JSONDecodeError, KeyError, IndexError) as e:
        if log_context:
            _write_log(log_context, request_body, "", "error", f"对话网关调用失败: {e}")
        raise ChatError(f"对话网关调用失败: {e}") from e
    if log_context:
        _write_log(log_context, request_body, answer, "ok")
    return answer

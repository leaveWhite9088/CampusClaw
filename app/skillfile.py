"""技能文件解析与工具引用校验（课程技能文件格式 / JSON）。

文件格式（.md/.txt）：头部逐行 `键：值`（支持全角/半角冒号），空行后其余为指令正文：
    名称：数学解题引导
    适用条件：方程,去括号
    工具：knowledge_search, formula_hint@campus-tools
    启用：是

    正文（空行以下全部作为完整指令）。
JSON 格式：{"name": 必填, "description", "instructions": 必填, "applicable", "tools", "enabled"}。
"""

import json
import re

BUILTIN_TOOLS = {"knowledge_search"}

# 工具名：小写字母开头，仅小写字母/数字/下划线；服务器名：另允许连字符
_REF_RE = re.compile(r"^([a-z][a-z0-9_]{0,31})@([a-z][a-z0-9_-]{0,31})$")
_SEPARATORS = re.compile(r"[,，、;；|]")
_KV_RE = re.compile(r"^\s*([^:：]{1,12})[:：]\s*(.*)$")

TOOL_REF_HINT = (
    "工具栏写法：多项用逗号分隔；每项为 knowledge_search 或 工具名@服务器名"
    "（如 formula_hint@campus-tools；工具名小写字母开头，可含数字下划线；"
    "服务器名另可含连字符）"
)


class SkillFileError(ValueError):
    pass


def parse_tool_refs(tools_text):
    """切分并校验工具引用格式；返回引用列表。格式错误抛 SkillFileError。"""
    refs = []
    for raw in _SEPARATORS.split(tools_text or ""):
        item = raw.strip()
        if not item:
            continue
        if item in BUILTIN_TOOLS:
            refs.append(item)
            continue
        if not _REF_RE.match(item):
            raise SkillFileError(f"工具引用格式非法：「{item}」。{TOOL_REF_HINT}")
        refs.append(item)
    return refs


def validate_tool_refs(class_id, refs):
    """保存前校验 MCP 引用可达性：服务器存在、已连接、工具已发现。

    返回错误信息字符串或 None；跨班/不存在/未连接均按同一口径提示，不泄露存在性。
    """
    from . import db

    for ref in refs:
        if ref in BUILTIN_TOOLS:
            continue
        tool_name, server_name = ref.split("@", 1)
        server = db.get_mcp_server_by_name(class_id, server_name)
        if server is None or not server["connected"]:
            return f"工具「{ref}」不可用：服务器「{server_name}」未登记或未连接"
        cached = {t["tool_name"] for t in db.list_mcp_tools(server["id"])}
        if tool_name not in cached:
            return (f"工具「{tool_name}」不在服务器「{server_name}」的发现清单里，"
                    f"可用工具：{('、'.join(sorted(cached))) or '（空）'}")
    return None


def parse_skill_text(filename, text):
    """解析技能文件内容；失败抛 SkillFileError。返回字段 dict。"""
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    if (filename or "").lower().endswith(".json"):
        return _parse_skill_json(text)
    return _parse_skill_md(text)


def _parse_skill_md(text):
    lines = text.split("\n")
    fields = {}
    body_start = len(lines)
    for i, line in enumerate(lines):
        if not line.strip():
            body_start = i + 1
            break
        m = _KV_RE.match(line)
        if not m:
            body_start = i  # 首个非「键：值」行起算正文（无头部文件）
            break
        fields[m.group(1).strip()] = m.group(2).strip()
    else:
        body_start = len(lines)
    instructions = "\n".join(lines[body_start:]).strip()
    name = fields.pop("名称", "").strip()
    if not name:
        raise SkillFileError("技能文件缺少「名称：」行")
    if not instructions:
        raise SkillFileError("技能文件缺少指令正文（头部空行之后应写完整指令）")
    enabled_raw = fields.pop("启用", "").strip().lower()
    enabled = enabled_raw in ("是", "yes", "true", "1", "启用")
    applicable = fields.pop("适用条件", "").strip()
    description = fields.pop("简介", "") or fields.pop("描述", "") or ""
    tools_text = fields.pop("工具", "").strip() or "knowledge_search"
    fields.pop("资料", None)  # 允许出现，本系统不做资料过滤键
    try:
        tools = parse_tool_refs(tools_text)
    except SkillFileError as e:
        raise SkillFileError(f"技能「{name}」{e}") from e
    return {
        "name": name[:64],
        "description": description.strip()[:200],
        "instructions": instructions,
        "applicable": applicable[:200],
        "tools": tools,
        "enabled": enabled,
        "source": "uploaded",
    }


def _parse_skill_json(text):
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise SkillFileError(f"JSON 解析失败：{e}") from e
    if not isinstance(data, dict):
        raise SkillFileError("JSON 技能文件应为对象")
    name = str(data.get("name") or "").strip()
    instructions = str(data.get("instructions") or "").strip()
    if not name:
        raise SkillFileError("JSON 技能文件缺少 name 字段")
    if not instructions:
        raise SkillFileError("JSON 技能文件缺少 instructions 字段")
    tools_raw = data.get("tools") or "knowledge_search"
    tools_text = (",".join(tools_raw) if isinstance(tools_raw, list)
                  else str(tools_raw))
    try:
        tools = parse_tool_refs(tools_text)
    except SkillFileError as e:
        raise SkillFileError(f"技能「{name}」{e}") from e
    applicable_raw = data.get("applicable")
    applicable = (",".join(applicable_raw) if isinstance(applicable_raw, list)
                  else str(applicable_raw or "")).strip()
    return {
        "name": name[:64],
        "description": str(data.get("description") or "").strip()[:200],
        "instructions": instructions,
        "applicable": applicable[:200],
        "tools": tools,
        "enabled": bool(data.get("enabled")),
        "source": "uploaded",
    }


def select_skills(skills, question):
    """按适用条件选中技能：无适用条件的关键词时始终选中；有关键词则提问命中任一才选中。"""
    selected = []
    for s in skills:
        applicable = (s["applicable"] or "").strip()
        if not applicable:
            selected.append(s)
            continue
        keywords = [k.strip() for k in _SEPARATORS.split(applicable) if k.strip()]
        if any(k in question for k in keywords):
            selected.append(s)
    return selected

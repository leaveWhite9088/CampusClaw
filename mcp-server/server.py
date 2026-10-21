#!/usr/bin/env python3
"""CampusClaw 自建 MCP 工具服务（教学演示）：JSON-RPC 2.0 over HTTP。

提供 POST /mcp（initialize / tools/list / tools/call）与 GET /health；
Bearer 令牌从环境变量 MCP_AUTH_TOKEN 读取，令牌缺失或错误返回 401。
仅暴露工具（tools）一类能力；仅供本地开发与课程演示，不参与生产部署。

用法：
    MCP_AUTH_TOKEN=xxx python server.py [端口]   # 默认 8090
"""

import json
import os
import re
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "campus-tools", "version": "1.0.0"}

UNITS = {
    # 单位 → (基准量纲, 相对基准的倍数, 别名)
    "米": ("length", 1.0), "m": ("length", 1.0), "米m": ("length", 1.0),
    "厘米": ("length", 0.01), "cm": ("length", 0.01),
    "毫米": ("length", 0.001), "mm": ("length", 0.001),
    "千米": ("length", 1000.0), "公里": ("length", 1000.0), "km": ("length", 1000.0),
    "分米": ("length", 0.1), "dm": ("length", 0.1),
    "千克": ("mass", 1.0), "公斤": ("mass", 1.0), "kg": ("mass", 1.0),
    "克": ("mass", 0.001), "g": ("mass", 0.001),
    "吨": ("mass", 1000.0), "t": ("mass", 1000.0),
    "秒": ("time", 1.0), "s": ("time", 1.0),
    "分": ("time", 60.0), "分钟": ("time", 60.0), "min": ("time", 60.0),
    "时": ("time", 3600.0), "小时": ("time", 3600.0), "h": ("time", 3600.0),
}

CONCEPTS = {
    "分数": "把单位「1」平均分成若干份，表示这样的一份或几份的数叫分数。横线下是分母（平均分的份数），横线上是分子（取了几份）。",
    "方程": "含有未知数的等式叫方程。解方程就是求出使等式成立的未知数的值；依据是等式的两边同时加减乘除同一个数，等式仍然成立。",
    "面积": "物体的表面或围成的平面图形的大小，叫作它们的面积。常用单位：平方米、平方分米、平方厘米；相邻单位间进率是 100。",
    "周长": "环绕有限面积的区域边缘的长度积分，叫作周长，也就是图形一周的长度。长方形周长 =（长 + 宽）× 2。",
    "质数": "大于 1 的自然数中，除了 1 和它本身外不能再被其他自然数整除的数叫质数（素数），如 2、3、5、7、11。1 既不是质数也不是合数。",
    "去括号": "去括号法则：括号前是「+」号，去括号后括号内各项不变号；括号前是「−」号，去括号后括号内每一项都要变号。",
    "通分": "把异分母分数分别化成和原来分数相等的同分母分数，叫作通分。通分时用原来几个分母的最小公倍数作公分母。",
    "勾股定理": "直角三角形两直角边 a、b 的平方和等于斜边 c 的平方：a² + b² = c²。",
}

FORMULAS = [
    (("去括号",), "去括号时：括号前的系数要乘到括号内每一项，符号不要漏变；括号前是减号时，去掉括号后里面每一项都要变号。"),
    (("通分", "异分母"), "通分步骤：1) 求出各分母的最小公倍数作公分母；2) 用公分母除以原分母，再乘原分子得到新分子；3) 再按同分母分数加减。"),
    (("方程", "解方程", "未知数"), "解方程的依据是等式的性质：两边同时加减同一个数、或乘除同一个非零数，等式仍成立。移项要变号。"),
    (("面积",), "长方形面积 = 长 × 宽；正方形面积 = 边长 × 边长；三角形面积 = 底 × 高 ÷ 2。单位别忘平方。"),
    (("周长",), "长方形周长 =（长 + 宽）× 2；正方形周长 = 边长 × 4。"),
    (("勾股", "直角三角形"), "勾股定理：直角三角形中 a² + b² = c²，c 为斜边。已知两边可求第三边。"),
    (("分数加", "分数减"), "同分母分数加减：分母不变，分子相加减；异分母先通分再加减。结果要化成最简分数。"),
    (("应用题", "行程"), "行程问题基本公式：路程 = 速度 × 时间。相遇问题：路程和 = 速度和 × 时间。"),
]


def _norm_unit(token):
    token = token.strip().lower()
    return UNITS.get(token) or UNITS.get(token.replace(" ", ""))


def formula_hint(query):
    q = (query or "").strip()
    hits = [text for keys, text in FORMULAS if any(k in q for k in keys)]
    if not hits:
        return ("这里先不直接给答案。提示：先判断题目考查的知识点（数与代数 / 图形与几何 / "
                "应用题），写出已知条件与要求的量，再想想用哪条公式或法则。"
                "可尝试的关键词：去括号、通分、方程、面积、周长、勾股、应用题。")
    return "根据你的问题，给一条相关公式/法则提示（不给最终答案）：" + hits[0]


def unit_convert(query, value=None, from_unit=None, to_unit=None):
    q = query or ""
    v, src, dst = value, from_unit, to_unit
    if v is None:
        m = re.search(r"(\d+(?:\.\d+)?)", q.replace("，", ","))
        v = float(m.group(1)) if m else None
    if src is None or dst is None:
        found = []
        for token in re.split(r"[\s，,把换算成到=?？。！!、]", q):
            u = _norm_unit(token)
            if u and token not in found:
                found.append(token)
        if len(found) >= 2 and src is None and dst is None:
            src, dst = found[0], found[1]
    if v is None or src is None or dst is None:
        src_info = _norm_unit(src or "")
        dst_info = _norm_unit(dst or "")
        return ("单位换算工具：请提供数值与两个单位（如「把 5 米换成厘米」）。"
                "支持长度（km/m/dm/cm/mm）、质量（t/kg/g）、时间（h/min/s）。")
    src_info, dst_info = _norm_unit(src), _norm_unit(dst)
    if not src_info or not dst_info:
        return f"暂不支持的单位：{src if not src_info else dst}。支持：km/m/dm/cm/mm、t/kg/g、h/min/s。"
    if src_info[0] != dst_info[0]:
        return f"「{src}」和「{dst}」不属于同一量纲（{src_info[0]} / {dst_info[0]}），无法换算。"
    result = v * src_info[1] / dst_info[1]
    unit_names = {k: k for k in UNITS}
    return f"换算过程：{v} {src} = {v} × {src_info[1]:g} ÷ {dst_info[1]:g} = {result:g} {dst}。"


def concept_lookup(query):
    q = query or ""
    for name, explain in CONCEPTS.items():
        if name in q:
            return f"【{name}】{explain}"
    return ("这个词不在概念小词典里。已收录：" + "、".join(CONCEPTS.keys()) +
            "。也可以先查本班材料，或换一个关键词。")


TOOLS = [
    {
        "name": "formula_hint",
        "description": "根据学生问题给出公式或步骤提示，不给最终数值答案（数学解题引导用）",
        "inputSchema": {"type": "object",
                        "properties": {"query": {"type": "string", "description": "学生提问原文"}},
                        "required": ["query"]},
        "run": lambda args: formula_hint(args.get("query", "")),
    },
    {
        "name": "unit_convert",
        "description": "米/厘米/千米、千克/克、时/分/秒之间的单位换算，可从自然语言问句取参",
        "inputSchema": {"type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "学生提问原文"},
                            "value": {"type": "number"},
                            "from": {"type": "string"},
                            "to": {"type": "string"},
                        },
                        "required": ["query"]},
        "run": lambda args: unit_convert(args.get("query", ""),
                                         args.get("value"), args.get("from"),
                                         args.get("to")),
    },
    {
        "name": "concept_lookup",
        "description": "小学数学概念速查（分数/方程/面积/周长/质数等），返回简明定义",
        "inputSchema": {"type": "object",
                        "properties": {"query": {"type": "string", "description": "概念或提问原文"}},
                        "required": ["query"]},
        "run": lambda args: concept_lookup(args.get("query", "")),
    },
]


def rpc_result(req_id, result):
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def rpc_error(req_id, code, message):
    return {"jsonrpc": "2.0", "id": req_id,
            "error": {"code": code, "message": message}}


def handle_rpc(body):
    """处理一条 JSON-RPC 请求（body 为 dict）；返回 (响应 dict, http_status)。"""
    if body.get("jsonrpc") != "2.0" or "method" not in body:
        return rpc_error(body.get("id"), -32600, "请求不是合法的 JSON-RPC 2.0 报文"), 400
    req_id = body.get("id")
    method = body["method"]
    params = body.get("params") or {}
    if method == "initialize":
        return rpc_result(req_id, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": SERVER_INFO,
        }), 200
    if method == "tools/list":
        return rpc_result(req_id, {"tools": [
            {k: t[k] for k in ("name", "description", "inputSchema")} for t in TOOLS
        ]}), 200
    if method == "tools/call":
        name = params.get("name")
        tool = next((t for t in TOOLS if t["name"] == name), None)
        if tool is None:
            return rpc_error(req_id, -32602, f"未知工具：{name}"), 200
        args = params.get("arguments") or {}
        try:
            text = tool["run"](args)
            return rpc_result(req_id, {"content": [{"type": "text", "text": text}],
                                       "isError": False}), 200
        except Exception as e:  # 工具内部错误：isError=true，HTTP 仍 200
            return rpc_result(req_id, {"content": [{"type": "text", "text": f"工具执行失败: {e}"}],
                                       "isError": True}), 200
    return rpc_error(req_id, -32601, f"未知方法：{method}"), 200


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, obj, code=200):
        raw = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path == "/health":
            self._send({"status": "ok"})
        else:
            self._send({"error": "not found"}, 404)

    def do_POST(self):
        if self.path != "/mcp":
            self._send({"error": "not found"}, 404)
            return
        token = os.environ.get("MCP_AUTH_TOKEN", "")
        auth = self.headers.get("Authorization", "")
        if not token or auth != f"Bearer {token}":
            self._send({"error": "unauthorized",
                        "message": "缺少或错误的 Bearer 令牌"}, 401)
            return
        try:
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        except (ValueError, UnicodeDecodeError):
            self._send(rpc_error(None, -32700, "请求体不是合法 JSON"), 400)
            return
        resp, code = handle_rpc(body)
        self._send(resp, code)


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8090
    print(f"campus-tools MCP 服务监听 http://0.0.0.0:{port} （POST /mcp, GET /health）")
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()

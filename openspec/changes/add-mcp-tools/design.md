# Design: add-mcp-tools

## mcp-server/（自建 MCP 服务）

纯 Python 标准库（`http.server`），无第三方依赖，独立 Dockerfile。

- `GET /health` → `{"status":"ok"}`（无需令牌）。
- `POST /mcp`：`Authorization: Bearer <MCP_AUTH_TOKEN>` 校验，失败 401；请求体非法 JSON → JSON-RPC `-32700`；未知方法 → `-32601`；参数非法 → `-32602`。
- `initialize` → 协议版本 `2024-11-05` + `serverInfo` + `capabilities.tools`。
- `tools/list` → 3 个工具（name/description/inputSchema）：
  - `formula_hint(query)`：按关键词（去括号/通分/方程/面积/勾股…）返回公式与步骤提示，不给最终数值答案；
  - `unit_convert(query)`：从问句解析 `数值+源单位+目标单位`（米/厘米/千米/千克/克/分/秒…），解析失败给默认换算示例；返回换算过程与结果；
  - `concept_lookup(query)`：内置小词典（分数/方程/面积/周长/质数…）返回概念解释，未收录时明确说明。
- `tools/call` → `{"content":[{"type":"text","text":…}],"isError":bool}`；工具内部异常 → `isError=true`（HTTP 仍 200）。
- 工具名满足主机侧引用规则：小写字母开头，仅小写字母/数字/下划线。

Compose：`mcp-server` 服务，`env_file: .env`（`MCP_AUTH_TOKEN`），不映射宿主端口；app 容器经 `http://mcp-server:8090` 访问。

## 主机侧数据模型

```sql
CREATE TABLE IF NOT EXISTS mcp_servers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    class_id INTEGER NOT NULL REFERENCES classes(id),
    name TEXT NOT NULL,
    base_url TEXT NOT NULL,
    auth_token TEXT NOT NULL DEFAULT '',
    connected INTEGER NOT NULL DEFAULT 0 CHECK (connected IN (0,1)),
    connected_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    UNIQUE(class_id, name)
);
CREATE TABLE IF NOT EXISTS mcp_tools (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    server_id INTEGER NOT NULL REFERENCES mcp_servers(id) ON DELETE CASCADE,
    tool_name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    schema_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(server_id, tool_name)
);
CREATE TABLE IF NOT EXISTS mcp_tool_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    class_id INTEGER NOT NULL REFERENCES classes(id),
    server_id INTEGER NOT NULL REFERENCES mcp_servers(id),
    tool_ref TEXT NOT NULL,
    user_id INTEGER REFERENCES users(id),
    conversation_id INTEGER REFERENCES conversations(id),
    status TEXT NOT NULL CHECK (status IN ('ok','denied','error')),
    detail TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
```

- `mcp_tools` 缓存覆盖写：连接成功事务内先删后插；外键需 `PRAGMA foreign_keys=ON`（连接内局部开启）。
- 令牌边界：库内存原文；列表响应只回 `has_auth` 布尔；修改时留空 = 不改；改地址或令牌 → 置回未连接并清缓存；日志不记令牌。

## 客户端与编排

`app/mcp.py`：

- `json_rpc(base_url, method, params, token, timeout=10)`：自动补 `/mcp` 后缀；401/网络错误/`error` 响应统一抛 `McpError`（带可读原因）。
- `sanitize_tool_text(text)`：命中指令式句式（`忽略前述`、`ignore previous`、`你现在是`、`system:`，大小写不敏感）或超 1200 字 → 整条丢弃，返回 None。

会话编排（`assistant.py`，位于「选技能」之后、「生成」之前）：

1. 汇总选中技能的 `tools` 白名单，跳过 `knowledge_search`；
2. 逐条解析 `tool@server`：按名取本班服务器——不存在 → `denied` 且**不写审计**；未连接 → `denied` **写审计**；已连接 → `tools/call({"query": 提问原文})`，成功 `ok`（detail=结果前 200 字）/ 失败 `error`，均写审计；
3. `ok` 的返回过 `sanitize_tool_text`，拼进用户消息：`\n\n[工具 <ref> 返回的数据]\n<文本>`；被丢弃或非 ok 的不进提示词；
4. `tool_calls` 清单（ref/status/摘要）先随 SSE `meta` 事件推送（在全部 `delta` 之前），并写入 `llm_call_logs.tool_calls` 与日志 `request_json` 的用户消息；
5. 任何工具失败不中断回答主路径。

## 技能绑定校验

`skillfile.validate_tool_refs(class_id, tools_text)` 返回 `(refs, error)`：

1. 分隔符切分（逗号/顿号/分号/竖线）；
2. 每项须为 `knowledge_search` 或匹配 `^[a-z][a-z0-9_]{0,31}@[a-z][a-z0-9_-]{0,31}$`；
3. MCP 引用：本班同名服务器存在且 `connected=1` 且工具在缓存清单内，否则 400（存在性不泄露：跨班/不存在同样提示「服务器未登记或未连接」）。

应用于：`POST /api/skills`、`PATCH /api/skills/<id>`（改 tools 时）、`POST /api/skills/upload`。

## API 一览（全部「登录 + 仅教师」，学生 403；他班/不存在一律 404）

| 方法与路径 | 说明 |
| --- | --- |
| `GET/POST /api/mcp/servers` | 列表（含 tool_count、has_auth，无令牌）/ 登记（同班同名 400） |
| `PUT/DELETE /api/mcp/servers/<id>` | 修改（清连接与缓存）/ 删除（缓存级联；有审计记录时保留审计并允许删除——审计表 `server_id` 允许悬空置 NULL？不：改为「先删缓存再删服务器，审计行 server_id 置 NULL、tool_ref 保留」） |
| `POST /api/mcp/servers/<id>/connect` | 握手+发现+覆盖缓存；失败 502 |
| `POST /api/mcp/servers/<id>/disconnect` | 置未连接并清缓存 |
| `GET /api/mcp/servers/<id>/tools` | 已发现工具清单 |
| `GET /api/mcp/tool-calls` | 本班审计，时间倒序，默认 50 上限 100 |

> 删除语义修正：为不阻塞删除又不丢证据，删除服务器时将其审计行 `server_id` 置 NULL（`tool_ref`/`class_id` 保留），缓存级联删除。SQLite 外键默认关闭，代码显式 `PRAGMA foreign_keys=ON` 后按此顺序处理。

## 页面

- `/settings` MCP 页签：服务器列表（名称/地址/状态/工具数/has_auth）、登记表单（令牌为密码框，提交后清空不回显）、连接并发现/断开按钮、工具清单展示、最近调用审计表。
- `/apps/<id>` 与 `/ask` 对话页：解析 SSE `meta.tool_calls`，回答气泡上方显示「🔧 formula_hint@campus-tools · ok」标签。

## 测试

- `tests/test_mcp.py`：进程内起 mcp-server（随机端口）+ stub 网关 + 临时 Qdrant——`initialize`/`tools/list`/`tools/call`、错令牌 401、登记/连接/断开与缓存覆盖、技能绑定四道校验拒绝路径、对话触发调用（审计 ok、`meta.tool_calls`、用户消息含数据块）、断开后 denied、未连接服务器保存技能被拒、令牌不出现在任何接口响应。
- `apitest/`：`mcp/servers/POST`（登记 + 令牌不回传 + 学生 403）、`mcp/servers/_id_/connect/POST`（连接发现 + 工具缓存落库）、`mcp/tool-calls/GET`（审计可见）；E2E 用例：连接 → 上传含 `formula_hint@…` 的技能 → 应用会话提问 → 审计出现 `ok` 且日志含工具数据块。

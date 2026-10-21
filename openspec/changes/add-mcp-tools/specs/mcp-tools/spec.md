# Spec: mcp-tools

## Purpose

把技能的「工具」栏从检索开关升级为真实外部调用：同仓自建 MCP 工具服务（JSON-RPC 2.0 over HTTP，Bearer 鉴权），教师登记并连接后发现工具；技能以 `工具名@服务器名` 绑定（保存前四道校验）；学生提问命中技能时服务端带令牌确定性调用，返回作为数据拼进用户消息，调用全程审计可查、SSE `meta` 可见、令牌不出服务端。

## ADDED Requirements

### Requirement: 自建 MCP 服务器

仓库 MUST 包含同仓 `mcp-server/`：提供 `GET /health` 与 `POST /mcp`（JSON-RPC 2.0），实现 `initialize`、`tools/list`、`tools/call`，暴露至少 2 个可调用工具；Bearer 令牌从环境变量读取，令牌错误 MUST 返回 401，非法请求 MUST 返回可读的 JSON-RPC 错误；由 Compose 与主应用一并构建启动且不对宿主暴露端口。

#### Scenario: 握手、发现与调用

- **WHEN** 携带正确 Bearer 令牌依次发送 `initialize`、`tools/list`、`tools/call({"name":"formula_hint","arguments":{"query":"去括号"}})`
- **THEN** 三个方法 MUST 各自返回 `result`（服务器信息 / 工具清单含名称与参数结构 / `content` 文本数组且 `isError=false`）
- **WHEN** 令牌错误或缺失
- **THEN** HTTP 状态 MUST 为 401

#### Scenario: Compose 一体启动

- **WHEN** `docker compose up` 后在 app 容器内访问 `http://mcp-server:8090/health`
- **THEN** MUST 返回 ok；宿主机 MUST NOT 能直连该服务

### Requirement: 服务器登记与令牌边界

教师 MUST 能登记本班 MCP 服务器（名称、Base URL、Bearer 令牌），同班同名 MUST 返回 400；令牌 MUST 只保存在服务端，任何列表/详情响应 MUST NOT 含令牌字段，只允许 `has_auth` 布尔；学生 MUST 不能访问 MCP 管理接口（403）；他班服务器按编号访问 MUST 与不存在一致（404）。

#### Scenario: 登记与令牌不回传

- **WHEN** 教师 A 登记服务器 `campus-tools` 并列出本班服务器
- **THEN** 响应 MUST 含 `has_auth=true` 且整份响应搜不到令牌原文
- **WHEN** 学生或 B 班教师调用任一 MCP 管理接口
- **THEN** MUST 得到 403 或 404

### Requirement: 连接与发现

教师 MUST 能对已登记服务器执行「连接」：服务端 MUST 先 `initialize` 握手再 `tools/list`，把工具清单**覆盖**写入缓存并标记已连接；任一步失败 MUST 返回 502、置回未连接且不写缓存；「断开」MUST 置回未连接并清空缓存；连接失败 MUST NOT 阻断既有检索与流式对话。

#### Scenario: 连接成功与缓存覆盖

- **WHEN** 教师对指向自建 mcp-server 的登记项连续连接两次
- **THEN** 两次 MUST 都成功，工具缓存行数 MUST 等于服务器工具数（不翻倍）
- **WHEN** 令牌改错后连接
- **THEN** MUST 返回 502 且该服务器状态为未连接、缓存为空

#### Scenario: 断开后缓存清空

- **WHEN** 教师断开已连接服务器
- **THEN** 状态 MUST 为未连接，`GET /api/mcp/servers/<id>/tools` MUST 返回空清单

### Requirement: 技能工具绑定

技能的 `tools` 栏 MUST 接受 `knowledge_search` 与 `工具名@服务器名` 引用（多项以逗号/顿号/分号/竖线分隔）；保存（新建/修改/上传）时 MUST 逐条校验：引用格式、本班同名服务器存在、已连接、工具在发现缓存内——任一不过 MUST 整份拒绝并返回可读原因；跨班或不存在的服务器 MUST 给出与「不存在」一致的提示。

#### Scenario: 合法引用保存成功

- **WHEN** 教师保存工具为 `knowledge_search, formula_hint@campus-tools` 的技能（服务器已连接且工具已发现）
- **THEN** MUST 保存成功且列表可见

#### Scenario: 非法引用被拒绝

- **WHEN** 保存工具为 `Formula_Hint@x`、`formula-hint@x`、`formula_hint`（缺 @服务器）或指向未连接/他班/不存在服务器的引用
- **THEN** MUST 返回 400 与可读原因，数据库无变更

### Requirement: 对话中的确定性调用与信任边界

命中带 MCP 工具的技能时，服务端 MUST 按技能白名单逐个调用（跳过 `knowledge_search`），调用参数 MUST 只含提问原文（`query`），不由模型生成；每次调用 MUST 写审计：`ok`（detail=结果摘要）/`denied`（服务器未连接）/`error`（调用失败），服务器已不存在时 MUST NOT 写审计行但 MUST 在响应中体现 `denied`；调用结果 MUST 先过安全校验（指令式句式或超 1200 字整条丢弃），再作为数据拼进用户消息，MUST NOT 进入 system 消息；SSE MUST 在首个 `delta` 前推 `meta` 事件并携带 `tool_calls`；工具失败 MUST NOT 中断回答主路径。

#### Scenario: 命中技能触发调用

- **WHEN** 学生在绑定了含 `formula_hint@campus-tools` 技能的应用中提问
- **THEN** SSE 事件序列 MUST 为 `meta`（含 `tool_calls`，该引用 `status=ok`）→ `delta…` → `citations` → `done`
- **AND** 发给 LLM 的用户消息 MUST 含 `[工具 formula_hint@campus-tools 返回的数据]` 数据块，system 消息 MUST NOT 含该数据块
- **AND** 审计表 MUST 新增 `ok` 行（含工具引用、用户、会话、时间）

#### Scenario: 断开后调用被拒

- **WHEN** 服务器断开后用同一技能提问
- **THEN** `tool_calls` 中该引用 MUST 为 `denied`，审计 MUST 新增 `denied` 行，回答照常流式返回

#### Scenario: 指令式返回被丢弃

- **WHEN** 工具返回文本包含「忽略前述请求」
- **THEN** 该条结果 MUST NOT 出现在发给 LLM 的任何消息中

### Requirement: 调用审计查询

教师 MUST 能查看本班最近 MCP 工具调用审计（工具引用、状态、摘要、用户、会话、时间，按时间倒序，默认 50 条上限 100）；审计 MUST 按班级隔离。

#### Scenario: 审计可查且本班隔离

- **WHEN** 教师 A 请求 `GET /api/mcp/tool-calls`
- **THEN** 响应 MUST 只含 A 班记录
- **AND** 三种状态 `ok`/`denied`/`error` 的记录均可通过构造相应场景观察到

### Requirement: 调用日志联动

带 MCP 调用的 LLM 请求 MUST 在 `llm_call_logs` 中记录 `tool_calls` 清单（引用与状态），且 `request_json` 的用户消息 MUST 可见工具数据块——与实际发出内容一致。

#### Scenario: 日志与实发一致

- **WHEN** 一次带工具调用的会话问答完成后查看调用日志详情
- **THEN** `tool_calls` 与 SSE `meta` 一致，`request_json` 中用户消息含数据块且 system 无数据块

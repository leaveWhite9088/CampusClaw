# Change: add-mcp-tools

## Why

个人项目验收要求平台「支持外部工具及 MCP 接入」，并要求验证「集成 MCP 工具后每次请求传给 LLM 的具体参数」。第 6 课任务清单给出了完整路径：同仓自建 `mcp-server/`（JSON-RPC 2.0，`initialize`/`tools/list`/`tools/call`），主机侧登记-连接-发现-绑定-调用-审计。当前系统技能的 `tools` 栏只是检索开关，没有任何真实外部调用。

## What Changes

- **自建 MCP 服务器**：同价新增 `mcp-server/`（纯标准库实现），`POST /mcp`（JSON-RPC 2.0）+ `GET /health`，Bearer 令牌鉴权（`MCP_AUTH_TOKEN` 环境变量），实现 `initialize`/`tools/list`/`tools/call`，暴露 3 个工具：`formula_hint`（公式/步骤提示，不给最终答案）、`unit_convert`（单位换算，支持从自然语言问句取参）、`concept_lookup`（概念速查）。由 `docker-compose.yml` 一并构建启动，仅内部网络可达。
- **主机侧登记与发现**：新增 `mcp_servers`/`mcp_tools`/`mcp_tool_calls` 三张表与 8 个管理接口（登记/列表/修改/删除/连接/断开/查工具/查审计）。令牌只存服务端，接口响应只回 `has_auth` 布尔；连接 = `initialize` 握手 + `tools/list` 发现 + 覆盖写缓存；失败返回 502 且不更新缓存。
- **技能绑定**：技能 `tools` 栏支持 `工具名@服务器名` 引用；保存（新建/修改/上传）时四道校验——引用格式、服务器存在、已连接、工具已发现——任一不过整份拒绝。
- **对话中鉴权调用**：命中带 MCP 工具的技能时，服务端按技能白名单确定性地逐个调用（跳过 `knowledge_search`），参数只含提问原文（`query`）；返回先过注入句式与长度安全校验，再作为**数据**拼进用户消息；SSE 先推 `meta` 事件（含 `tool_calls` 状态）再推 `delta`；每次调用写审计（`ok`/`denied`/`error`；服务器已不存在时不写审计行）。
- **教师 MCP 管理页**：`/settings` 新增 MCP 页签（登记、连接并发现、断开、查看工具与审计）；对话页展示本次工具调用。
- **调用日志联动**：`llm_call_logs.tool_calls` 记录本轮调用清单，日志 `request_json` 中的用户消息可见 `[工具 … 返回的数据]` 数据块，支撑验收第 5 项取证。

## Capabilities

### New Capabilities

- `mcp-tools`：MCP 服务器登记/连接/发现/断开、技能工具绑定校验、对话中的确定性调用与审计的可验收行为。

### Modified Capabilities

- `ai-app-platform`：技能上传与技能保存的工具校验从「格式 + 未知服务器拒绝」扩展为「服务器已连接且工具已发现」；会话编排插入「调工具」步骤，SSE 增加 `meta` 事件。

## Impact

- 新增 `mcp-server/` 目录（server.py、Dockerfile）与 Compose `mcp-server` 服务（不映射宿主端口）。
- 数据层：新增三张 MCP 表；服务层新增 `app/mcp.py`（客户端 + 安全校验）与 `app/mcp_api.py`（管理接口）；对话编排、SSE 事件、技能校验联动修改。
- 页面：`/settings` MCP 页签；`/apps/<id>` 对话页工具调用展示。
- `.env.example` 增加 `MCP_AUTH_TOKEN`；`tests/test_mcp.py` 与 `apitest/` 新增用例。

## Non-goals（非目标）

- 不做完整 MCP 传输（stdio/长连接）、资源与提示能力；只实现工具的发现与调用。
- 不做模型原生 Function Calling——调用时机与参数由代码决定，不由模型决定。
- 不做多服务器负载、重试与超时策略（单次调用 10s 超时，失败即记 `error`）。

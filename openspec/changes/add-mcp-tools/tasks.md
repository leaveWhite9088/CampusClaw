# Tasks: add-mcp-tools

## 1. mcp-server/

- [ ] 1.1 `mcp-server/server.py`：`/health` + `POST /mcp`（JSON-RPC：initialize / tools/list / tools/call，Bearer 401，-32700/-32601/-32602）— verify: 错令牌 401；tools/call 返回文本
- [ ] 1.2 三个工具：`formula_hint`、`unit_convert`（问句取参）、`concept_lookup` — verify: tools/list 可见；tools/call 各得文本
- [ ] 1.3 `mcp-server/Dockerfile` + Compose `mcp-server` 服务（不映射宿主端口）— verify: `docker compose up` 后 app 容器可达 `http://mcp-server:8090/health`

## 2. 主机侧数据与管理接口

- [ ] 2.1 三张表迁移：`mcp_servers`/`mcp_tools`/`mcp_tool_calls`（同班唯一、级联、审计只增） — verify: 重复启动不报错；唯一约束生效
- [ ] 2.2 `app/mcp.py`：JSON-RPC 客户端（自动补 `/mcp`、10s 超时、McpError）+ `sanitize_tool_text`（句式/1200 字） — verify: 单测覆盖 401/超时/句式拦截
- [ ] 2.3 八个管理接口：列表/登记/修改/删除/连接/断开/查工具/查审计（教师 403、他班 404、令牌只回 `has_auth`） — verify: apitest + 单测
- [ ] 2.4 连接五步：取服务器 → 补 `/mcp` → 握手 → 发现 → 覆盖写缓存+标记；失败 502 不落缓存 — verify: 改错令牌连接 502；连两次缓存不翻倍

## 3. 绑定与编排

- [ ] 3.1 `validate_tool_refs` 四道校验接入技能新建/修改/上传 — verify: 四类非法引用各 400
- [ ] 3.2 会话编排插入工具调用：白名单逐个调用（跳过 knowledge_search）→ 审计（ok/denied/error；无服务器不写审计）→ 安全校验 → 数据块拼用户消息 — verify: 单测断言 stub 收到的 messages
- [ ] 3.3 SSE `meta` 事件（tool_calls）先于首个 delta；`llm_call_logs.tool_calls` 落库 — verify: 解析事件序与日志行
- [ ] 3.4 断开/删除后的调用路径：断开 → denied+审计；删除 → denied 无审计 — verify: 单测

## 4. 页面与文档

- [ ] 4.1 `/settings` MCP 页签：登记（密码框令牌）/连接/断开/工具清单/审计表 — verify: 浏览器全流程
- [ ] 4.2 对话页展示 `meta.tool_calls` 标签 — verify: 命中技能提问后可见
- [ ] 4.3 `openapi.json` 补 MCP 路径；`.env.example` 增 `MCP_AUTH_TOKEN` — verify: Swagger 可见可试调

## 5. 测试与收尾

- [ ] 5.1 `tests/test_mcp.py` 全过；第 4/5/6 课回归不破 — verify: 全量单测
- [ ] 5.2 apitest 新增 MCP 用例全绿（登记/连接/断开/学生 403/E2E 审计 ok） — verify: `python apitest/run_all.py`
- [ ] 5.3 令牌边界自查：接口响应、前端页面、Git、镜像均无令牌原文 — verify: grep + 页面检查

# Design: add-skill-prompt-stream-chat

## Context

第 4 课已归档/实现：Flask + SQLite + Qdrant，三种检索模式、`/api/ask` 单次问答、Bearer+Cookie 双凭证。本 change 新增解题助手：提示词与技能由教师维护，学生侧会话连续追问，SSE 流式返回。可验收行为见 `specs/assistant-chat/spec.md`。

## Goals / Non-Goals

**Goals:**

- 一次回答的输入 = 班级提示词 + 已启用技能指令 + 本班检索切片 + 本轮提问（+ 历史）。
- 回答经 SSE 逐段送达；提问与回答落库，按会话可查。
- 教师写、学生读；技能开关与提示词修改在服务端按角色拒绝。

**Non-Goals:** 见 proposal（其余技能、MCP、异步队列、Function Calling 等）。

---

## 数据模型

```sql
class_prompts(            -- 每班一条当前生效的提示词
  class_id INTEGER PRIMARY KEY REFERENCES classes(id),
  content TEXT NOT NULL,
  updated_by INTEGER, updated_at TEXT DEFAULT (datetime('now','localtime')))

-- skills 表扩展（第 3 课占位表）：
--   + description TEXT（一句话简介）, instructions TEXT（完整指令）,
--   + enabled INTEGER DEFAULT 0, updated_at TEXT
conversations(
  id INTEGER PK, class_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
  title TEXT NOT NULL, created_at TEXT DEFAULT ...)
messages(
  id INTEGER PK, conversation_id INTEGER NOT NULL REFERENCES conversations(id),
  role TEXT CHECK (role IN ('user','assistant')), content TEXT NOT NULL,
  citations TEXT,            -- JSON 数组，assistant 消息用
  created_at TEXT DEFAULT ...)
```

- 会话属于「用户 + 班级」：列表与消息只读自己的；跨用户/跨班访问 403/404（与材料一致，固定 403 用于越权、404 用于不存在）。
- 既有库经启动迁移幂等建表/加列（`CREATE TABLE IF NOT EXISTS` + `ALTER TABLE ... ADD COLUMN` 探测）。

## API 设计

| 方法 | 路径 | 角色 | 说明 |
| --- | --- | --- | --- |
| GET | `/api/prompt` | 登录 | 读取本班当前提示词（无则空串） |
| PUT | `/api/prompt` | 教师 | 保存提示词 `{content}`；学生 403；从下一轮对话生效 |
| GET | `/api/skills` | 登录 | 本班技能列表（名称/简介/启用态） |
| POST | `/api/skills` | 教师 | 新建技能 `{name, description, instructions}`；学生 403 |
| PATCH | `/api/skills/<id>` | 教师 | 修改或开关 `{enabled?, instructions?, ...}`；跨班 403 |
| POST | `/api/conversations` | 登录 | 新建会话 `{title?}`（默认取首条提问前 20 字） |
| GET | `/api/conversations` | 登录 | 自己的会话列表（倒序） |
| GET | `/api/conversations/<id>/messages` | 登录 | 该会话历史消息（含 citations） |
| POST | `/api/conversations/<id>/messages` | 登录 | 发送消息，**SSE 流式返回**回答 |

SSE 事件（`text/event-stream`，每事件一行 JSON）：

```
data: {"type":"delta","text":"……"}      # 回答片段，可有多个
data: {"type":"citations","citations":[{material_title,chunk_index,...}]}
data: {"type":"done"}                   # 结束
```

无命中时直接 `delta` 推固定文案 + 空 `citations` + `done`，不调用对话网关。

## 回答编排（assistant pipeline）

`POST messages` 收到提问后：

1. 保存 user 消息；空提问 400；会话归属校验。
2. 本班混合检索取前 4 条（沿用 `retrieval.search`；向量路径不可用时退化为关键字路径——第 4 课 spec 的 503 语义针对 `/api/search`，会话内问答以可用路径作答并在事件中标注 `degraded: true`）。
3. 组装对话输入：system = 班级提示词 + （启用技能的完整指令）+ 编号资料（沿用 `chat.py` 的引用格式，技能指令嵌入 system 段）；历史消息取该会话最近 6 条。
4. 调对话网关（非流式请求），拿到完整回答后**服务端按约 20 字切段**以 SSE 逐段推送，随后推 citations 与 done；保存 assistant 消息（content + citations JSON）。
   - 决策：SSE 分段在服务端做而非透传网关流式——stub 网关无需实现 SSE，真实网关亦可复用同一非流式调用；对浏览器行为一致。
5. 网关失败：`delta` 推错误说明 + `done`（事件带 `error`），HTTP 状态仍为 200（SSE 已开始）；尚未开始时可返回 503。

## 页面

- `/settings`（仅教师进入，学生 302 回本班材料页）：提示词 textarea（GET/PUT）；技能列表（启用开关）+ 新建技能表单（名称/简介/指令）。
- `/ask`（登录）：左栏会话列表 + 「新对话」；主区消息流；输入框回车发送，fetch + ReadableStream 解析 SSE 逐段渲染，回答下方列出处（沿用第 4 课 hit 卡片样式）；材料页顶栏加入口链接。
- 两个页面均通过 `authFetch` 携带 Bearer 令牌（第 0930 任务已实现）。

## OpenAPI 与 Swagger

- 手写 `openapi.json`（OpenAPI 3.1）覆盖全部 API：login、logout、search、ask、prompt、skills、conversations、messages、materials、reindex、health；每个路径标注入参出参、错误码（400/401/403/404/503）与是否需要登录（`security: bearerAuth / cookieAuth`）。
- 静态托管于 `/openapi.json`；`/swagger` 页面用本地 vendored swagger-ui（`app/static/vendor/swagger-ui/`），离线可开，试调时 Authorize 填 Bearer 令牌。

## apitest 接口测试

```
apitest/
  run_all.py                  # 一键：起临时实例（临时库+stub 网关）→ 跑全部用例 → HTML 报告
  lib.py                      # HTTP 客户端封装、DB 断言工具、报告渲染
  cases/api/login/POST.py
  cases/api/search/GET.py
  cases/api/prompt/PUT.py
  cases/api/skills/POST.py
  cases/api/conversations/POST.py
  cases/api/conversations/_id_/messages/POST.py
  reports/                    # gitignore
```

- 用例不只断言状态码：核对响应字段与数据库行（如发消息后 `messages` 表确有 user+assistant 两行且 citations 非空）。
- run_all 依赖可达的 Qdrant（缺则尝试 `docker run` 临时容器），嵌入/对话走内置 stub。

## Decisions（摘要）

| # | 决策 | 备选 |
| --- | --- | --- |
| 1 | 提示词每班一条当前生效 | 多版本历史（本课不验收） |
| 2 | 技能启用即整段注入 system | 渐进式披露（只有一个技能，暂不需要） |
| 3 | SSE 分段由服务端做，网关仍非流式 | 透传网关 SSE（stub 需实现 SSE，链路更脆） |
| 4 | 会话归属用户本人 | 全班共享会话（不符合「学生新建会话」语义） |
| 5 | swagger-ui vendored 到 static | CDN 引用（离线打不开） |

## Risks / Trade-offs

- [SSE 占用 gunicorn worker] → sync worker 2 个，演示并发足够；后续可换 gevent。
- [启动迁移 ALTER 老库] → 幂等探测列存在性；新库由 init_db 全量建。
- [技能指令被注入攻击] → 仅教师可写；学生消息中的 system 注入仍被丢弃（第 4 课行为）。

## Migration Plan

既有 `data/app.db`：启动时补 `class_prompts`/`conversations`/`messages` 表与 `skills` 新列；技能表插入一条种子「解题引导」技能（A/B 班各一条，默认停用，教师上课时启用）。实现顺序见 `tasks.md`。

## Open Questions

（无。）

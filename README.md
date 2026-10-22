# CampusClaw

> 仓库地址：https://github.com/leaveWhite9088/CampusClaw.git （main 分支）
>
> 北京大学《互联网软件开发技术与实践》课程项目（2026 年秋，主讲：张齐勋）。
> 本仓库是课程实训作业：以 SDD（规约驱动开发）方式，借助 AI 编程工具逐课迭代实现——
> 所有功能先在 `openspec/changes/` 下编写规约四件套（proposal / design / specs / tasks），再按规约实现与验收。

## 项目简介

CampusClaw 是一个面向中小学教研场景的 **AI 应用平台**：教师按班级上传与管理教学材料，本班成员围绕材料做检索与问答；在此之上平台提供应用层能力——**内置多个 AI 应用、提示词模板、内置与可上传的技能（Skill）、经 MCP（Model Context Protocol）接入的外部工具**。

- **班级是数据边界**：所有业务查询在服务端按登录会话中的班级过滤，请求中携带的 `class_id` 一律丢弃；跨班访问表现为「不存在/无命中」，不泄露数据归属。
- **安全约定**：密码哈希存储；所有密钥（会话密钥、对话/嵌入网关、MCP 令牌）只放服务端 `.env`，不进 Git、不进镜像、不进前端；外部内容（检索切片、工具返回）一律作为数据进用户消息，不进 system 消息。
- **不做**：重排序、LangChain 类编排框架、模型自主选工具（Function Calling）、作业提交与批改、注册与找回密码、SSO、生产级高可用（各 change 的 Non-goals 见 `openspec/`）。

## 功能总览

| 功能 | 说明 | 主要入口 |
| --- | --- | --- |
| 内置多个 AI 应用 | 每班预置「资料问答 / 解题引导 / 作文点评」三个内置应用，教师可自建应用并绑定模板、技能与材料范围；应用内会话与旧会话（解题助手）共存 | `/apps`、`/ask` |
| 提示词模板 | 每班 3 个内置模板，支持 `{{skills}}`/`{{knowledge}}` 占位符；应用绑定模板，渲染后作为 system 消息发给 LLM | `/settings` 模板页签 |
| 知识库检索 | SQLite FTS5 关键字 + Qdrant 向量，keyword/vector/hybrid（RRF）三种模式；回答带 `[编号]` 出处；应用可限定材料子集 | `/materials`、`/api/search` |
| 技能（Skill） | 内置「解题引导 / 概念讲解 / 作文点评」，按适用条件关键词路由；支持课程技能文件格式上传（`.md`/`.json`），工具白名单保存前校验 | `/settings` 技能页签 |
| MCP 工具接入 | 同仓自建 `mcp-server/`（JSON-RPC 2.0，3 个工具）；教师登记/连接/断开；技能按 `工具名@服务器名` 绑定；命中即带令牌确定性调用，SSE `meta` 显示 `tool_calls`，全程审计 | `/settings` MCP 页签 |
| LLM 调用日志 | 每次调用对话网关完整记录请求 JSON、返回内容、模板/技能注入、知识库「全库 vs 实际传入」统计（教师可查、按班隔离） | `/settings` 日志页签 |

## 快速开始

### 标准启动：Docker Compose（五服务）

```bash
cp .env.example .env        # 填入 SECRET_KEY 与网关/MCP 配置（见下节）
docker compose up --build
```

服务拓扑（对外只有 Nginx 一个端口）：

```
浏览器 ──> web (Nginx, 8088) ──> app (gunicorn, 8000, 内部) ──> qdrant (6333, 内部)
                                              └─────────────> mcp-server (8090, 内部)
宿主机 stub 网关 (9700) <──── app 经 host.docker.internal 调用（可选）
```

- 登录页：http://localhost:8088/login ；健康检查：http://localhost:8088/health
- 预置账号：`teacher_a` / `teach123`（教师·班级 A）、`student_a1` / `stu123`（学生·班级 A）、`student_b1` / `stu123`（学生·班级 B）
- 首次启动自动建表并写入种子数据；数据经 `./data`、`./uploads` 与 `qdrant_storage` 卷持久化
- 一键准备演示数据（登记并连接 MCP 服务器、创建「数学解题引导」技能与「数学工具助手」应用、扩充数学材料）：

```bash
docker compose exec app python scripts/seed_demo.py
```

### 网关与 MCP 配置（`.env`）

课程演示用抽取式 stub 网关扮演 OpenAI 兼容的嵌入与对话接口（无需真实密钥）：

```bash
python scripts/dev_stub_gateway.py 9700    # 宿主机启动 stub 网关
```

`.env` 中 `EMBEDDING_API_*`、`CHAT_API_*` 指向 `http://host.docker.internal:9700`（本地开发则 `localhost:9700`）；`MCP_AUTH_TOKEN` 为自建 MCP 服务的 Bearer 令牌（mcp-server 容器与主机侧登记使用同一个值）。接入真实网关时替换对应三项即可；未配置嵌入网关时 `keyword` 检索仍可用，`vector`/`hybrid` 返回 503，不编造分数或出处。

### 本地开发（单进程）

```bash
pip install -r requirements.txt
python scripts/init_db.py   # 初始化 SQLite 并写入种子数据
python run.py               # http://localhost:8080
```

## 使用导览

**学生**：`/materials` 检索本班材料并就材料提问；`/apps` 进入 AI 应用发起会话（SSE 流式回答 + 出处标注，命中 MCP 工具时显示工具调用标签）；`/ask` 使用第 5 课的解题助手（旧会话路径）。

**教师**（额外能力）：`/materials` 上传 `.txt/.md` 材料并选择切分策略；`/apps` 新建/删除应用；`/settings` 五个页签——班级提示词（旧会话用）、提示词模板、技能（新建 + 上传技能文件）、MCP 服务器（登记 / 连接并发现 / 断开 / 审计）、LLM 调用日志（列表 + 完整请求/返回详情）。

**一次应用内问答的编排**（服务端确定性流程）：选应用 → 按适用条件选技能 → 本班（或应用绑定材料范围）混合检索取前 4 条切片 → 按技能工具白名单逐个调用 MCP 工具（跳过 `knowledge_search`）→ 工具返回过安全校验后作为数据拼进用户消息 → 模板渲染 + 技能全文 + 编号资料组装 system → 调用对话网关（写一条调用日志）→ SSE 按 `meta` → `delta` → `citations` → `done` 推送。无命中不调模型也不调工具；工具失败只影响本次回答，不中断主路径。

## API 文档与测试

- **API 文档**：`/openapi.json`（OpenAPI 3.0，33 个路径）与 `/swagger` 离线试调页（本地 vendor，可配置 Bearer 令牌直接试调）。
- **单元测试**（4 套 72 项，数据用例需 Qdrant，网关由内置 stub 扮演）：

```bash
python tests/test_lesson4.py   # 切分/检索/溯源/隔离/降级（37 项）
python tests/test_lesson5.py   # 提示词/技能/会话/SSE/文档（11 项）
python tests/test_lesson6.py   # AI 应用/模板/技能上传/调用日志（11 项）
python tests/test_mcp.py       # MCP 协议/登记连接/绑定校验/调用与审计（13 项）
```

- **接口测试**（临时实例一键跑完，出 HTML 报告，报告不入库）：

```bash
python apitest/run_all.py      # 13 个用例，检查项含返回内容与数据库一致性核对
```

## 仓库结构

```
app/            Flask 应用（认证、班级隔离、材料入库、切分检索、应用/模板/技能、
                对话编排与调用日志、MCP 管理 app/mcp_api.py、MCP 客户端 app/mcp.py）
mcp-server/     自建 MCP 工具服务（JSON-RPC 2.0 over HTTP，formula_hint/
                unit_convert/concept_lookup，Bearer 鉴权，纯标准库）
scripts/        init_db.py 建库与种子、dev_stub_gateway.py 演示网关、seed_demo.py 演示数据
tests/          第 4/5/6 课与 MCP 单元测试（unittest）
apitest/        接口测试（一接口一脚本 + run_all.py 一键 HTML 报告）
openspec/       SDD 规约：changes/ 当前 change 四件套，archive/ 已归档 change
deploy/         Nginx 反向代理配置
docs/           设计参考资料、作业材料；docs/report/ 为验收报告（docx/pdf、
                截图 assets/、取证 evidence/、生成脚本 build_report.js）
ppt/            课件 Markdown 整理版
```

## 课程进度

- **第 2 课**：OpenSpec 初始化，编写 `add-auth-rbac-class-knowledge` 规约四件套
- **第 3 课**：实现登录、班级隔离、上传入库与文件下载；Docker Compose 双服务部署（Nginx 反代 + 后端不暴露端口）并归档规约
- **第 4 课**：`add-traceable-vector-retrieval`——正文切分（auto/custom/hierarchy）、FTS5 + Qdrant 双库、keyword/vector/hybrid（RRF）检索、命中溯源、`/api/ask` 带出处问答、检索侧隔离与降级
- **0930 课堂任务**：`add-bearer-token-auth`——JWT 签发、Bearer + Cookie 双凭证；stub 网关 `scripts/dev_stub_gateway.py`
- **第 5 课**：`add-skill-prompt-stream-chat`——班级提示词与「解题引导」技能、`/ask` 会话式 SSE 流式问答 + 出处标注、OpenAPI 与离线 Swagger、`apitest/` 接口测试
- **第 6 课**：`add-ai-app-platform` + `add-mcp-tools`——内置多 AI 应用（应用绑定模板/技能/材料范围）、提示词模板（占位符渲染）、技能上传、LLM 调用日志；自建 `mcp-server/`、主机侧登记/连接/绑定/确定性调用/审计、SSE `meta.tool_calls`（详见 `openspec/changes/`）
- **验收**：五大功能全部实现并跑通；五项验证内容逐项取证（结论与证据见 `docs/report/` 报告第 3 章）；单元测试 72 项、接口测试 13 用例全绿

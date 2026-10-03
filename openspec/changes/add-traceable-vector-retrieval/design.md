# Design: add-traceable-vector-retrieval

## Context

第 3 课 change（`2026-09-23-add-auth-rbac-class-knowledge`）已归档：Flask 3 + SQLite 单体应用，web(Nginx)+app(gunicorn) 双服务 Compose 拓扑，app 不暴露端口；登录、角色、班级隔离、上传入库、下载均已实现。本 change 在其后追加**检索能力**：切分、嵌入、向量库、三种检索模式与问答接口。动机见 `proposal.md`；可验收行为见 `specs/knowledge-retrieval/spec.md`。

## Goals / Non-Goals

**Goals:**

- 一句自然语言可在本班材料中定位相关切片，结果含出处（标题、序号、字符区间、摘录）。
- 三种检索模式行为可区分、可独立验证；默认混合。
- 无依据时明确返回未找到，不调用生成模型、不编造出处。
- 班级边界在检索链路与上传链路一致，改请求参数无法越权。
- 向量库与两类模型网关仅服务端可达，密钥不出服务端。

**Non-Goals:**

- 见 `proposal.md` Non-goals（流式、重排序、编排框架、按班拆集合、PDF 等）。

---

## 技术选型：课程方案到本项目的映射

课件演示栈为 Go + MySQL + Qdrant + 课程网关；本项目沿用第 3 课已固定的 Flask + SQLite，向量库与网关协议与课件对齐。

| 环节 | 课件选型 | 本项目选型 | 说明 |
| --- | --- | --- | --- |
| 应用服务 | Go | Flask 3（沿用） | 新增检索模块，认证/材料模块不变 |
| 切片正文 | MySQL `knowledge_chunks` | SQLite `knowledge_chunks` | 关系库职责相同：正文、序号、偏移、班级 |
| 关键字索引 | MySQL `FULLTEXT ... WITH PARSER ngram`（token 2） | SQLite **FTS5 trigram** | trigram 对中文按三字滑窗切分，效果等价 ngram-2；建立在 `chunk_text` 上 |
| 向量库 | Compose 中的 Qdrant，collection `campusclaw_chunks`，余弦 | **相同** | 向量主键 = `knowledge_chunks.id`；payload 仅标识；**无宿主机端口映射** |
| 嵌入 | 课程网关，OpenAI 兼容 `/embeddings` | OpenAI 兼容 `/embeddings` 网关，env 配置 | `EMBEDDING_API_BASE` / `EMBEDDING_API_KEY` / `EMBEDDING_MODEL`；维度须与 collection 一致 |
| 对话生成 | 课程网关，OpenAI 兼容 chat | OpenAI 兼容 chat 网关，env 配置 | `CHAT_API_BASE` / `CHAT_API_KEY` / `CHAT_MODEL`；仅命中切片后调用 |
| 混合排序 | RRF（k = 60），两路先按绝对分数过滤 | **相同** | 名次分不是相关性阈值，缺席一路不贡献分数 |

**网关未配置的处理：** 未提供嵌入密钥/地址时，向量与混合模式按「向量路径不可用」处理（检索接口 503；问答接口回退为固定文案语义见 spec）；关键字检索不依赖网关，始终可用。这使无网关密钥的演示环境仍可验收关键字检索与隔离行为。

---

## 数据模型

### 新表 `knowledge_chunks`

| 字段 | 说明 |
| --- | --- |
| `id` | 主键；同时作为向量库中的向量主键 |
| `knowledge_entry_id` / `material_id` | 关联知识库条目与材料 |
| `class_id` | 冗余班级字段，供回表过滤与核对 |
| `chunk_index` | 切片序号（从 0 或 1 起，实现固定并写入 README） |
| `chunk_text` | 切片正文（摘录来源） |
| `start_offset` / `end_offset` | 在待切分文本中的字符区间 |
| `strategy` | 本次切分使用的策略（`auto`/`custom`/`hierarchy`） |
| `index_status` | `ready` / `failed`；仅 `ready` 参与检索 |

- FTS5 虚表 `knowledge_chunks_fts(chunk_text)`（trigram 分词），与主表行同步维护（同事务写入/删除）。
- `knowledge_entries.body_text` 始终为上传原文，预处理不改写；切片偏移相对于预处理后的文本。

### 向量库记录

- Collection `campusclaw_chunks`，余弦度量，维度与嵌入模型一致。
- 向量主键 = `knowledge_chunks.id`；payload 仅 `class_id`、`material_id`、`knowledge_entry_id`、`chunk_id`、`chunk_index`，**不含正文**。
- 关联不变式：向量主键 = `knowledge_chunks.id` = `payload.chunk_id`。

---

## 上传后的入库流程（在第 3 课链路后追加）

```
教师上传 → 落盘 + materials/knowledge_entries 事务提交（第 3 课行为，不变）
  → 检索模块读取 body_text（不改写原文）
  → 按本次策略切分 → 写入 knowledge_chunks（先删旧切片再写新记录）
  → 同步维护 FTS5 行
  → 逐切片调用嵌入网关
  → 写入 Qdrant（向量主键 = 切片主键）
```

- 嵌入失败：材料与切片记录保留，受影响切片标 `index_status = failed`，不写入不完整的向量数据；这批切片仍可被关键字检索排除在外的部分按 spec 处理（failed 不参与任何检索）。
- 教师可对既有材料**重建索引**：先删除旧切片与旧向量记录，再按本次请求策略重新执行上述流程；未指定策略按 `auto`。

---

## 检索时的三条路径

`GET /api/search?q=<问句>&mode=keyword|vector|hybrid`（默认 `hybrid`），登录必需，班级取自会话。

| 模式 | 访问组件 | 排序 |
| --- | --- | --- |
| `keyword` | 仅 SQLite FTS5；`WHERE class_id = 会话班级 AND index_status = 'ready'`；不调用嵌入，不访问 Qdrant | 全文相关度（bm25）降序 |
| `vector` | 问句嵌入 → Qdrant 按 `class_id` 过滤，余弦 < 0.35 丢弃 → 以向量主键回 SQLite 取正文，回表时再以同一会话班级核对 | 余弦相似度降序 |
| `hybrid` | 两路均执行，各路先按绝对分数过滤 | RRF（k = 60）按名次融合；缺席一路不贡献分数 |

- 摘录始终取自 SQLite `chunk_text`；Qdrant payload 中的编号不得单独作为正文来源。
- 空查询（空串或全空白）返回 400。
- Qdrant/嵌入不可用：`keyword` 正常；`vector`/`hybrid` 返回 503，不编造分数。

### 问答接口

`POST /api/ask`（JSON：`question`，可选 `history` 若干轮）：

1. 以最新一句执行本班混合检索，取前 4 条。
2. 无命中 → 直接返回固定文案「资料中未找到相关内容」，`citations` 为空；**不调用对话网关**。
3. 有命中 → 对话网关输入为材料标题、切片序号、切片正文与本轮提问（历史附后）；system 提示由服务端写入，客户端注入的 system 消息丢弃。
4. 回答正文以 [1]、[2] 标注出处，顺序与 `citations` 列表一致。

对话模块的输入由检索模块组装，不得自行访问数据库或向量库；不向其传递向量分量、Qdrant 原始点数据或其他班级切片。

---

## 切分策略

| 策略 | 规则 |
| --- | --- |
| `auto`（默认） | 最大 800 字，重叠 80 字；优先在空行、换行、句号处断开；请求中另行填写的长度与预处理参数不生效 |
| `custom` | 按换行、空行或句号控制粒度；最大长度 100–2000 字，重叠比例 0–50%；无断点处按最大长度强制截断；可选预处理（移除 URL/邮箱、折叠连续空白） |
| `hierarchy` | 按 `#`/`##`/`###` 分章，标题保留在该章切片内；章过长再按 `auto` 窗口切分 |

- 上传与重建索引共用同一组参数；未指定按 `auto`；种子材料启动时补齐索引也用 `auto`。
- 预处理仅作用于待切分/待嵌入文本；`body_text` 保持原样；此时偏移量相对预处理后文本，不能再视作原文件下标。
- 已入库材料不会自动重新切分；更换策略必须显式重建。

---

## 班级隔离（检索侧）

- 认证前置逻辑（第 3 课）将会话中的 `class_id` 写入请求上下文；检索模块**只从该上下文读取班级**。查询串、JSON body、请求头中携带的 `class_id` 解析后一律丢弃。
- 两条路径都带班级条件：FTS5 查询含 `class_id = 会话班级`；Qdrant 查询含 `class_id` 过滤，回表再用同一班级条件核对——单侧过滤不构成隔离。
- 跨班检索对外表现为无命中：HTTP 200 + 空 `hits`（问答接口为固定文案），**不得**以 403/404 暗示资料归属他班。按材料 ID 打开详情沿用第 3 课已固定行为（403）。

---

## Compose 拓扑（新增 qdrant 服务）

```
浏览器 ──► localhost:8088 (web: Nginx) ──► app:8000 (Flask/gunicorn)
              唯一对外端口映射                 │
                                            ├─► qdrant:6333（无 ports，仅内部网络）
                                            └─► 嵌入/对话网关（出站 HTTPS）
```

- `docker-compose.yml` 新增 service `qdrant`（`qdrant/qdrant` 镜像），**不写 `ports`**，向量数据卷持久化（如 `qdrant_storage` named volume）。
- app 新增 env：`QDRANT_URL=http://qdrant:6333`、`EMBEDDING_*`、`CHAT_*`；`.env.example` 列出占位与说明。
- entrypoint/启动时：若 collection 不存在则创建（维度取自嵌入配置）；若 `knowledge_chunks` 为空且库中已有种子/上传材料，按 `auto` 策略补齐索引（嵌入不可用时切片标 `failed`，不阻塞启动）。
- Nginx 不变；Qdrant 与网关均不是浏览器入口。

---

## Decisions（摘要）

| # | 决策 | 备选 |
| --- | --- | --- |
| 1 | Flask + SQLite 沿用，向量库用 Qdrant（对齐课件） | 整体迁 Go+MySQL；或 SQLite 内存向量计算 |
| 2 | FTS5 trigram 做中文关键字检索 | 自建分词 + LIKE；SQLite 无 ngram parser |
| 3 | 向量主键 = 切片主键，payload 仅存标识 | 随机向量主键 + 映射表；payload 存正文副本 |
| 4 | RRF（k=60）按名次融合 | 分数归一化加权求和（换模型需重新标定权重） |
| 5 | 跨班检索表现为无命中（200 空） | 返回 403（泄露资源存在性） |
| 6 | 嵌入/对话走 env 配置的 OpenAI 兼容网关；未配置时向量路径降级 503 | 本地嵌入模型（镜像体积与效果不可控） |
| 7 | qdrant 服务无宿主机端口映射 | 映射 6333 便于调试（客户端可绕过认证直连） |

## Risks / Trade-offs

- [无网关密钥的演示环境] → 关键字检索与隔离行为仍可验收；向量/混合按 spec 降级 503，验收记录注明。
- [FTS5 trigram 索引体积] → 材料量级小，可接受；仅索引 `chunk_text`。
- [trigram 不支持 <3 字符的词] → 中文双字词常见，短词自动降级为 LIKE 子串匹配（按出现次数排序），长词仍走 FTS5 bm25；两种结果按分数合并。
- [无空格长问句整句无命中] → 对 ≥4 字的词追加滑窗二字词作 OR 条件（命中的仍是原文真实出现的词，同义改写依旧落空），自然问句可直接检索。
- [重建索引期间检索旧切片] → 重建在单事务内先删后写切片表，向量删除先行；短暂不一致以 `index_status` 兜底。
- [维度变更] → 更换嵌入模型须重建 collection 与全部向量，README 注明。

## Migration Plan

- 新表与 FTS5 虚表由 `init_db.py` 建表逻辑扩展；既有 `data/app.db` 通过启动时的轻量迁移（`CREATE TABLE IF NOT EXISTS`）兼容。
- 既有种子材料与已上传材料：启动时检测无切片则按 `auto` 补齐索引。
- 实现顺序见 `tasks.md`（数据模型 → 切分 → 嵌入/向量库 → 三种检索 → 问答 → Compose → 页面 → validate）。

## Open Questions

- 嵌入/对话网关的可用端点与密钥来源（课程网关或自配）——spec 不依赖具体取值，实现时经 `.env` 注入。

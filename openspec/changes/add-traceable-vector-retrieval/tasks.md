# Tasks: add-traceable-vector-retrieval

> Apply 已完成：29 项自动化测试全部通过（`python tests/test_lesson4.py`），并经 Compose 端到端实证（8088 检索/问答、qdrant 与 app 均不暴露、down/up 持久化）。

## 1. 数据模型与切分（T1）

- [x] 1.1 扩展 `scripts/init_db.py`：新增 `knowledge_chunks` 表（id、entry/material/class 关联、chunk_index、chunk_text、start/end_offset、strategy、index_status）与 FTS5 trigram 虚表 — verify: 执行后 `.schema` 含两表；既有库经启动迁移可升级
- [x] 1.2 实现切分模块：`auto`（800 字/重叠 80，优先空行、换行、句号断开）、`custom`（100–2000 字，重叠 0–50%，无断点强制截断，可选预处理）、`hierarchy`（Markdown 标题分章，过长章再按 auto） — verify: 同一份带标题正文分别用三策略切分，条数与偏移符合 design 规则
- [x] 1.3 预处理不改写原文：移除 URL/折叠空白仅作用于待切分文本 — verify: 切分后 `knowledge_entries.body_text` 与上传原文逐字节一致

## 2. 嵌入与向量库（T2）

- [x] 2.1 封装嵌入网关调用（OpenAI 兼容 `/embeddings`，`EMBEDDING_API_BASE/KEY/MODEL` 来自环境变量） — verify: 未配置密钥时调用方得到明确错误而非异常崩溃
- [x] 2.2 Compose 新增 `qdrant` 服务（无 `ports`，named volume 持久化）；app 增加 `QDRANT_URL` — verify: `docker compose up -d` 后宿主 `curl http://localhost:6333/` 连接失败；app 容器内可访问
- [x] 2.3 启动时确保 collection `campusclaw_chunks` 存在（余弦、维度与嵌入配置一致） — verify: 删除 collection 后重启自动重建
- [x] 2.4 上传事务提交后追加索引链路：切分 → 写切片表 + FTS5 → 逐条嵌入 → 写向量（向量主键 = 切片主键）；嵌入失败切片标 `failed` — verify: 对照两库验证主键三者一致；断开网关上传，材料保留、切片 failed、向量库无记录
- [x] 2.5 启动时为无切片的既有/种子材料按 `auto` 补齐索引；嵌入不可用标 `failed` 不阻塞启动 — verify: 清空切片表重启后切片恢复

## 3. 三种检索模式（T3）

- [x] 3.1 实现 `GET /api/search?q=&mode=`（默认 `hybrid`），登录必需；空查询 400 — verify: 未登录 401/重定向；`q=""` 返回 400
- [x] 3.2 `keyword`：仅查 FTS5（`class_id = 会话班级 AND index_status = 'ready'`），不调用嵌入、不访问 Qdrant，按相关度排序 — verify: 原词命中；嵌入网关断开时仍 200
- [x] 3.3 `vector`：问句嵌入 → Qdrant 按 `class_id` 过滤 → 余弦 < 0.35 丢弃 → 回表取正文并再核对班级 — verify: 同义改写可命中；回表班级不符的记录不出现
- [x] 3.4 `hybrid`：两路独立过滤后 RRF（k=60）按名次融合，缺席一路不贡献分数 — verify: 双路命中切片排名高于单路命中
- [x] 3.5 命中结构含材料标题、切片序号、字符区间、摘录；摘录取自切片表；响应不含向量分量 — verify: 摘录与 `chunk_text` 一致；响应 JSON 无向量字段

## 4. 问答接口（T4）

- [x] 4.1 实现 `POST /api/ask`：最新一句 → 本班混合检索前 4 条 → 有命中才调用对话网关（`CHAT_API_BASE/KEY/MODEL`），system 由服务端写入 — verify: 有依据的问题回答含 [1]/[2] 且与 citations 顺序一致
- [x] 4.2 无命中返回固定文案「资料中未找到相关内容」，citations 为空，不调用对话网关 — verify: 问天气类问题返回 200 固定文案；网关调用日志/计数为零
- [x] 4.3 客户端携带的 system 消息丢弃；历史对话附于其后 — verify: 注入恶意 system 后回答仍仅依据切片

## 5. 检索侧班级隔离（T5）

- [x] 5.1 班级仅取自会话上下文；query/body/header 中的 `class_id` 解析后丢弃 — verify: A 班请求体写 B 班 `class_id` 检索 B 班专属词，返回 200 空 hits
- [x] 5.2 跨班检索对外表现为无命中（200 空），不返回 403/404 — verify: 同上用三种模式各验一次
- [x] 5.3 两条路径均带班级条件且回表再核对 — verify: 代码审查 + 构造向量库中他班记录，回表后被排除

## 6. 索引重建接口（T6）

- [x] 6.1 教师重建接口：先删旧切片与旧向量，再按本次策略重切、嵌入、写入 — verify: auto 入库后以 hierarchy 重建，切片条数与策略标记变化，向量库旧主键清除
- [x] 6.2 学生调用重建返回 403 且两库无变更 — verify: 学生 A1 调用后切片表行数不变

## 7. 页面与文档（T7）

- [x] 7.1 材料列表页增加检索框（模式可选）与问答面板，命中可跳转材料详情；页面不展示向量分量 — verify: 浏览器走完 检索→打开材料 链路
- [x] 7.2 README 更新：三种检索模式说明、`.env` 新变量、网关未配置时的降级行为 — verify: 按 README 可完成配置与验证

## 8. 规约与收尾（T8）

- [x] 8.1 运行 `openspec validate add-traceable-vector-retrieval --strict` — verify: exit 0 且无 error
- [x] 8.2 手工对照 spec 关键 Scenario：跨班空命中、无切片不调模型、Qdrant 停止后 keyword 可用/vector 503 — verify: 记录三条验收结果于实验报告

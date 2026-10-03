# CampusClaw

> 北京大学《互联网软件开发技术与实践》课程项目（2026 年秋，主讲：张齐勋）。
> 本仓库是课程实训作业：以 SDD（规约驱动开发）方式，借助 AI 编程工具逐课迭代实现。

## 项目简介

- **价值**：面向中小学的教研智能体，教师登录后按班级上传与管理教学材料，本班成员可用自然语言检索材料并回溯出处，为智能问答打底。
- **场景**：教师、学生账号密码登录；班级是数据边界，A 班用户看不到 B 班材料；教师上传材料入库，本班列表可查，学生只读；本班材料支持关键字/向量/混合检索与带出处标注的问答。
- **不做**：流式长对话、重排序、LangChain 类编排框架、作业提交与批改、注册与找回密码、SSO 与生产级高可用（详见 openspec 中 proposal 的 Non-goals）。

## 仓库结构

- `app/` — Flask 应用（登录会话、班级隔离、材料上传入库、切分与检索、问答编排）
- `scripts/` — 数据库初始化与种子数据（班级 A/B、teacher_a、student_a1/b1）
- `deploy/` — Nginx 反向代理配置（Compose 部署）
- `openspec/` — 规约驱动开发（SDD）的 change 规约与归档，所有功能先规约后实现
- `ppt/` — 课件 Markdown 整理版（整理规范见 `ppt/AGENTS.md`）
- `docs/` — 设计参考资料与作业材料

## 运行方式

### 标准启动：Docker Compose（web + app 双服务）

```bash
cp .env.example .env      # 然后编辑 .env，填入 SECRET_KEY
docker compose up --build
```

- 登录页：http://localhost:8088/login （预置账号：`teacher_a` / `teach123`，`student_a1` / `stu123`）
- 健康检查：http://localhost:8088/health （无需登录）
- 拓扑：浏览器 → `web`（Nginx，唯一对外端口 8088）→ 内部网络 → `app`（gunicorn 8000，**不映射端口、宿主不可直连**）

首次启动若数据库不存在，entrypoint 会自动执行 `scripts/init_db.py` 建表并写入种子数据。`docker compose down` 后再 `up`（不加 `-v`），数据经 `./data`、`./uploads` 与 `qdrant_storage` 卷持久化。

### 第 4 课：检索与问答

- 拓扑新增 `qdrant` 服务（向量库，**不映射宿主机端口**，仅 Compose 内部可达）；向量主键 = `knowledge_chunks.id`，payload 只存标识不含正文。
- 检索接口：`GET /api/search?q=...&mode=keyword|vector|hybrid`（默认 hybrid，RRF k=60，向量余弦阈值 0.35）；问答接口：`POST /api/ask`（本班混合检索前 4 条，无命中返回「资料中未找到相关内容」且不调用对话模型）。
- 班级只取自登录会话：请求中携带的 `class_id` 一律丢弃；跨班检索表现为 200 空命中，不返回 403/404。
- 切分策略：`auto`（默认 800 字/重叠 80）、`custom`（100–2000 字，重叠 0–50%）、`hierarchy`（Markdown 标题分章）；教师可 `POST /api/materials/<id>/reindex` 按新策略重建索引。
- 关键字检索用 SQLite FTS5 trigram；**不足 3 字符的短词**（如「集合」）trigram 无法索引，自动降级为 LIKE 子串匹配兜底；无空格的长中文问句（如「磁铁能吸木块吗」）自动按滑窗二字词扩展为 OR 条件，命中的仍是原文中真实出现的词。
- 登录认证为双凭证：Cookie 会话 + Bearer Token（JWT HS256，2 小时有效）。`POST /api/login` 返回 `access_token`，前端保存于 localStorage，检索/问答等 API 请求携带 `Authorization: Bearer` 头；令牌无效或过期返回 401，角色与班级仅从已验证凭证读取。
- 网关配置在 `.env`（见 `.env.example`）：未配置嵌入网关时，`keyword` 模式仍可用，`vector`/`hybrid` 返回 503，问答返回固定文案——不编造分数或出处；更换嵌入模型（维度变化）须清空 `qdrant_storage` 卷并重建索引。

### 本地开发（单进程）

```bash
pip install -r requirements.txt
python scripts/init_db.py   # 初始化 SQLite 并写入种子数据
python run.py               # 启动开发服务（http://localhost:8080）
```

健康检查：`GET /health`（无需登录）。

## 课程进度

- 第 2 课：OpenSpec 初始化，编写 `add-auth-rbac-class-knowledge` 变更规约四件套（proposal / design / specs / tasks）
- 第 3 课：按规约实现登录、班级隔离、上传入库与文件下载，逐条验收；Docker Compose 双服务部署（Nginx 反代 + 后端不暴露端口）并归档规约
- 第 4 课：新增 `add-traceable-vector-retrieval` 规约并实现——正文切分（auto/custom/hierarchy）、SQLite FTS5 + Qdrant 双库存储、关键字/向量/混合（RRF）三种检索、命中溯源、`/api/ask` 带出处标注的问答、检索侧班级隔离与故障降级
- 0930 课堂任务：`add-bearer-token-auth`——登录签发 JWT、API 接受 Bearer 与 Cookie 双凭证；基于知识库的 AI 问答演示（问答面板 + [1] 出处标注），演示用抽取式 stub 网关 `scripts/dev_stub_gateway.py`

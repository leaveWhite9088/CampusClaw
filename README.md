# CampusClaw

> 北京大学《互联网软件开发技术与实践》课程项目（2026 年秋，主讲：张齐勋）。
> 本仓库是课程实训作业：以 SDD（规约驱动开发）方式，借助 AI 编程工具逐课迭代实现。

## 项目简介

- **价值**：面向中小学的教研智能体，教师登录后按班级上传与管理教学材料，材料解析后写入知识库，为后续检索与智能问答打底。
- **场景**：教师、学生账号密码登录；班级是数据边界，A 班用户看不到 B 班材料；教师上传材料入库，本班列表可查，学生只读。
- **不做**：检索问答、AI 对话助手、作业提交与批改、注册与找回密码、SSO 与生产级高可用（详见 openspec 中 proposal 的 Non-goals）。

## 仓库结构

- `app/` — Flask 应用（登录会话、班级隔离、材料上传入库）
- `scripts/` — 数据库初始化与种子数据（班级 A/B、teacher_a、student_a1/b1）
- `deploy/` — Nginx 反向代理配置（Compose 部署）
- `openspec/` — 规约驱动开发（SDD）的 change 规约与归档，所有功能先规约后实现
- `ppt/` — 课件 Markdown 整理版（整理规范见 `ppt/AGENTS.md`）
- `docs/` — 设计参考资料

## 运行方式

### 标准启动：Docker Compose（web + app 双服务）

```bash
cp .env.example .env      # 然后编辑 .env，填入 SECRET_KEY
docker compose up --build
```

- 登录页：http://localhost:8088/login （预置账号：`teacher_a` / `teach123`，`student_a1` / `stu123`）
- 健康检查：http://localhost:8088/health （无需登录）
- 拓扑：浏览器 → `web`（Nginx，唯一对外端口 8088）→ 内部网络 → `app`（gunicorn 8000，**不映射端口、宿主不可直连**）

首次启动若数据库不存在，entrypoint 会自动执行 `scripts/init_db.py` 建表并写入种子数据。`docker compose down` 后再 `up`（不加 `-v`），数据经 `./data`、`./uploads` 卷持久化。

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

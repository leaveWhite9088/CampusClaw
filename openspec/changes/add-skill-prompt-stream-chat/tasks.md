# Tasks: add-skill-prompt-stream-chat

> Apply 已完成：tests/test_lesson5.py 11 项全过（第 4 课 37 项回归不破）；apitest 6/6 用例（44 项检查）全过；Compose 端到端实证（8088 提示词/技能/SSE 问答/openapi.json/Swagger 页面）。

## 1. 数据模型与迁移（T1）

- [x] 1.1 `init_db.py` 与启动迁移：新增 `class_prompts`、`conversations`、`messages` 表；`skills` 表扩展 `description`/`instructions`/`enabled`/`updated_at` 列 — verify: 新库 `.schema` 含全部表列；旧库启动后自动补齐
- [x] 1.2 种子：A/B 班各一条「解题引导」技能（默认停用）— verify: 库中 skills 有两条含 instructions 的记录

## 2. 提示词与技能 API（T2）

- [x] 2.1 `GET /api/prompt`（登录可读）与 `PUT /api/prompt`（教师）：保存后库中可查、下一轮回答生效 — verify: 学生 PUT 403 且库无变更；教师 PUT 后 GET 一致
- [x] 2.2 `GET/POST /api/skills`、`PATCH /api/skills/<id>`（教师写）：新建/启用/停用；跨班 403 — verify: 学生写 403；启用后 GET 列表 enabled=1

## 3. 会话与 SSE（T3）

- [x] 3.1 `POST/GET /api/conversations`、`GET /api/conversations/<id>/messages`：归属本人本班 — verify: 他人会话 403/404；列表仅本人
- [x] 3.2 `POST /api/conversations/<id>/messages` SSE：delta 若干 + citations + done；拼接 delta == 落库 assistant 内容；空提问 400 — verify: 测试解析事件流并比对 DB
- [x] 3.3 编排：system = 班级提示词 + 启用技能指令 + 编号资料；历史取最近 6 条；客户端 system 丢弃 — verify: stub 网关收到的 messages 含三者且无注入
- [x] 3.4 无命中固定文案不调网关；向量路径不可用时关键字兜底并标 `degraded` — verify: 天气类提问 citations 为空且 stub 无调用记录

## 4. 页面（T4）

- [x] 4.1 `/settings` 教师页：提示词编辑保存、技能列表开关与新建；学生访问被拒 — verify: 教师保存后 GET 一致；学生 302/403
- [x] 4.2 `/ask` 学生页：会话列表、新对话、SSE 逐段渲染、出处卡片；材料页加入口 — verify: 浏览器走完提问→流式回答→出处链路

## 5. OpenAPI 与 Swagger（T5）

- [x] 5.1 手写 `openapi.json`（3.x）：全部 API 路径 + 入参出参 + 错误码 + security（bearerAuth/cookieAuth），静态服务于 `/openapi.json` — verify: `curl /openapi.json` 合法 JSON 且含 login/search/ask/prompt/skills/conversations
- [x] 5.2 vendor swagger-ui 到 `app/static/vendor/`，`/swagger` 页面离线可开可试调 — verify: 断网打开页面渲染文档

## 6. apitest（T6）

- [x] 6.1 `apitest/lib.py` + 用例：`login/POST`、`search/GET`、`prompt/PUT`、`skills/POST`、`conversations/POST`、`conversations/_id_/messages/POST` — verify: 各用例含 DB 一致性核对
- [x] 6.2 `run_all.py`：临时实例 + stub 网关一键跑完，HTML 报告入 `apitest/reports/`（gitignore）— verify: 全新环境一键全绿；`git status` 不出现报告文件

## 7. 测试与收尾（T7）

- [x] 7.1 `tests/test_lesson5.py`：提示词权限、技能权限与注入、会话归属、SSE 事件序列、无命中不调模型、openapi.json 合法 — verify: 全过且第 4 课回归不破
- [x] 7.2 Compose e2e：8088 走完 教师存提示词→启用技能→学生会话流式问答→出处；Swagger 页面试调 — verify: 记录结果
- [x] 7.3 `openspec validate add-skill-prompt-stream-chat --strict` — verify: exit 0

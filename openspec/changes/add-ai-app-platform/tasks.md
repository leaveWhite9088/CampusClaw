# Tasks: add-ai-app-platform

## 1. 数据层

- [ ] 1.1 启动迁移 + `init_db.py`：新增 `prompt_templates`、`ai_apps`、`llm_call_logs` 表；`skills` 加 `applicable`/`tools`/`source` 列；`conversations` 加 `app_id` 列（幂等）— verify: 新旧库启动后列齐全
- [ ] 1.2 种子：每班 3 个内置模板、3 条内置技能（含既有「解题引导」）、3 个内置应用 — verify: 初始化后各表行数符合

## 2. 对话编排与调用日志

- [ ] 2.1 `chat.render_system`：模板渲染（`{{skills}}`/`{{knowledge}}`，缺省追加）+ 固定边界句 — verify: 单测覆盖占位符与缺省两种形态
- [ ] 2.2 `generate_answer` 扩展：`log_context` 写 `llm_call_logs`（成功/失败均留痕），`extra_user_blocks` 预留工具数据块 — verify: 单测断言日志行字段
- [ ] 2.3 会话消息路由：`app_id` 会话取应用绑定（模板/技能/材料子集），旧会话走班级提示词 — verify: 单测断言 stub 收到的 system 与资料范围

## 3. API

- [ ] 3.1 `/api/templates` CRUD：教师写、全班读、跨班不可见 — verify: 学生写 403
- [ ] 3.2 `/api/apps` CRUD + `POST /api/apps/<id>/conversations`：绑定校验（模板/技能/材料属本班）、内置不可删 — verify: 跨班绑定 400；学生写 403
- [ ] 3.3 `POST /api/skills/upload`：`.md`/`.json` 解析、必填校验、工具引用校验 — verify: 合法文件 201 入库；缺名称/坏引用 400
- [ ] 3.4 `/api/llm-logs` 列表与详情：仅教师、仅本班 — verify: 学生 403；B 班看不到 A 班日志

## 4. 页面

- [ ] 4.1 `/apps` 应用列表 + 教师新建/删除；`/apps/<id>` 应用内对话页（SSE + 出处） — verify: 浏览器走通
- [ ] 4.2 `/settings` 页签化：提示词 / 模板 / 技能（新建 + 上传）/ 调用日志详情 — verify: 上传文件后列表出现技能；日志详情完整显示 request_json

## 5. 测试与收尾

- [ ] 5.1 `tests/test_lesson6.py` 全过；第 4/5 课回归不破 — verify: `python tests/test_lesson4.py && python tests/test_lesson5.py && python tests/test_lesson6.py`
- [ ] 5.2 `apitest/` 新增用例全绿并出 HTML 报告 — verify: `python apitest/run_all.py`
- [ ] 5.3 `openapi.json` 补充新路径 — verify: `/swagger` 可见并可试调

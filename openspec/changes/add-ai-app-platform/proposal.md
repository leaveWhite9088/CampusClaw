# Change: add-ai-app-platform

## Why

个人项目验收要求平台「内置多个 AI 应用、支持提示词模板、支持知识库检索、支持内置 Skill 并支持上传技能」。第 5 课只有单一解题助手（一个班级提示词 + 技能开关），不具备「应用」这一层：无法在同一个班里并存多个用途不同、绑定不同模板/技能/资料范围的 AI 应用；提示词只有班级级一条、不可模板化复用；技能只能表单手工录入、不能按课程技能文件格式上传。同时，验收要求逐项回答「每次请求传给 LLM 的具体参数与返回」，当前系统不留任何调用痕迹，无法取证。

## What Changes

- **AI 应用**：新增 `ai_apps` 表与 `/api/apps` CRUD。每个应用绑定一个提示词模板、若干技能、可选的材料子集（空 = 本班全部材料）；每班预置 3 个内置应用（资料问答助手 / 解题引导助手 / 作文点评助手）。学生从 `/apps` 进入应用发起会话，会话归属应用；会话内问答沿用第 5 课 SSE 流式与出处标注。
- **提示词模板**：新增 `prompt_templates` 表与 `/api/templates` CRUD；每班预置 3 个内置模板。模板正文支持 `{{skills}}` 与 `{{knowledge}}` 占位符（未写占位符时按固定顺序追加），应用渲染模板后作为 system 消息发给 LLM。
- **技能增强**：`skills` 表扩展 `applicable`（适用条件关键词）、`tools`（工具白名单，本 change 先支持 `knowledge_search`）、`source`（built_in / uploaded / manual）；每班预置多条内置技能；新增 `POST /api/skills/upload` 按课程技能文件格式（`名称：/适用条件：/工具：/启用：` 头部 + 正文指令）或 JSON 上传创建技能。
- **LLM 调用日志**：新增 `llm_call_logs` 表；每次调用对话网关（`/api/ask` 与会话消息）都完整记录请求 JSON（messages 等全部参数）、返回内容、模型名、知识库总量与实际传入切片量、所用模板与技能清单、状态。教师可在 `/settings` 调用日志页查看，作为验收取证依据。
- **沿用语义**：班级只取自会话、跨班不可见、Bearer + Cookie 双凭证、无命中不调模型——全部不变。

## Capabilities

### New Capabilities

- `ai-app-platform`：AI 应用与提示词模板的维护与绑定、技能上传、应用内会话、LLM 调用日志的可验收行为。

### Modified Capabilities

- `assistant-chat`：会话增加可选 `app_id` 绑定；发往 LLM 的 system 组装从「班级提示词 + 技能」改为「模板渲染 + 技能」（无应用会话以班级提示词充当模板，行为向后兼容）。

## Impact

- 数据层：新增 `ai_apps`、`prompt_templates`、`llm_call_logs` 表；`skills` 表加 `applicable`/`tools`/`source` 列；`conversations` 表加 `app_id` 列。
- 服务层：新增应用/模板/技能上传/调用日志四组 API；对话编排改为模板渲染并写调用日志。
- 页面：`/apps` 应用列表页、`/apps/<id>` 应用对话页；`/settings` 改为分页签（提示词 / 模板 / 技能+上传 / 调用日志）。
- 测试：`tests/test_lesson6.py` 与 `apitest/` 新增用例。

## Non-goals（非目标）

- 不做应用市场/跨班共享应用；模板不做版本历史。
- 不做模型自主选工具（Function Calling）；工具白名单由教师配置（MCP 引用在 `add-mcp-tools` 落地）。
- 不做流式 token 级直传（沿用第 5 课分段推送）。

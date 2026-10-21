# Design: add-ai-app-platform

## 数据模型

```sql
CREATE TABLE IF NOT EXISTS prompt_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    class_id INTEGER NOT NULL REFERENCES classes(id),
    name TEXT NOT NULL,
    content TEXT NOT NULL,
    built_in INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS ai_apps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    class_id INTEGER NOT NULL REFERENCES classes(id),
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    template_id INTEGER REFERENCES prompt_templates(id),
    skill_ids TEXT NOT NULL DEFAULT '[]',      -- JSON 数组
    material_ids TEXT NOT NULL DEFAULT '[]',   -- JSON 数组；空 = 本班全部材料
    built_in INTEGER NOT NULL DEFAULT 0,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS llm_call_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    class_id INTEGER NOT NULL REFERENCES classes(id),
    user_id INTEGER REFERENCES users(id),
    conversation_id INTEGER REFERENCES conversations(id),
    app_id INTEGER REFERENCES ai_apps(id),
    source TEXT NOT NULL DEFAULT 'conversation',  -- conversation | ask
    model TEXT NOT NULL DEFAULT '',
    request_json TEXT NOT NULL,                   -- 发给网关的完整 JSON 请求体
    response_text TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'ok' CHECK (status IN ('ok','error')),
    error TEXT NOT NULL DEFAULT '',
    template_name TEXT NOT NULL DEFAULT '',
    skill_names TEXT NOT NULL DEFAULT '[]',       -- 本轮注入指令的技能名（JSON 数组）
    tool_calls TEXT,                              -- 预留：MCP 调用清单（add-mcp-tools 填写）
    kb_total_chunks INTEGER NOT NULL DEFAULT 0,   -- 本班（或应用绑定范围）知识库切片总量
    kb_total_chars INTEGER NOT NULL DEFAULT 0,
    kb_passed_chunks INTEGER NOT NULL DEFAULT 0,  -- 实际传入 LLM 的切片数
    kb_passed_chars INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
```

- `skills` 扩展列（启动迁移幂等补齐）：`applicable TEXT DEFAULT ''`、`tools TEXT DEFAULT 'knowledge_search'`、`source TEXT DEFAULT 'manual'`。
- `conversations` 扩展列：`app_id INTEGER NULL`（NULL = 第 5 课旧路径，班级提示词充当模板）。
- 班级边界：三张新表都带 `class_id`；应用绑定校验（模板/技能/材料必须属于本班）在服务端完成。

## 模板渲染（system 组装）

`chat.py` 新增纯函数 `render_system(template_content, skills_block, refs_block)`：

1. `template = template_content or 班级提示词 or 内置默认模板`；
2. 将模板中的 `{{skills}}` 替换为技能指令块、`{{knowledge}}` 替换为编号资料块；模板未出现的占位块按「技能 → 资料」顺序追加在末尾；
3. 末尾始终拼接固定边界句（SYSTEM_PROMPT：仅依据资料、`[编号]` 标注出处）。

向后兼容：第 5 课用例断言 system 含「提示词标记 + 技能标记 + `[1]`」——渲染结果天然满足。

## 调用日志

`chat.generate_answer` 扩展签名，新增可选 `log_context`（class_id / user_id / conversation_id / app_id / source / template_name / skill_names / kb_stats / tool_calls）。发送前后各取一次状态，单次调用写一行 `llm_call_logs`（成功记完整请求 JSON 与返回文本；失败记 error）。`request_json` 就是实际发出的 HTTP 请求体（`model` + `messages` + `stream`），保证「验证 1/2/3/5」可直接以日志为证。

## 技能上传解析

`skillfile.py` 纯函数 `parse_skill_text(filename, text)`：

- `.md/.txt`：逐行解析头部 `键：值`（支持全角冒号），遇到空行后其余全部作为 instructions 正文。键集合：`名称`（必填）、`简介`、`适用条件`（逗号/顿号分隔）、`工具`（逗号/顿号/分号/竖线分隔，逐项校验格式与可达性）、`启用`（是/否，默认否）。未知键忽略，缺 `名称` 或正文为空返回错误。
- `.json`：字段 `name`（必填）、`description`、`instructions`（必填）、`applicable`、`tools`、`enabled`。

工具白名单本 change 仅接受 `knowledge_search` 与格式合法的 `tool@server` 引用（引用校验在 `add-mcp-tools` 扩展为「服务器已连接且工具已发现」；本 change 阶段对未知服务器引用直接拒绝，语义不变）。

## 页面

- `/apps`：应用卡片（名称、简介、绑定模板/技能/资料范围），点击进入；教师可见「新建应用」表单（模板下拉、技能多选、材料多选）与删除（内置应用不可删）。
- `/apps/<id>`：会话式对话页（复用第 5 课交互），顶部展示应用绑定信息。
- `/settings`：改为页签式——班级提示词 / 提示词模板 / 技能（新建 + 上传文件）/ 调用日志（列表 + 详情，`request_json` 以 `<pre>` 完整展示）。

## API 一览

| 方法与路径 | 权限 | 说明 |
| --- | --- | --- |
| `GET /api/templates` | 登录 | 本班模板列表 |
| `POST /api/templates`、`PUT/DELETE /api/templates/<id>` | 教师 | 模板 CRUD；内置模板可改不可删 |
| `GET /api/apps` | 登录 | 本班应用列表 |
| `POST /api/apps`、`PUT/DELETE /api/apps/<id>` | 教师 | 应用 CRUD；绑定校验；内置不可删 |
| `POST /api/apps/<id>/conversations` | 登录 | 在应用下新建会话 |
| `POST /api/skills/upload` | 教师 | 上传技能文件（multipart `file`） |
| `GET /api/llm-logs`、`GET /api/llm-logs/<id>` | 教师 | 调用日志列表/详情（本班） |

## 测试

- `tests/test_lesson6.py`：模板/应用 CRUD 权限与绑定校验、应用会话编排（stub 网关断言 system 含模板标记与技能标记、knowledge 只含前 4 切片）、技能上传解析与校验、调用日志落库与字段完整性、旧路径回归（`app_id=NULL` 会话行为不变）。
- `apitest/`：`templates/POST`、`apps/POST`、`skills/upload/POST`、`llm-logs/GET`，均含 DB 一致性核对。

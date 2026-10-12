# 第 5 课配套原型（week05）

> 来源：北京大学《互联网软件开发技术与实践》第 5 课配套原型。原型为线上动态应用（React 打包 SPA），无法离线转为信息文档，本文件仅作索引说明。

- 原型地址：<https://devops.hello1023.com/week05/login>
- 接口文档：<https://devops.hello1023.com/week05/swagger/>（OpenAPI 描述：<https://devops.hello1023.com/week05/openapi.json>）
- 用途：第 5 课「提示词、AI 技能与流式会话」的可交互参照。任务清单中各项功能（解题助手、Swagger 文档、接口测试）可对照该原型理解预期效果。

## 已知页面（前端路由）

| 路由 | 功能 |
| --- | --- |
| `/login` | 登录页；提供演示账号快捷填充 |
| `/materials` | 班级材料：列表/网格视图、按标题搜索、上传 `.txt` / `.md`、材料详情与下载原文件 |
| `/search` | 资料检索（个人资料 / 本班资料 / 资源库，含目录管理） |
| `/ask` | 解题助手对话：新对话、最近对话列表，回答以 SSE 流式逐段返回并标注引用出处 |
| `/tutor` | 智能体入口（选择智能体后进入提问） |
| `/admin` | 教师后台：班级管理（学生名册）、智能体创建与保存、角色提示词、技能文件维护（新建/上传 `.md` / `.txt`、启用开关） |

## 主要功能特征（从前端 bundle 的界面文案归纳）

- 登录后用 Bearer 令牌访问接口；未登录或会话失效会回到登录页。
- 材料详情页可查看「向量数据」：展示 MySQL 切片与向量库记录的对应关系（`knowledge_chunks.id` = 向量主键 = `payload.chunk_id`），可展开向量分量与维度；教师可「按当前策略重建向量」。
- 分段策略三种：自动分段（默认最大 800 字、重叠 80 字）、自定义分段（分隔符/最大长度/重叠比例/文本清洗）、按标题层级分段（Markdown `#`/`##`/`###`）。
- 解题助手预置引导式提问示例（方程、几何、古诗等场景，均强调「先别告诉我得数」）；内置「数学解题引导」技能示例。
- 另有「我的错题本」「智能批改」「自助学习」入口，界面标注「随后开放」，本课不验收。

## 主要接口（bundle 中出现）

`POST /api/login`、`POST /api/logout`、`GET /api/me`、`GET /api/demo-accounts`、`GET /api/class/students`、`GET/POST /api/agents`、`GET/POST /api/skills`、`POST /api/conversations/{id}/messages`（SSE，`Accept: text/event-stream`）、`/api/me/folders`、`/api/me/notes`、`/api/me/resources`、`/api/resources` 等。完整定义以 Swagger 页面与 `openapi.json` 为准。

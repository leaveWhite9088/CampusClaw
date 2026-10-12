# Spec: assistant-chat

## Purpose

在既有登录、班级隔离与本班检索之上提供解题助手：教师维护班级提示词与「解题引导」技能（只引导、不直接给最终答案）；学生新建会话连续追问，回答前先检索本班知识库并标注出处，以 SSE 流式逐段返回；提示词、技能、知识库参与同一次回答；配套 OpenAPI 文档与接口测试。

## ADDED Requirements

### Requirement: 班级提示词维护

系统 MUST 支持教师为本班编写并保存一条提示词（规定助手角色），保存后 MUST 从下一轮对话生效；学生 MUST 不能修改提示词。

#### Scenario: 教师保存提示词并生效

- **WHEN** 教师 A 通过 `PUT /api/prompt` 保存提示词内容
- **THEN** 系统 MUST 将其与本班关联保存（数据库可查）
- **AND** 之后的问答与会话回答 MUST 以该提示词作为 system 提示的一部分

#### Scenario: 学生修改提示词被拒绝

- **WHEN** 学生调用 `PUT /api/prompt`
- **THEN** 系统 MUST 返回 HTTP 403
- **AND** 数据库中的提示词 MUST 无变更

### Requirement: 解题引导技能

系统 MUST 支持教师维护至少一条「解题引导」类技能（名称、一句话简介、完整指令），并可启用或停用；启用时回答 MUST 只引导思路并引用本班材料标题与位置，MUST NOT 直接给出最终答案；停用后同一问题的回答方式 SHOULD 明显不同；学生 MUST 不能新建、修改或开关技能。

#### Scenario: 教师新建并启用技能

- **WHEN** 教师 A 通过 `POST /api/skills` 新建技能并以 `PATCH /api/skills/<id>` 启用
- **THEN** 技能 MUST 入库（名称、简介、指令、enabled=1）
- **AND** 之后本班回答 MUST 把该技能的完整指令注入对话输入

#### Scenario: 学生开关技能被拒绝

- **WHEN** 学生调用 `POST /api/skills` 或 `PATCH /api/skills/<id>`
- **THEN** 系统 MUST 返回 HTTP 403
- **AND** 技能表 MUST 无变更

#### Scenario: 启用与停用的回答差异

- **WHEN** 同一问题分别在技能启用与停用状态下提问
- **THEN** 启用时回答 MUST 遵循技能指令（引导式，含出处指引）
- **AND** 停用时的回答 SHOULD 与启用时明显不同（不再受该指令约束）

### Requirement: 会话管理

系统 MUST 支持学生新建会话、查看自己的会话列表与历史消息；提问与回答 MUST 按会话保存；用户 MUST 只能访问自己的会话。

#### Scenario: 新建会话并保存消息

- **WHEN** 学生 A1 通过 `POST /api/conversations` 新建会话并发送一条消息
- **THEN** 系统 MUST 创建会话记录（归属该用户与本班）
- **AND** 提问与回答 MUST 各写入一条消息记录，回答消息 MUST 携带出处信息（citations）
- **AND** `GET /api/conversations/<id>/messages` MUST 能按序取回这两条消息

#### Scenario: 他人会话不可访问

- **WHEN** 用户访问不属于自己的会话（列表、消息或向其发消息）
- **THEN** 系统 MUST 拒绝（HTTP 403 或 404）
- **AND** 会话列表 MUST 仅含本人会话

### Requirement: SSE 流式回答

`POST /api/conversations/<id>/messages` MUST 以 `text/event-stream` 逐段推送回答：先推送若干 `delta` 事件（回答片段），再推送 `citations` 事件（出处列表），最后推送 `done` 事件；同一次回答 MUST 用上已保存的提示词、已启用的技能指令与本班检索结果。

#### Scenario: 流式事件序列完整

- **WHEN** 学生在会话中发送一条有依据的提问
- **THEN** 响应 Content-Type MUST 为 `text/event-stream`
- **AND** 事件序列 MUST 为一个或多个 `delta`、随后一个 `citations`、最后一个 `done`
- **AND** 全部 `delta` 拼接 MUST 等于最终保存的 assistant 消息内容

#### Scenario: 无命中时不调用生成模型

- **WHEN** 提问在本班材料中无依据（混合检索无候选）
- **THEN** 响应 MUST 流式返回固定文案「资料中未找到相关内容」，`citations` 为空
- **AND** MUST NOT 调用对话网关

#### Scenario: 回答编排三要素齐备

- **WHEN** 教师已保存提示词且启用了技能，学生发送有依据的提问
- **THEN** 发往对话网关的 system 输入 MUST 同时包含班级提示词、技能完整指令与编号资料（材料标题、切片序号、切片正文）
- **AND** 客户端注入的 system 消息 MUST 被丢弃

### Requirement: 沿用检索与隔离语义

会话回答 MUST 沿用第 4 课语义：班级仅从已验证凭证读取；跨班检索表现为无命中；回答中的出处编号顺序 MUST 与 citations 列表一致。

#### Scenario: 跨班内容不出现在回答中

- **WHEN** 学生在会话中提问仅存在于他班材料中的内容
- **THEN** 回答 MUST 为固定文案且 citations 为空
- **AND** MUST NOT 返回 403/404 暗示资料归属

### Requirement: OpenAPI 文档与 Swagger 页面

系统 MUST 提供机器可读的 OpenAPI 描述（覆盖全部 API 路径、入参出参、错误码与是否需要登录），并提供浏览器可打开的 Swagger 页面，可对照文档试调主要接口；Bearer 令牌 MUST 可在页面中配置。

#### Scenario: openapi.json 可取且覆盖主要接口

- **WHEN** 请求 `/openapi.json`
- **THEN** 返回 MUST 为合法 OpenAPI 3.x 文档
- **AND** MUST 至少覆盖登录、检索、问答、提示词、技能、会话与消息接口
- **AND** 每个受保护路径 MUST 声明 security 要求（bearer 或 cookie）

#### Scenario: Swagger 页面可打开可试调

- **WHEN** 浏览器打开 `/swagger`
- **THEN** 页面 MUST 渲染接口文档且离线可用（不依赖外网 CDN）
- **AND** 配置 Bearer 令牌后 MUST 能直接从页面试调登录、检索等主要接口

### Requirement: 接口测试

仓库 MUST 包含 `apitest/`：一个接口一个脚本，目录按 URL 组织（如 `cases/api/login/POST.py` 表示 `POST /api/login`）；`run_all.py` MUST 一键跑完全部用例并生成 HTML 报告；报告文件 MUST NOT 提交到 Git；用例 MUST 不只核对状态码，还要核对返回内容与数据库一致性；覆盖范围 MUST 至少含登录、检索、提示词/技能、创建会话并发送一条消息。

#### Scenario: 一键执行并出报告

- **WHEN** 在仓库根执行 `python apitest/run_all.py`
- **THEN** 全部用例 MUST 顺序执行并输出通过/失败汇总
- **AND** MUST 在 `apitest/reports/` 生成 HTML 报告（该目录被 gitignore）

#### Scenario: 用例核对数据库一致性

- **WHEN** 发送会话消息的用例执行完成
- **THEN** 用例 MUST 直接查询数据库核对消息行（user/assistant 各一、assistant 带 citations）
- **AND** 任一接口返回内容与库中记录不一致时该用例 MUST 判失败

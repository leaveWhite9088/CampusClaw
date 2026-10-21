# Spec: ai-app-platform

## Purpose

在既有登录、班级隔离与本班检索之上提供「个人项目应用平台」底座：同一班级可并存多个内置 AI 应用，应用绑定提示词模板、技能与资料范围；教师可维护模板并按课程技能文件格式上传技能；每次 LLM 调用完整留痕（请求参数、返回内容、知识库与技能注入统计），供验收取证。

## ADDED Requirements

### Requirement: 提示词模板维护

系统 MUST 支持教师为本班维护多条提示词模板（名称、正文），模板正文 MAY 包含 `{{skills}}` 与 `{{knowledge}}` 占位符；每班 MUST 预置至少 3 个内置模板。学生 MUST 不能新建、修改或删除模板。

#### Scenario: 教师创建模板并在列表可见

- **WHEN** 教师通过 `POST /api/templates` 提交名称与正文
- **THEN** 系统 MUST 将模板与本班关联保存（数据库可查），`GET /api/templates` MUST 返回该模板
- **AND** 内置模板 MUST 存在且 `built_in=1`

#### Scenario: 学生写模板被拒绝

- **WHEN** 学生调用 `POST /api/templates` 或 `PUT /api/templates/<id>`
- **THEN** 系统 MUST 返回 HTTP 403 且数据库无变更

### Requirement: AI 应用维护

系统 MUST 支持教师为本班维护多个 AI 应用；每个应用 MUST 可绑定一个提示词模板、若干技能与一个可选的材料子集（空 = 本班全部材料）；绑定对象 MUST 校验属于本班；每班 MUST 预置至少 3 个内置应用。学生 MUST 不能新建、修改或删除应用，但 MAY 查看并在应用内发起会话。

#### Scenario: 教师创建应用并绑定

- **WHEN** 教师通过 `POST /api/apps` 提交名称并绑定本班模板与技能
- **THEN** 应用 MUST 入库且绑定关系可查
- **WHEN** 提交的绑定对象不属于本班
- **THEN** 系统 MUST 返回 400 且不入库

#### Scenario: 内置应用预置

- **WHEN** 全新初始化完成
- **THEN** 每班 MUST 至少存在 3 个 `built_in=1` 的应用，且各自绑定了模板或技能

### Requirement: 应用内会话

用户 MUST 能在指定应用下新建会话；会话 MUST 记录其应用归属；应用内提问的回答 MUST 以该应用绑定的模板渲染 system 消息、注入所选技能的完整指令，且检索范围 MUST 限定为本班全部材料或应用绑定的材料子集；回答沿用 SSE 流式与出处标注。无应用归属的旧会话 MUST 保持第 5 课行为（班级提示词 + 全部启用技能）。

#### Scenario: 应用会话的编排三要素

- **WHEN** 学生在绑定了模板 T 与技能 S 的应用 A 中提问，且本班材料有命中
- **THEN** 发往对话网关的 system MUST 包含模板 T 的正文（含 `{{skills}}`/`{{knowledge}}` 渲染结果）、技能 S 的完整指令与编号资料
- **AND** 当应用绑定了材料子集时，引用 MUST 只来自子集内材料

#### Scenario: 应用会话归属

- **WHEN** 学生通过 `POST /api/apps/<id>/conversations` 新建会话
- **THEN** 会话 MUST 记录 `app_id` 且归属本人本班；他人 MUST 不能访问该会话

### Requirement: 技能上传

系统 MUST 支持教师按课程技能文件格式上传技能：`POST /api/skills/upload`（multipart 文件，`.md`/`.txt`/`.json`），文件头部含 `名称`（必填）、可选 `简介`/`适用条件`/`工具`/`启用`，空行后为指令正文；解析结果 MUST 入库并可在技能列表查看。格式不合法（缺名称、正文为空、工具引用非法）MUST 返回 400 及可读原因。学生 MUST 不能上传技能。

#### Scenario: 上传合法技能文件

- **WHEN** 教师上传含 `名称：古诗鉴赏引导`、`适用条件：古诗,唐诗`、`工具：knowledge_search` 与正文的技能文件
- **THEN** 系统 MUST 解析入库（source=uploaded），技能列表 MUST 含该技能及其适用条件与工具
- **AND** 当 `启用：是` 时技能 MUST 处于启用状态

#### Scenario: 上传非法文件被拒绝

- **WHEN** 上传的文件缺少名称或正文为空，或工具栏写了格式非法的引用
- **THEN** 系统 MUST 返回 400 且提示可读原因，数据库 MUST 无新技能行

### Requirement: LLM 调用日志

每次调用对话网关（会话消息与 `/api/ask`）系统 MUST 写入一条调用日志，记录：发给网关的完整请求 JSON（含 model 与 messages 全部内容）、返回文本、模型名、状态（ok/error 及错误原因）、所用模板名、本轮注入指令的技能名清单、知识库切片总量与字符总量、实际传入切片数与字符数。日志 MUST 按班级隔离，仅教师可查；`GET /api/llm-logs/<id>` MUST 返回含完整 `request_json` 的详情。

#### Scenario: 一次会话问答产生完整日志

- **WHEN** 学生在应用会话中发送一条有依据的提问
- **THEN** `llm_call_logs` MUST 新增一行，`request_json` 反序列化后 MUST 含 `model` 与 `messages`，且 system 消息内容与会话编排一致
- **AND** `kb_total_chunks` MUST 大于等于 `kb_passed_chunks`；`template_name`、`skill_names` 与应用绑定一致

#### Scenario: 调用失败也留痕

- **WHEN** 对话网关不可用导致调用失败
- **THEN** 系统 MUST 记录 `status=error` 与错误原因
- **AND** 接口行为不变（503）

#### Scenario: 日志班级隔离

- **WHEN** 教师 B 请求 `GET /api/llm-logs`
- **THEN** 响应 MUST 只含 B 班的日志，不出现 A 班记录

## MODIFIED Requirements

### Requirement: 回答编排（assistant-chat）

会话回答的 system 输入 MUST 由「模板渲染 + 技能指令 + 编号资料 + 固定边界句」组装：模板来自会话所属应用的绑定（无应用会话沿用班级提示词）；技能取应用绑定的启用技能（无应用会话取全部启用技能），且 MUST 注入技能完整指令；编号资料 MUST 仅含检索命中的切片（前 4 条）。`/api/ask` 行为不变。

#### Scenario: 旧路径行为不变

- **WHEN** 学生在第 5 课创建的无应用会话中提问且技能已启用
- **THEN** system MUST 含班级提示词、启用技能完整指令与 `[1]` 编号资料（与第 5 课用例一致）

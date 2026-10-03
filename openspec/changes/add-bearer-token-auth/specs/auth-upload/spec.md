# Spec: auth-upload（delta）

## Purpose

在既有 Cookie 会话之外，为 API 增加 Bearer Token（JWT）凭证：登录接口签发令牌，前端持有并在 API 请求中提交，服务端校验令牌后识别用户、角色与班级。

## ADDED Requirements

### Requirement: Token 登录凭证

`POST /api/login` 成功响应 MUST 在既有字段之外返回 `access_token`（JWT，HS256 签名）与 `token_type: "bearer"`；令牌 payload MUST 含用户标识、角色（role）、班级（class_id）与过期时间（exp）；签名密钥 MUST 仅来自服务端环境变量（复用 `SECRET_KEY`）。受保护 API MUST 接受 `Authorization: Bearer <token>` 作为与 Cookie 会话等价的凭证；令牌签名不符、格式错误或已过期 MUST 返回 HTTP 401。角色与班级 MUST 仅从已验证的凭证读取，请求参数中携带的班级信息 MUST 一律无效。

#### Scenario: 登录响应携带 JWT

- **WHEN** 用户以有效账号密码调用 `POST /api/login`
- **THEN** 响应 MUST 为 HTTP 200，body 含 `access_token` 与 `token_type: "bearer"`
- **AND** `access_token` MUST 为三段式 JWT，解码 payload 含 `role`、`class_id` 与 `exp`
- **AND** 响应 MUST 同时通过 `Set-Cookie` 建立服务端会话（既有行为不变）

#### Scenario: 仅凭 Bearer 访问受保护 API

- **WHEN** 客户端不携带 Cookie，仅以 `Authorization: Bearer <有效令牌>` 请求受保护 API（如 `GET /api/search`）
- **THEN** 系统 MUST 正常处理请求（如 HTTP 200）
- **AND** 生效的角色与班级 MUST 来自令牌声明，而非请求参数

#### Scenario: 无效或过期令牌被拒绝

- **WHEN** 请求携带签名被篡改、格式非法或已过期的令牌
- **THEN** 系统 MUST 返回 HTTP 401
- **AND** MUST NOT 以该请求识别出任何用户、角色或班级

#### Scenario: 令牌中的班级即数据边界

- **WHEN** 持有 A 班令牌的用户检索一个仅出现在 B 班正文中的词，并在请求中伪造 B 班班级信息
- **THEN** 实际过滤条件 MUST 仍为令牌声明中的 A 班
- **AND** 响应 MUST 表现为无命中（HTTP 200 空列表），不得泄露 B 班内容

#### Scenario: 令牌不出现在 URL 中

- **WHEN** 前端携带令牌发起 API 请求
- **THEN** 令牌 MUST 仅出现在 `Authorization` 请求头
- **AND** MUST NOT 出现在 URL 查询串或路径中（避免落入日志与历史记录）

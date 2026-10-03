# Change: add-bearer-token-auth

## Why

课程课堂任务要求以 **Token 方案**实现登录认证：登录接口签发令牌，前端持有令牌并在后续 API 请求中通过 `Authorization: Bearer <token>` 提交，服务端验证令牌后识别用户与班级。当前系统仅有 Cookie 会话一种凭证，浏览器 Network 面板中看不到 Bearer 令牌，不满足验收截图要求。

## What Changes

- **登录签发令牌**：`POST /api/login` 成功响应中除既有字段外，MUST 同时返回 `access_token`（JWT，HS256）与 `token_type: bearer`；Cookie 会话行为保持不变（双凭证并存，不破坏现有页面）。
- **Bearer 凭证校验**：受保护 API MUST 接受 `Authorization: Bearer <token>` 作为与 Cookie 会话等价的凭证；令牌无效、过期或签名不符 MUST 返回 401；角色与班级 MUST 仅从已验证的凭证（令牌声明或会话）读取，请求参数中的班级信息一律无效。
- **前端携带令牌**：登录页保存令牌（localStorage），材料页的检索/问答等 fetch 调用 MUST 携带 `Authorization` 头；页面 SSR 导航仍走 Cookie，不做改动。
- **密钥与令牌安全**：签名密钥复用服务端 `SECRET_KEY` 环境变量；令牌含过期时间（exp）；令牌不出现在 URL 查询串中。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `auth-upload`：新增「Token 登录凭证」要求——登录接口签发 JWT、API 接受 Bearer 凭证、令牌声明作为角色/班级来源。

## Impact

- `app/`：新增令牌签发/校验模块；`login_required` 支持 Bearer；登录页与材料页 JS 保存并携带令牌。
- 不改变数据库结构、不改变 Cookie 会话语义、不改变班级隔离判定逻辑。
- 新增测试：令牌签发到校验全链路、无 Cookie 仅凭 Bearer 访问、无效令牌 401。

## Non-goals（非目标）

- 不做刷新令牌（refresh token）、令牌撤销列表、多设备管理。
- 不做 OAuth/OIDC 第三方登录。
- 不将 SSR 页面导航改为 Bearer（浏览器导航天然走 Cookie，仅 API fetch 携带令牌）。

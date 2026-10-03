# Tasks: add-bearer-token-auth

> Apply 已完成：37 项自动化测试全部通过（含 7 项 token 用例），并经 Compose 端到端实证（8088 签发/仅凭 Bearer 访问/篡改 401）。

## 1. 令牌模块（T1）

- [x] 1.1 实现 `app/token_auth.py`：HS256 JWT 签发（sub/username/role/class_id/iat/exp=2h）与校验（签名、exp、格式），stdlib 实现、密钥取自 `SECRET_KEY` — verify: 单元脚本签出三段式令牌，篡改任一字符后校验失败

## 2. 登录与认证链路（T2）

- [x] 2.1 `POST /api/login` 成功响应追加 `access_token`、`token_type: bearer`；Cookie 会话行为不变 — verify: 响应含合法 JWT 且 Set-Cookie 仍在
- [x] 2.2 `login_required` 支持 `Authorization: Bearer`：有效令牌写入请求上下文（role/class_id 来自声明），无效/过期 401；与 Cookie 并存时 Bearer 优先 — verify: 无 Cookie 仅凭 Bearer 调 `/api/search` 返回 200

## 3. 前端携带令牌（T3）

- [x] 3.1 登录页保存 `access_token` 到 localStorage，退出登录时清除 — verify: 登录后 localStorage 含 `campusclaw_token`
- [x] 3.2 材料页 fetch（检索/问答）统一附加 `Authorization: Bearer` 头 — verify: DevTools Network 中 API 请求头可见 `Authorization: Bearer eyJ...`

## 4. 测试与收尾（T4）

- [x] 4.1 测试：登录响应含 JWT；仅凭 Bearer 访问 200 且班级取自声明；篡改/过期令牌 401；Bearer 与参数伪造班级仍按声明过滤 — verify: `python tests/test_lesson4.py` 全过
- [x] 4.2 运行 `openspec validate add-bearer-token-auth --strict` — verify: exit 0 且无 error

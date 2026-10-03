# Design: add-bearer-token-auth

## Context

系统已有 Flask signed-cookie 会话（第 3 课归档规约），登录页通过 fetch 调 `POST /api/login` 建立会话；材料页 JS 调用 `/api/search`、`/api/ask`。课堂任务要求 Token 方案：登录签发 JWT，API 请求以 `Authorization: Bearer` 提交。本 change 在不动 Cookie 会话的前提下追加 Bearer 凭证。

## Goals / Non-Goals

**Goals:**

- `/api/login` 响应含 `access_token`（JWT HS256）与 `token_type: bearer`。
- 受保护 API 接受 Bearer 与 Cookie 任一种有效凭证。
- DevTools Network 面板可观察到携带 `Authorization: Bearer eyJ...` 的 API 请求。

**Non-Goals:** 刷新令牌、撤销、OIDC、SSR 导航改 Bearer（见 proposal）。

---

## 令牌格式与签发

- **JWT（HS256）**，签名密钥复用 `SECRET_KEY` 环境变量（禁止另起硬编码密钥）。
- Payload 声明：`sub`（user_id）、`username`、`role`、`class_id`、`iat`、`exp`（签发后 2 小时）。
- 标准库实现（`hmac` + `hashlib` + `base64` + `json`），不引入新依赖；canonical base64url 编码。
- 签发位置：`POST /api/login` 成功分支，与会话建立同时进行，互不影响。

## 校验与凭证合并

- `login_required` 前置逻辑扩展：
  1. 请求头含 `Authorization: Bearer <token>` → 校验签名与 `exp`；通过则把 `user_id`/`role`/`class_id` 写入请求上下文（Flask `g` 与 session 兼容读取），失败返回 401 JSON。
  2. 否则回退到既有 session cookie 判定；页面请求仍 302 登录页，API 401。
- Bearer 与 Cookie 同时存在时以 Bearer 为准（显式凭证优先），二者指向不同用户时不得混用。
- 角色/班级读取统一经由请求上下文；查询串/body 中的 `class_id` 依旧一律丢弃。

## 前端

- 登录页：`/api/login` 成功后将 `access_token` 存入 `localStorage`（键 `campusclaw_token`），再跳转材料页。
- 材料页：检索/问答 fetch 统一封装 `authFetch()`，自动附加 `Authorization: Bearer <token>`（无令牌时退化为普通 fetch，Cookie 仍可用）。
- 退出登录时清除 localStorage 中的令牌。

## 测试关注点

- 登录响应含合法三段式 JWT，解码 payload 含 role/class_id/exp。
- 无 Cookie、仅 `Authorization: Bearer` 调 `/api/search` 返回 200；班级取自令牌声明。
- 篡改签名/过期令牌/伪造 class_id 声明之外参数的令牌 → 401 或按声明者班级过滤。

## Decisions（摘要）

| # | 决策 | 备选 |
| --- | --- | --- |
| 1 | JWT HS256 + stdlib 实现 | PyJWT（新依赖） |
| 2 | Bearer 与 Cookie 双凭证并存 | 全面替换 Cookie（破坏现有 SSR 页面） |
| 3 | localStorage 存令牌 | Cookie 存令牌（无法出现在 Authorization 头） |
| 4 | 2 小时过期 | 永久令牌（不安全）/ 刷新令牌（本课不做） |

## Risks / Trade-offs

- [localStorage 令牌可被 XSS 读取] → 课程演示场景可接受；HttpOnly Cookie 仍是主凭证，Bearer 仅用于 API 演示与验收。
- [双凭证并存增加判定分支] → 收敛在 `login_required` 一处，单元测试覆盖两条路径。

## Migration Plan

无数据结构变更；旧会话继续有效，登录后重新走 `/api/login` 即可获得令牌。

## Open Questions

（无。）

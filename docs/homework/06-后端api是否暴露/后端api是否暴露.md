# 0923-后端（api）是否暴露给用户？如何通过浏览器直接访问后端接口

## 一、问题 1：后端 api 是否暴露给用户？

**没有暴露。** 依据演示仓的 `docker-compose.yml`：api 服务只声明了 `build / env_file / environment / volumes / depends_on / healthcheck`，**没有 `ports` 端口映射**。`.env` 中的 `PORT=8000` 只是 api 在 **Compose 内部网络**的监听端口——Docker 中不写 `ports` 的服务，宿主机与浏览器都无法直达。唯一对外入口是 web（Nginx）映射的 `WEB_PORT=8088`。

这是刻意的**攻击面最小化**设计：对外只开一个门（8088），api 与 db（3306 同样不映射）都藏在内部网络。

## 二、问题 2：如何通过浏览器直接访问后端接口？

**经 Nginx 同源反向代理。** 浏览器请求 `http://localhost:8088/api/...`，Nginx 按配置转发：

```nginx
location /api/ {
    proxy_pass http://api:8000/api/;
    ...
}
location /health {
    proxy_pass http://api:8000/health;
}
```

即：浏览器只跟 8088 的 Nginx 说话，由 Nginx 在内部网络把请求递给 api 容器并带回响应。前端与 API 同源，顺带规避了跨域问题。

```
浏览器 ──► localhost:8088 (Nginx) ──内部网络──► api:8000 (后端) ──► db:3306
              唯一对外入口              不暴露                不暴露
```

## 三、本仓库（CampusClaw）的对照实现

我们的学期仓采用**单服务架构**（design.md 选型，课件允许）：Flask 一个进程同时承担页面与 API，对外只有一个端口 8080（见截图「代码1」「代码2」）。两种架构形态不同，但设计目标一致——**收窄并守住入口**：

| | 演示仓（三服务） | 本仓库（单服务） |
| --- | --- | --- |
| 后端隔离方式 | 网络层隔离：api 无 ports，仅内部网络可达 | 同进程，不做网络隔离 |
| 入口 | 仅 Nginx 8088 | 仅 Flask 8080 |
| 后端接口保护 | 入口唯一 + 应用鉴权 | 应用层鉴权：未登录页面 302 / API 401（截图「代码3」「代码4」） |
| 浏览器如何访问后端 | 8088 → Nginx 反代 → api:8000 | 直接请求 8080 的 `/api/...`，由会话鉴权拦截 |

**实测证据**（截图「实测5」）：

- 未登录 `GET /materials` → **302 重定向登录页**，响应无业务数据
- 错误密码 `POST /api/login` → **401** `{"error":"invalid_credentials"}`
- `GET /health` → **200** `{"status":"ok"}`（规约要求的公开探活端点）
- 正确密码 `POST /api/login` → **200** JSON + `Set-Cookie: session=...; HttpOnly; SameSite=Lax`

## 四、结论

后端 api **不直接暴露**：演示仓靠「无 ports + Nginx 反代」在网络层隐藏后端，浏览器经 8088 同源访问；本仓库当前为单服务形态，后端接口与页面同端口可达，但同样只有一个入口，且所有受保护接口在应用层强制鉴权（302/401）。两者都是"最小暴露面 + 统一入口"的落地方式。

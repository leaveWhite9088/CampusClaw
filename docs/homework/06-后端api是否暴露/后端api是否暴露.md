# 0923-后端（api）是否暴露给用户？如何通过浏览器直接访问后端接口

## 一、问题 1：后端 api 是否暴露给用户？

**没有暴露。** 本仓库 `docker-compose.yml` 中，`app` 服务（Flask/gunicorn，监听 8000）只声明 `build / env_file / volumes / healthcheck`，**没有 `ports` 端口映射**（见「配置1」）；`.env.example` 中亦注明 `PORT=8000`「仅 Compose 内部网络可达，不映射到宿主」（见「配置3」）：

- Docker 中不写 `ports` 的服务只在 Compose 内部网络可达，宿主机与浏览器都无法直连
- `docker ps` 实测：`app` 仅显示 `8000/tcp`（无映射），`web` 显示 `0.0.0.0:8088->8080`
- 宿主机直接请求后端端口 `curl http://localhost:8000/health` → **连接失败**

这是**攻击面最小化**设计：整个系统只对外开一个门（8088），后端与数据文件都不临街。

## 二、问题 2：如何通过浏览器直接访问后端接口？

**经 Nginx 同源反向代理。** 浏览器只跟唯一入口 `web`（Nginx，8088）说话，由 Nginx 在内部网络把请求转发给 `app:8000`（`deploy/nginx.conf` 全文见「配置2」）：

```nginx
location /api/   { proxy_pass http://app:8000/api/;  ... }
location /health { proxy_pass http://app:8000/health; ... }
location /       { proxy_pass http://app:8000;        ... }
```

```
浏览器 ──► localhost:8088 (web: Nginx) ──内部网络──► app:8000 (Flask/gunicorn)
              唯一对外端口映射                          无 ports，宿主不可直连
```

前端与后端接口同源（都是 8088），顺带规避了跨域问题。

## 三、实测证据

以下命令均可按 README 从零复现（`cp .env.example .env` → 填 SECRET_KEY → `docker compose up --build`）：

| 验证 | 结果 |
| --- | --- |
| `docker compose up --build -d` 后两容器状态 | app healthy、web running |
| 宿主直连 `localhost:8000/health` | 连接失败（后端不暴露） |
| `localhost:8088/health` | 200 `{"status":"ok"}` |
| `localhost:8088/api/login`（POST 正确密码） | 200 JSON + `Set-Cookie: HttpOnly; SameSite=Lax` |
| 浏览器 `localhost:8088/login` 登录 teacher_a 后的首页 | 正常，仅显示本班材料 |
| `docker compose down` → `up`（不删卷）后预置与上传数据 | 仍在（volume 持久化） |

## 四、结论

后端 api **不直接暴露给用户**：它只在 Compose 内部网络监听，宿主机直连失败；浏览器通过唯一入口 Nginx（8088）的反向代理访问后端接口（`/api/...` 与 `/health`）。本仓库与课程演示架构同构——演示仓为 web/api/db 三服务（Go + MySQL），本仓库为 web/app 双服务（Flask + SQLite，规约允许的等价选型），两者的暴露面控制完全一致。

---

## 附：提交材料清单

1. `配置1-docker-compose（app无ports，web映射8088）.png` —— `docker-compose.yml` 全文：app 无 `ports`（含注释），web 映射 `8088:8080`
2. `配置2-nginx反代配置.png` —— `deploy/nginx.conf` 全文：`/api/`、`/health`、`/` 三个 location 均反代到 `app:8000`
3. `配置3-env端口与密钥.png` —— `.env.example` 全文：`PORT=8000` 仅内部可达；`SECRET_KEY` 仅经环境变量注入

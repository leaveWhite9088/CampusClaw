# 0923-后端（api）是否暴露给用户？如何通过浏览器直接访问后端接口

> 分析对象：本仓库 CampusClaw 的 Docker Compose 部署（`docker-compose.yml`、`deploy/nginx.conf`），与课程演示架构同构
> 规约依据：`openspec/specs/auth-upload/spec.md`「Docker Compose 部署与健康检查」（含「后端服务不直接暴露」Scenario）

## 一、问题 1：后端 api 是否暴露给用户？

**没有暴露。** 本仓库 `docker-compose.yml` 中，`app` 服务（Flask/gunicorn，监听 8000）只声明 `build / env_file / volumes / healthcheck`，**没有 `ports` 端口映射**（截图 1、2）：

- Docker 中不写 `ports` 的服务只在 Compose 内部网络可达，宿主机与浏览器都无法直连
- `docker ps` 实测：`app` 仅显示 `8000/tcp`（无映射），`web` 显示 `0.0.0.0:8088->8080`（截图 3）
- 宿主机直接请求后端端口 `curl http://localhost:8000/health` → **连接失败**（截图 4）

这是**攻击面最小化**设计：整个系统只对外开一个门（8088），后端与数据文件都不临街。

## 二、问题 2：如何通过浏览器直接访问后端接口？

**经 Nginx 同源反向代理。** 浏览器只跟唯一入口 `web`（Nginx，8088）说话，由 Nginx 在内部网络把请求转发给 `app:8000`（`deploy/nginx.conf`，截图 5）：

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

| 验证 | 结果 | 截图 |
| --- | --- | --- |
| `docker compose up --build -d` 后两容器 running/healthy | ✅ | 截图 3 |
| 宿主直连 `localhost:8000/health` | 连接失败（后端不暴露） | 截图 4 |
| `localhost:8088/health` | 200 `{"status":"ok"}` | 截图 4 |
| `localhost:8088/api/login`（POST 正确密码） | 200 JSON + `Set-Cookie: HttpOnly; SameSite=Lax` | 截图 4 |
| 浏览器 `localhost:8088/login` 登录 teacher_a 后的首页 | 正常，仅显示本班材料 | 截图 6 |
| `docker compose down` → `up`（不删卷）后数据仍在 | ✅ | — |

## 四、结论

后端 api **不直接暴露给用户**：它只在 Compose 内部网络监听，宿主机直连失败；浏览器通过唯一入口 Nginx（8088）的反向代理访问后端接口（`/api/...` 与 `/health`）。本仓库与课程演示架构同构——演示仓为 web/api/db 三服务（Go + MySQL），本仓库为 web/app 双服务（Flask + SQLite，规约允许的等价选型），两者的暴露面控制完全一致。

---

## 附：截图清单

1. `截图1-compose全文.png` —— `docker-compose.yml`（VS Code 全文）
2. `截图2-app服务无ports.png` —— compose 中 app 服务段（含「不声明 ports」注释）
3. `截图3-docker-ps.png` —— 终端 `docker ps`（web 8088 映射、app 仅 8000/tcp、healthy）
4. `截图4-端口实测.png` —— 终端三条：`curl -m 3 http://localhost:8000/health`（失败）、`curl http://localhost:8088/health`（200）、`curl -X POST http://localhost:8088/api/login ...`（200 + Set-Cookie）
5. `截图5-nginx反代配置.png` —— `deploy/nginx.conf` 全文
6. `截图6-8088登录首页.png` —— 浏览器经 8088 登录 teacher_a 后的材料首页（地址栏 8088 入镜）

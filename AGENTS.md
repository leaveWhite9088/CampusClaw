# CampusClaw 项目规则

- **无规约不写代码**：任何功能实现必须先有 `openspec/changes/` 下对应的 change 规约（proposal / design / specs / tasks），规约未覆盖的行为不得实现。
- 规约变更仅限于 `openspec/**/*.md`，口头约定无效。
- 密码必须哈希存储，禁止明文；密钥只放服务端环境变量，禁止硬编码或提交入库。
- 班级是数据边界：所有业务查询必须在服务端按会话中的班级过滤，前端隐藏按钮不算满足隔离要求。
- 标准启动方式为 Docker Compose；应用提供 `GET /health`。

# M1 验收报告：项目骨架与认证

> 验收日期：2026-10-13  
> 验收范围：`DMS_V1.0_MiMo_Development_Spec.md` 第 16 节 M1 里程碑  
> 验收方式：实际执行构建、迁移、自动化测试与运行时接口验证（非仅代码审阅）  
> **验收结论：通过**

---

## 1. M1 开发目标对照

| 规格要求（§16 M1） | 实现情况 | 结论 |
|---|---|---|
| 建立仓库及目录 | `backend/` `frontend/` `docs/` `deploy/` `scripts/` 按规格 §3 结构创建 | 通过 |
| 前后端基本工程 | FastAPI + Vue3/Vite/Element Plus/Pinia 可构建、可运行 | 通过 |
| Docker Compose | `compose.yaml`（mysql + backend + frontend + 健康检查依赖链） | 通过 |
| MySQL | MySQL 8.0 容器，InnoDB/utf8mb4，127.0.0.1 绑定 | 通过 |
| 数据库迁移 | Alembic `0001_initial_auth`，全新库可执行、可重复执行 | 通过 |
| 认证 | 登录/登出/刷新/me，Argon2id + JWT 双 Token（可撤销） | 通过 |
| 用户/角色/权限 | RBAC 五角色 + 27 权限码，CRUD 与授权接口 | 通过 |
| 统一 API 格式 | `{code,message,details,request_id}` + `{items,total,page,page_size}` | 通过 |
| 审计基础 | `audit_logs` 仅追加表 + 登录/用户变更写审计 | 通过 |
| 健康检查 | `/health`、`/health/ready`（含 DB 探活） | 通过 |
| 登录页可用 | Vite SPA 登录页 + Nginx 静态服务 | 通过 |
| 登录成功 | 实测 admin 登录返回 27 项权限 | 通过 |
| 连接数据库 | `/health/ready` 返回 `database: ok` | 通过 |
| 迁移可重复执行 | 第二次 `upgrade head` 为 no-op | 通过 |

---

## 2. 测试项目、执行命令与结果

### 2.1 后端静态检查

| 项目 | 命令 | 结果 |
|---|---|---|
| 代码风格 | `ruff check app tests` | **All checks passed** |

### 2.2 后端自动化测试（真实 MySQL 8.0）

| 项目 | 命令 | 结果 |
|---|---|---|
| 单元 + 集成测试 | `pytest -q` | **16 passed** |

用例明细：

| 用例 | 结果 |
|---|---|
| test_health_ok / test_health_v1 / test_openapi_available | PASSED |
| test_password_hash_roundtrip / test_password_hash_is_argon2id | PASSED |
| test_access_token_roundtrip / test_access_token_rejects_garbage | PASSED |
| test_refresh_token_fingerprint_stable | PASSED |
| test_login_success / test_login_wrong_password | PASSED |
| test_me_requires_token | PASSED |
| test_full_auth_flow（登录→me→权限→刷新轮换→旧Token失效→登出） | PASSED |
| test_permission_gate_user_manage（HR 无 user:manage → 403） | PASSED |
| test_list_roles_and_permissions | PASSED |
| test_user_crud_and_roles | PASSED |
| test_disable_account_revokes_login | PASSED |

### 2.3 前端构建与类型检查

| 项目 | 命令 | 结果 |
|---|---|---|
| TypeScript 严格检查 | `npm run typecheck` | **通过（0 error）** |
| 生产构建 | `npm run build` | **成功**（约 2.6s，产出 dist/） |

### 2.4 数据库迁移

| 项目 | 命令 | 结果 |
|---|---|---|
| 现有库迁移头 | `alembic current` | `0001_initial_auth (head)` |
| **全新库迁移** | 新建 `dms_fresh` → `alembic upgrade head` | **成功**，创建 8 张表 |
| 迁移可重复 | 再次 `alembic upgrade head` | **no-op（无重复执行）** |
| 全新库种子 | `python -m app.seed` | 成功：RBAC 目录 + admin + super_admin |

全新库创建的表：

```
alembic_version, audit_logs, auth_refresh_tokens,
sys_permissions, sys_role_permissions, sys_roles, sys_user_roles, sys_users
```

### 2.5 Docker Compose

| 项目 | 命令 | 结果 |
|---|---|---|
| 配置校验 | `docker compose config --quiet` | **COMPOSE_CONFIG_OK**（缺必填环境变量时正确报错） |
| 后端镜像构建 | `docker compose build backend` | **成功** |
| 前端镜像构建 | `docker compose build frontend` | **成功** |
| 全栈启动 | `docker compose up -d` | mysql/backend/frontend **全部 healthy** |

全栈容器状态：

| 容器 | 状态 | 端口 |
|---|---|---|
| mysql-1 | healthy | 127.0.0.1:3306 |
| backend-1 | healthy | 8000（内网） |
| frontend-1 | healthy | 0.0.0.0:8080→80 |

---

## 3. 运行时功能验证（实测，非代码推断）

### 3.1 健康检查与数据库

```
GET  /health                  → 200 {"status":"ok","service":"DMS Backend","env":"production"}
GET  /api/v1/health/ready     → 200 {"status":"ready","database":"ok"}
```

（上述经 Nginx `http://127.0.0.1:8080` 反代验证）

### 3.2 认证流

| 场景 | 结果 |
|---|---|
| 登录（admin） | 200，返回 access/refresh token，`super_admin`，27 权限 |
| `/auth/me` | 200，返回角色与权限列表 |
| 错误密码 | 401 `authentication_error` |
| 无 Token 访问 `/users` | 401 `authentication_error` + request_id |
| 伪造 JWT | 401 `authentication_error` |
| 刷新令牌轮换 | 200，签发新 refresh token |
| 旧 refresh 重放 | 401（已撤销） |
| 登出 | 200 |
| 登出后使用 refresh | 401 |

### 3.3 权限控制（RBAC）

| 场景 | 结果 |
|---|---|
| HR 角色调用 `GET /users`（需 `user:manage`） | **403** `permission_denied` |
| HR 角色调用 `GET /roles`（已认证） | 200 |
| HR `/auth/me` 中无 `user:manage` | 已确认 |

### 3.4 前后端通信

| 链路 | 结果 |
|---|---|
| Vite 代理 `/api/v1/health` | 200 |
| Vite 代理登录接口 | 200，登录成功 |
| Vite SPA `/login` | 200，返回 HTML |
| Nginx 反代登录 | 200 |
| Nginx 提供 SPA | 200，`公司宿舍入住管理系统` |

---

## 4. 安全检查

| 检查项 | 方法 | 结果 |
|---|---|---|
| 源码硬编码密码 | 全文扫描 `password=` / `secret=` 字面量 | **无**（仅测试从环境变量读取） |
| 明文密钥/连接串 | 扫描 `mysql+asyncmy://user:pass@` / 私钥 / AKIA | **无** |
| `.env` 是否入库 | `find . -name .env` | **不存在** |
| `.gitignore` 覆盖 `.env` | 检查规则 | **已覆盖** |
| `.env.example` | 检查内容 | 仅占位符（`change-me`） |
| 密码哈希 | Argon2id（`$argon2id$` 前缀，测试已验证） | 合格 |
| 刷新令牌存储 | 仅存 SHA-256 哈希，可撤销 | 合格 |
| 错误响应泄密 | 500 不返回堆栈/SQL | 合格 |
| 未授权接口 | 路由审计 | 仅 `login`/`refresh`/`health` 有意公开 |

### 4.1 路由鉴权审计（OpenAPI 实测 15 条路径）

| 路径 | 鉴权要求 | 判定 |
|---|---|---|
| `POST /auth/login` | 公开 | 预期 |
| `POST /auth/refresh` | 公开（持 refresh） | 预期 |
| `GET /health`、`/health/ready` | 公开 | 预期（容器探活） |
| `POST /auth/logout`、`GET /auth/me`、`GET /auth/permissions` | 需登录 | 合格 |
| `GET /auth/token-lifetime` | 需登录（**本次修复**） | 合格 |
| `GET/POST /users`、`PATCH /users/{id}`、`PUT /users/{id}/roles` | 需 `user:manage` | 合格 |
| `GET /roles`、`GET /permissions` | 需登录 | 合格 |

---

## 5. 本次发现并修复的问题

| # | 问题 | 严重程度 | 修复 |
|---|---|---|---|
| 1 | 测试代码硬编码 `admin12345` | 中 | 改为 `DMS_ADMIN_USERNAME` / `DMS_ADMIN_PASSWORD` 环境变量（conftest 提供默认测试值） |
| 2 | `GET /auth/token-lifetime` 未鉴权即可访问 | 中 | 增加 `CurrentUserDep`，未登录返回 401 |
| 3 | 后端 `Dockerfile` 先 `pip install .` 再拷贝 `app/`，镜像内安装会失败 | 高 | 调整为先 `COPY app` 再 `pip install .` |
| 4 | 前端 `Dockerfile` 未使用 lockfile，构建不可复现 | 低 | 优先 `npm ci`（有 package-lock.json） |
| 5 | `docs/DECISIONS.md` 写 `scripts/init_admin.py`，实际实现为 `app.seed` | 低 | 文档更正 |
| 6 | `backend/tests/db.py` 为无用残留文件 | 低 | 删除 |

修复后回归：`pytest` **16 passed**，`ruff` **All checks passed**，`vue-tsc` **0 error**，Nginx 链路 401/403/登出均复验通过。

---

## 6. 无法执行 / 受环境限制的检查

| 项目 | 原因 | 影响评估 |
|---|---|---|
| Docker Hub 偶发超时 | 构建过程中 `auth.docker.io` 曾 i/o timeout；预拉取基础镜像后重试成功 | 无最终影响，镜像已构建成功 |
| 浏览器 UI 人工点击走查 | 当前环境无法打开图形浏览器做人工点击验收 | 已用 HTTP 实测 SPA 可访问、登录 API 与代理链路可用；UI 交互细节留待 M6 端到端验收 |
| 生产 HTTPS / Cookie CSRF | 属部署配置，非 M1 范围 | 记录到 M6 / DEPLOYMENT 文档 |
| 压测（50 并发等） | 属 M6 非功能验收 | 不阻塞 M1 |

---

## 7. 遗留问题（不阻塞 M1，登记待办）

1. **前端 `npm run test`（Vitest）尚未编写用例**——M1 以 `typecheck + build + HTTP 链路验证` 为准；组件级测试可在 M5 页面增多后补充。
2. **审计日志查询接口未暴露**——`audit_logs` 表与写入已就绪，查询 API 按规格属权限矩阵中的 `audit:view`，可在 M4/M5 一并提供；当前已记录登录/用户变更审计。
3. **`deploy/nginx/default.conf` 与 `frontend/nginx.conf` 双份维护**——内容一致，M6 可合并为单一来源避免漂移。
4. **Compose 中 MySQL 将 3306 绑定到 `127.0.0.1`**（便于集成测试）——生产加固可删除 ports 映射（见 `docs/DECISIONS.md` D-018）。

---

## 8. 验收结论

### **M1 验收：通过**

理由：
1. 规格 M1 全部交付项均有真实文件与可运行实现；
2. 自动化测试 16/16 通过，lint 与前端类型检查/构建通过；
3. 全新数据库迁移与重复迁移均验证通过；
4. Docker Compose 三服务全栈启动 healthy，经 Nginx 完成登录、401、403、登出与健康检查实测；
5. 安全扫描未发现硬编码凭据或未授权业务接口；发现的 6 个问题已修复并回归通过；
6. 无阻塞性缺陷。

### M2 开发准备情况：**就绪**

M2 将基于现有骨架扩展：
- 数据模型：`departments`、`employees`（含人事状态）+ Alembic 迁移
- API：员工 CRUD/详情/住宿查询、Excel 模板/预览/提交/导出、`dorm_areas`→`dorm_beds` 层级 CRUD
- 前端：员工管理页、宿舍资源树与房间/床位管理页
- 约束落地：`UNIQUE(employee_no)`、部门外键、楼层/房间/床位唯一编号、容量校验、停用禁止新分配
- 测试：导入冲突（重复工号）、层级创建、停用校验等

可立即开始 M2，无需等待其他前置条件。

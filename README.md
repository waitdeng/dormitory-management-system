# 公司宿舍入住管理系统（DMS）V1.0

企业内部行政、人事办理员工入职住宿、在住调整及离职退宿的 Web 管理平台。

## 技术栈

| 层 | 技术 |
|---|---|
| 前端 | Vue 3 · TypeScript · Vite · Element Plus · Pinia · Vue Router · Axios |
| 后端 | FastAPI · Pydantic v2 · SQLAlchemy 2.x (async) · asyncmy |
| 数据库 | MySQL 8.0 · InnoDB · utf8mb4 |
| 迁移 | Alembic |
| 部署 | Docker Compose · Nginx |
| 测试 | pytest · httpx · Vitest · Playwright |

## 快速开始

### 1. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，至少设置：
#   MYSQL_PASSWORD / MYSQL_ROOT_PASSWORD / SECRET_KEY / DMS_ADMIN_PASSWORD
python3 -c "import secrets; print(secrets.token_urlsafe(64))"  # 生成 SECRET_KEY
```

### 2. 启动全部服务（Docker Compose）

```bash
# 开发 / 本地联调（MySQL 发布到 127.0.0.1:3306，便于宿主机工具连接）
docker compose up -d --build

# 公司内网正式部署（MySQL 不映射到宿主机，仅 Compose 内网可达）
docker compose -f compose.yaml -f compose.production.yaml up -d --build
```

首次启动会自动执行：
- MySQL 健康检查通过后启动 backend
- Alembic `upgrade head`
- 种子权限/角色 + 初始化管理员（`DMS_ADMIN_USERNAME` / `DMS_ADMIN_PASSWORD`）

访问：
- 管理后台：http://localhost:8080
- 健康检查：http://localhost:8080/health
- API 文档：http://localhost:8080/api/docs（非 production 环境；production 需在 `.env` 设置 `ENABLE_API_DOCS=true` 才开放）

> **部署形态**：公司内网、单 backend 实例。预留过期扫描在每个 FastAPI 进程的 lifespan 内启动；若以后改为多 worker / 多副本，需改用独立任务调度或分布式锁（见 `docs/DEPLOYMENT.md`）。

### 3. 本地开发（不使用 Docker 跑应用）

```bash
# 后端
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp ../.env.example .env   # 或使用 backend/.env
alembic upgrade head
python -m app.seed
uvicorn app.main:app --reload --port 8000

# 前端
cd frontend
npm install
npm run dev   # http://localhost:5173，已代理 /api 到 8000
```

## 测试

```bash
# 后端单元测试（无需数据库）
cd backend && pytest tests/test_health.py tests/test_security.py -q

# 后端集成/并发测试（需要真实 MySQL，务必指向隔离测试库）
export MYSQL_DATABASE=dms_p1fix_test   # 或其它非生产库
export MYSQL_HOST=127.0.0.1 MYSQL_PASSWORD=... SECRET_KEY=...
cd backend && pytest -q

# 前端
cd frontend && npm run typecheck
cd frontend && npm test
cd frontend && npm run build

# Playwright E2E（需本地前后端或预置 base URL）
cd frontend && npx playwright test
```

> 测试结果以本轮实际执行记录为准，见 `docs/DMS_CODE_REVIEW_FIX_REPORT.md` 与各阶段验收报告。请勿把历史报告结果当作当前一次执行结果。

## 备份与恢复

```bash
export MYSQL_PASSWORD=...
./scripts/backup.sh ./backups
./scripts/restore.sh ./backups/dms_XXXX.sql.gz
```

正式环境建议使用 `compose.production.yaml` 后，备份脚本通过 `docker exec` 进入 MySQL 容器执行，不依赖宿主机 3306 端口。

## 里程碑

| 阶段 | 内容 | 状态 |
|---|---|---|
| M1 | 项目骨架与认证 | 已完成（2026-10-13） |
| M2 | 基础数据（员工/宿舍） | 已完成（2026-10-13） |
| M3 | 入住/调宿/退宿事务闭环 | 已完成（2026-10-13） |
| M4 | 离职联动与预警 | 已完成（2026-10-13） |
| M5 | 可视化与报表 | 已完成（2026-10-13） |
| M6 | 联调、迁移和上线验证 | 已完成（2026-10-14） |
| 代码审查修复 | 导入事务/预留锁序/到期校验等 P1–P3 | 见 `docs/DMS_CODE_REVIEW_FIX_REPORT.md` |

详细计划见 `docs/IMPLEMENTATION_PLAN.md`，技术取舍见 `docs/DECISIONS.md`。

## 安全说明

- 源码中不包含任何真实密码、令牌或数据库凭据。
- `.env` 已在 `.gitignore` 中排除，请勿提交。
- 密码使用 Argon2id 哈希；刷新令牌只存哈希且可撤销。
- 所有关键写操作写入审计日志（`audit_logs`，仅追加）。
- production 环境默认关闭 `/api/docs`；MySQL 不要映射到 `0.0.0.0`。

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
| 测试 | pytest · httpx · Vitest |

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
docker compose up -d --build
```

首次启动会自动执行：
- MySQL 健康检查通过后启动 backend
- Alembic `upgrade head`
- 种子权限/角色 + 初始化管理员（`DMS_ADMIN_USERNAME` / `DMS_ADMIN_PASSWORD`）

访问：
- 管理后台：http://localhost:8080
- API 文档：http://localhost:8080/api/docs
- 健康检查：http://localhost:8080/health

### 3. 本地开发（不使用 Docker 跑应用）

```bash
# 后端
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
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

# 后端集成测试（需要真实 MySQL）
export DMS_RUN_DB_TESTS=1
export MYSQL_HOST=127.0.0.1 MYSQL_PASSWORD=... SECRET_KEY=...
cd backend && pytest -q

# 前端类型检查
cd frontend && npm run typecheck
```

## 备份与恢复

```bash
export MYSQL_PASSWORD=...
./scripts/backup.sh ./backups
./scripts/restore.sh ./backups/dms_XXXX.sql.gz
```

## 里程碑

| 阶段 | 内容 | 状态 |
|---|---|---|
| M1 | 项目骨架与认证 | 已完成 |
| M2 | 基础数据（员工/宿舍） | 待开始 |
| M3 | 入住/调宿/退宿事务闭环 | 待开始 |
| M4 | 离职联动与预警 | 待开始 |
| M5 | 可视化与报表 | 待开始 |
| M6 | 联调、迁移和上线验证 | 待开始 |

详细计划见 `docs/IMPLEMENTATION_PLAN.md`，技术取舍见 `docs/DECISIONS.md`。

## 安全说明

- 源码中不包含任何真实密码、令牌或数据库凭据。
- `.env` 已在 `.gitignore` 中排除，请勿提交。
- 密码使用 Argon2id 哈希；刷新令牌只存哈希且可撤销。
- 所有关键写操作写入审计日志（`audit_logs`，仅追加）。

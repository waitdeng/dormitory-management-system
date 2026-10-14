# DMS V1.0 部署文档

> 适用版本：V1.0（M6 验收）  
> 部署形态：Docker Compose（mysql + backend + frontend/nginx）  
> 约束：MySQL 不对公网暴露；密钥经环境变量注入；生产建议 HTTPS。

---

## 1. 环境要求

| 组件 | 要求 |
|---|---|
| Docker | 24+（Docker Desktop / Engine 均可） |
| Docker Compose | v2（`docker compose`） |
| CPU / 内存 | 建议 ≥2 核 / ≥4GB |
| 磁盘 | ≥20GB（含 MySQL 数据与备份） |
| 网络 | 内网部署；仅前端 80/443 对用户开放 |

---

## 2. 首次部署

### 2.1 准备环境变量

```bash
cp .env.example .env
# 编辑 .env，至少设置：
#   MYSQL_PASSWORD / MYSQL_ROOT_PASSWORD（强随机）
#   SECRET_KEY（python -c "import secrets; print(secrets.token_urlsafe(64))"）
#   DMS_ADMIN_USERNAME / DMS_ADMIN_PASSWORD（首次初始化后建议改密）
#   WEB_PORT（默认 8080）
```

**禁止**将真实 `.env` 提交到版本库。

### 2.2 启动服务

```bash
# 开发 / 本地联调（MySQL 映射到 127.0.0.1:3306）
docker compose up -d --build

# 公司内网正式部署（MySQL 不发布到宿主机，仅 Compose 网络可达）
docker compose -f compose.yaml -f compose.production.yaml up -d --build

docker compose ps
```

启动顺序：mysql（healthy）→ backend（跑 `alembic upgrade head` + `app.seed` + uvicorn）→ frontend（nginx）。

**两种 Compose 模式**

| 模式 | 命令 | MySQL 端口 | 适用 |
|---|---|---|---|
| 开发 | `docker compose up` | `127.0.0.1:3306` | 本地调试、集成测试、宿主机 GUI 连库 |
| 生产 | `docker compose -f compose.yaml -f compose.production.yaml up` | 无宿主机映射 | 内网正式部署；宿主机 3306 被占用时仍可启动 |

备份脚本 `scripts/backup.sh` 通过 `docker exec` 在容器内执行 `mysqldump`，两种模式均可用，不依赖宿主机端口。

**单实例前提**：预留过期扫描（`SCANNER_ENABLED`）在每个 FastAPI 进程 lifespan 内启动。V1 内网单 backend 实例可直接使用；若改为多 worker（`uvicorn --workers N`）或多副本部署，会出现扫描重入，届时需独立任务调度或分布式锁，不要直接横向扩容 backend。

### 2.3 验证

```bash
curl -s http://127.0.0.1:8080/health
# {"status":"ok",...}

# 浏览器打开
open http://127.0.0.1:8080/
# 使用 DMS_ADMIN_USERNAME / DMS_ADMIN_PASSWORD 登录
```

---

## 3. 升级（已有数据）

```bash
git pull   # 或同步新版本文件
docker compose build backend frontend
docker compose up -d
# backend 启动命令内含 alembic upgrade head，会按序应用新迁移
docker compose logs backend | tail -50   # 确认迁移与启动日志
```

升级前务必执行备份（见 `docs/BACKUP_RESTORE.md`）。

---

## 4. 生产加固清单

| 项 | 要求 | 本仓库默认 |
|---|---|---|
| MySQL 端口 | 不对外网开放 | 开发：`127.0.0.1:3306`；生产用 `compose.production.yaml` 去掉映射 |
| SECRET_KEY | 足够强度随机值，可轮换 | 环境变量，`.env.example` 仅占位 |
| 管理员口令 | 首次登录后修改 | 启动时 seed |
| HTTPS | TLS1.2+，HSTS | 见 `deploy/nginx/ssl.conf.example` |
| API 文档 | 生产隐藏 `/api/docs` | 默认关闭；`ENABLE_API_DOCS=true` 才在 production 开放 |
| 上传限制 | 文件类型/大小 | 5MB 服务端校验 + nginx `client_max_body_size 8m` |
| 导出安全 | 公式注入防护 | `_safe_excel_value` |
| CORS | 仅允许前端源 | `CORS_ORIGINS` |
| 备份 | 每日 + 恢复演练 | `scripts/backup.sh` |

### 4.1 HTTPS

1. 申请/签发证书（企业 CA 或 Let's Encrypt）。
2. 将 `deploy/nginx/ssl.conf.example` 挂载为 frontend 容器站点配置。
3. 证书放在 `/etc/nginx/tls/fullchain.pem` 与 `privkey.pem`（或 Docker secret）。
4. 将 `WEB_PORT` 改为 `443` 或前置负载均衡终结 TLS。

### 4.2 关闭生产 API 文档

```bash
# .env
APP_ENV=production
ENABLE_API_DOCS=false   # 默认已是 false；仅在内网需要调试时改为 true
```

`/api/docs` 与 `/api/openapi.json` 的暴露条件（`backend/app/main.py`）：

- `APP_ENV != production`：始终开放（开发/测试）
- `APP_ENV == production`：仅当 `ENABLE_API_DOCS=true` 时开放

---

## 5. 环境变量参考

| 变量 | 说明 | 默认 |
|---|---|---|
| `MYSQL_DATABASE` | 库名 | `dms` |
| `MYSQL_USER` / `MYSQL_PASSWORD` | 应用账号 | 必填 |
| `MYSQL_ROOT_PASSWORD` | root（仅容器内） | 必填 |
| `SECRET_KEY` | JWT 签名密钥 | 必填 |
| `DMS_ADMIN_USERNAME` / `DMS_ADMIN_PASSWORD` | 初始管理员 | `admin` / 空 |
| `WEB_PORT` | 前端对外端口 | `8080` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | 访问令牌 | `30` |
| `REFRESH_TOKEN_EXPIRE_DAYS` | 刷新令牌 | `14` |
| `SCANNER_ENABLED` | 预留过期/预警扫描 | `true` |
| `SCANNER_INTERVAL_SECONDS` | 扫描间隔 | `60` |
| `ENABLE_API_DOCS` | 是否在 production 暴露 OpenAPI | `false` |
| `MYSQL_HOST_PORT` | 开发模式宿主机映射端口 | `3306` |
| `CORS_ORIGINS` | 允许的前端源 | localhost 列表 |

---

## 6. 平台启动指令

### macOS / Linux

```bash
cp .env.example .env   # 填写真实值
docker compose up -d --build
```

### Windows（PowerShell + Docker Desktop）

```powershell
Copy-Item .env.example .env
# 编辑 .env
docker compose up -d --build
```

### 常用运维

```bash
docker compose ps
docker compose logs -f backend
docker compose restart
docker compose down          # 保留数据卷
# docker compose down -v     # 危险：删除数据卷，仅限全新环境
```

---

## 7. 故障排查

| 现象 | 排查 |
|---|---|
| frontend 502 | `docker compose logs backend`；backend health 依赖 MySQL |
| 迁移失败 | 看 backend 启动日志中的 alembic 输出；确认 MySQL healthy |
| 登录 401 | 核对 `DMS_ADMIN_*`；账号是否被禁用 |
| 扫描不跑 | `POST /api/v1/scanner/run`；检查 `SCANNER_ENABLED` |
| 导入失败 | 看 `/api/v1/imports/{id}/errors`；确认 ≤2000 行、≤5MB |

---

## 8. 相关文档

- 用户操作：`docs/USER_MANUAL.md`
- 备份恢复：`docs/BACKUP_RESTORE.md`
- 发布清单：`docs/RELEASE_CHECKLIST.md`
- 验收结论：`docs/M6_ACCEPTANCE_REPORT.md`

# DMS V1.0 发布清单（Release Checklist）

> 用途：上线前逐项勾选。任一 P0 未完成不得宣布 V1.0 验收完成。

---

## A. 代码与版本

- [x] M1～M5 功能代码冻结（仅 M6 测试/修复/加固）
- [x] 无擅自新增业务模块
- [x] 数据库变更均经 Alembic（当前 head：`0005_m5_reports_scope`）
- [x] `.env` 不入库；`.env.example` 仅占位符
- [ ] 打 Git tag / 发布制品（由项目负责人执行；本工作区当前非 git 仓库）

## B. 测试与验收

- [x] 后端全量 pytest：**81 passed**
- [x] 前端 `vue-tsc` / `npm run build`：通过
- [x] 前端 Vitest：**4 passed**
- [x] Playwright E2E：**6 passed**（含真实分床全流程 / 409 / 不可用床位）
- [x] P0-1 部门数据隔离（含 Dashboard 员工类指标）
- [x] P0-2 真实浏览器分床流程
- [x] P0-3 业务全生命周期
- [x] P0-4 备份恢复 + 全新库迁移
- [x] P0-5 部署与安全
- [x] 并发/幂等测试通过
- [x] 性能 smoke：列表 p95 < 2s

## C. 数据

- [x] 备份脚本可用并完成一次真实备份
- [x] 隔离库恢复演练通过（表计数一致）
- [x] 历史员工 Excel 导入演练通过
- [ ] 生产库上线前全量备份（上线窗口执行）
- [ ] 备份异地/加密存放（运维配置）

## D. 部署与配置

- [x] `docker compose build && up -d` 三服务 healthy
- [x] 重启后服务恢复（restart 验证）
- [x] MySQL 仅绑定 `127.0.0.1`（或生产删除 ports）
- [x] `SECRET_KEY` / 库口令 / 管理员口令为强随机
- [ ] `APP_ENV=production`
- [ ] `ENABLE_API_DOCS=false`（或按需保留内网文档）
- [ ] HTTPS 证书就位并启用 `deploy/nginx/ssl.conf.example`
- [ ] CORS 源改为正式域名
- [ ] 管理员首次登录后改密
- [ ] 时钟同步（NTP）；确认 UTC 日切符合业务习惯

## E. 运维就绪

- [x] 每日备份 cron/计划已文档化
- [x] 恢复步骤已文档化
- [x] 预留过期扫描默认开启（60s）
- [ ] 监控/告警接入（CPU/磁盘/5xx/备份失败）
- [ ] 日志采集与保留策略
- [ ] 值班与故障联系人

## F. 文档交付

- [x] `docs/M6_ACCEPTANCE_REPORT.md`
- [x] `docs/DEPLOYMENT.md`
- [x] `docs/USER_MANUAL.md`
- [x] `docs/BACKUP_RESTORE.md`
- [x] `docs/RELEASE_CHECKLIST.md`（本文件）

---

## 上线日操作顺序（摘要）

1. 全量备份生产库（若已有数据）。
2. `docker compose pull/build && up -d`。
3. 确认 `alembic` 升到 head、`/health` 200。
4. 管理员登录冒烟：员工列表 / 分床 / 报表导出 / 待办。
5. 配置 HTTPS 与生产环境变量。
6. 观察 24h 错误日志与扫描任务。

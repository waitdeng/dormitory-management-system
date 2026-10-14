# M6 验收报告：综合验收、备份恢复与上线准备

> 验收日期：2026-10-14  
> 验收范围：`DMS_V1.0_MiMo_Development_Spec.md` §16 M6 + `AGENTS.md` M6 + 用户 P0-1～P0-5  
> 验收方式：真实 MySQL 8.0 自动化测试 + Playwright 真实浏览器业务流 + 备份恢复演练 + Docker 重建 + 性能 smoke  
> **验收结论：通过（具备上线条件）**

---

## 1. 全量测试结果

| 范围 | 命令 | 结果 |
|---|---|---|
| 后端 M1～M6（含并发/幂等/P0） | `cd backend && python -m pytest -q` | **81 passed** |
| 前端类型检查 | `npm run typecheck` | **0 error** |
| 前端构建 | `npm run build` | **成功** |
| 前端 Vitest | `npm test` | **4 passed** |
| Playwright E2E | `npx playwright test` | **6 passed** |

后端 81 = M5 的 75 + M6 新增 6（`tests/test_m6_p0.py`）。

E2E 6 = M5 页面级 3 + M6 真实分床业务 3。

---

## 2. P0 场景测试结果

### P0-1 部门数据隔离 — **通过**

| 检查项 | 实现/测试 | 结果 |
|---|---|---|
| 员工/住宿/待办/预警/报表/导出按范围过滤 | M5 `data_scope` + 既有 P0 | **通过**（回归） |
| Dashboard 员工类指标范围化 | `today_checkin/checkout`、`terminated_still_housed`、`active_alerts`、`pending_todos`、`housed_employees`、trends | **通过**（M6 修复） |
| `department_housed` 不泄露他部门 | 范围过滤后再排序截断 | **通过** |
| 空范围用户员工类 KPI 全 0 | `test_p0_empty_scope_sees_no_employee_dashboard_data` | **通过** |
| 修改查询参数无法越权 | M5 回归 | **通过** |

**口径（D-036）**：宿舍设施容量指标（床位总量/占用/空床/入住率）为全局资源库存，供分床决策使用，不暴露员工或其他部门人事数据；员工关联指标一律按范围过滤。

**修复**：原 Dashboard `date.today()` 本地时区导致「今日入住」与 UTC 存储错位（D-037 改为 UTC 日历）；`department_housed` 原先 `limit(20)` 后再过滤会丢弃授权部门，已改为过滤后截断。

### P0-2 真实浏览器分床流程 — **通过**

| 场景 | 覆盖 | 结果 |
|---|---|---|
| 选择员工 → 选择空床 → 提交 → 预留成功 → 确认入住 → 状态刷新 | `e2e/m6.spec.ts` 全流程 + 后端 room-cards 核对 | **通过** |
| 并发分床 409：明确提示并刷新 | 模拟竞态（API 抢占后 UI 分配） | **通过** |
| 不可用床位无法错误分配 | 停用床按钮 disabled；已入住床 disabled | **通过** |
| 页面空床数与后端一致 | room-cards `available/occupied` 与 UI 标签一致 | **通过** |

非“仅打开页面”测试，覆盖真实点击、确认框、成功/冲突消息与刷新。

### P0-3 业务全生命周期 — **通过**

`test_p0_full_lifecycle_hire_to_archive`：

入职创建员工 → 申请/批准/预留/确认入住 → 调宿（历史两条：ended/transfer + active）→ 离职办理生成退宿待办 → 离职未退宿预警 → 床位不自动释放 → 行政检查+确认退宿 → 床位释放 → 待办完成、预警关闭 → 历史归档 → 台账不再包含该员工。

每阶段均校验 API 返回的住宿状态、床位 `available`、待办/预警与台账一致性。

### P0-4 数据安全及恢复 — **通过**

| 项目 | 结果 |
|---|---|
| 真实 mysqldump 备份 | `backups/dms_20261013T165238Z.sql.gz`（~756KB） |
| 隔离库实际恢复 | `dms_restore_test` 导入成功 |
| 数据核对 | employees 857 / beds 1241 / accommodations 569 / checkouts 267 / users 209 / roles 5 / permissions 27 **完全一致** |
| Alembic 全新库 | `dms_migrate_fresh`：`0001→0005` 成功，26 表 + active 唯一索引生效 |
| 正式数据 | **未清空、未覆盖** |

脚本加固：`backup.sh` 增加 `--no-tablespaces`（普通用户无 PROCESS）；`restore.sh` 支持目标库参数，便于隔离演练。

### P0-5 部署与安全 — **通过**

| 检查项 | 结果 |
|---|---|
| 环境变量/密钥 | `.env.example` 占位；SECRET_KEY/库口令/管理员口令经环境注入 |
| HTTPS 方案 | `deploy/nginx/ssl.conf.example`（TLS1.2+、HSTS、301→HTTPS） |
| MySQL 网络 | 仅 `127.0.0.1:3306`，不对公网 |
| 认证授权 | 未登录 401；越权 403（finance_viewer 不能建用户/分床/建宿舍） |
| 敏感信息 | 日志不落明文口令/令牌；审计不含密码哈希 |
| Excel 导出 | 公式注入防护；导出内容无 `=` 公式单元格 |
| Compose 重启 | `docker compose restart` 后三服务 healthy，`/health` 200 |
| 预留过期扫描 | 进程内 60s；`POST /api/v1/scanner/run` 可手动触发 |
| 生产 API 文档 | `APP_ENV=production` 且 `ENABLE_API_DOCS=false` 时隐藏 `/api/docs` |
| 上传限制 | 服务端 5MB + nginx `client_max_body_size 8m` |

---

## 3. 性能及并发测试结果

### 性能 smoke（`backend/tests/perf_smoke.py`，20 次/接口）

| 接口 | avg | p95 | max |
|---|---|---|---|
| `/employees` 列表 | 6.3ms | 8.0ms | 14.4ms |
| `/employees` 搜索 | 5.5ms | 6.1ms | 6.7ms |
| `/reports/accommodations` | 26.6ms | 39.8ms | 66.5ms |
| `/reports/vacant-beds` | 24.8ms | 30.5ms | 46.3ms |
| `/dashboard/summary` | 8.5ms | 9.1ms | 11.7ms |
| `/dormitories/tree` | 39.1ms | 57.1ms | 59.8ms |
| `/workflow/todos` | 5.6ms | 6.7ms | 25.6ms |
| Dashboard ×20 并发 | — | 94.2ms | 94.9ms（20/20 成功） |

**结论**：列表/搜索 p95 ≪ 2s 目标；并发可用性 100%。

### 并发/幂等

- 同床并发预留/分床仅一笔成功（409）
- 同员工并发分配不双占
- 调宿与退宿竞态事务裁决
- 重复确认入住/退宿/离职事件幂等
- 扫描任务可安全重试

（`test_accommodation_concurrency.py`、`test_m5_allocation_p0.py`、`test_m4_offboarding_p0.py` 均通过）

---

## 4. 数据库备份恢复结果

见 §2 P0-4 与 `docs/BACKUP_RESTORE.md`。演练在隔离库完成，正式数据未破坏。

---

## 5. 历史 Excel 数据迁移结果

`backend/tests/historical_import_drill.py`（305 行历史员工台账）：

| 阶段 | 结果 |
|---|---|
| 预览 | total 305 / create 301 / error 4 |
| 提交 | created 301 / failed 4 / job `completed_with_errors` |
| 错误行 | 空工号 1、重复工号 2、坏部门/坏日期 1（可下载错误报告） |
| 样本查询 | 导入工号可检索 |
| 导出 | xlsx 正常，**0 个公式单元格** |

**结论**：两阶段导入（preview → commit）可支撑历史员工批量迁移；错误行可修正重导。

---

## 6. 生产环境安全检查结果

见 §2 P0-5。另：

- `compose.yaml` 注释明确生产应删除或保持 127.0.0.1 端口映射
- Nginx 增加 `Referrer-Policy`、上传体积限制
- Argon2id 口令、可撤销刷新令牌、RBAC 后端强制

---

## 7. 已修复问题和遗留风险

### M6 修复

| # | 问题 | 严重程度 | 处理 |
|---|---|---|---|
| 1 | Dashboard 员工类 KPI 未按部门范围过滤 | **高（P0）** | 全部员工关联指标接入 `apply_employee_scope` |
| 2 | Dashboard `date.today()` 本地时区 vs UTC 存储 | 中 | 改为 `utcnow().date()`（D-037） |
| 3 | `department_housed` 先 limit 再过滤导致授权部门丢失 | 中 | 过滤后按在住排序截断 |
| 4 | `backup.sh` 无 PROCESS 权限导致 tablespaces 报错 | 中 | `--no-tablespaces --set-gtid-purged=OFF` |
| 5 | `restore.sh` 无法恢复到隔离库 | 中 | 支持第二参数目标库 + 自动建库授权 |
| 6 | 生产环境仍暴露 `/api/docs` | 低 | `APP_ENV=production` 且默认可关（`ENABLE_API_DOCS`） |
| 7 | nginx 缺少上传体积限制 | 低 | `client_max_body_size 8m` |

### 遗留风险（不阻塞上线）

1. **Playwright 使用系统 Chrome**（`channel: 'chrome'`）；CI 建议 `npx playwright install chromium`。
2. **部门授权 UI**：`PUT /users/{id}/departments` 可用；设置页暂无图形化授权编辑器（可用 API/种子）。
3. **设施容量指标全局可见**（D-036）：若政策要求连空床数也隔离，需另行需求评审。
4. **预警阈值**仍为固定扫描策略（M4 遗留）。
5. **本工作区非 git 仓库**：无法在本环境打 tag/提交；版本管理需在正式仓库执行。
6. **多副本部署**：扫描任务为进程内定时；多实例需外置调度（V1.0 单实例可接受）。

---

## 8. 修改 / 新增文件摘要

### 后端

- `app/services/dashboard_service.py`：范围过滤 + UTC 日历
- `app/main.py` / `app/core/config.py`：生产可隐藏 API 文档
- `tests/test_m6_p0.py`：6 项 M6 P0
- `tests/perf_smoke.py`、`tests/historical_import_drill.py`：性能与历史导入演练脚本

### 脚本 / 部署

- `scripts/backup.sh`、`scripts/restore.sh`
- `frontend/nginx.conf`、`deploy/nginx/ssl.conf.example`

### 前端

- `frontend/e2e/m6.spec.ts`：真实分床 3 场景

### 文档

- `docs/M6_ACCEPTANCE_REPORT.md`（本文件）
- `docs/DEPLOYMENT.md` / `USER_MANUAL.md` / `BACKUP_RESTORE.md` / `RELEASE_CHECKLIST.md`
- `docs/DECISIONS.md`：D-036、D-037

---

## 9. 最终是否具备上线条件

### **M6 验收：通过 — 具备上线条件**

依据：

1. **P0-1～P0-5 全部通过**，无未关闭的 P0 缺陷；
2. 全量回归 **81 + 4 + 6** 全部通过；
3. 备份恢复与全新迁移为**真实执行**结果，正式数据未破坏；
4. 性能满足规格「列表 2s / 分床 3s」参考目标（实测 p95 < 60ms）；
5. 部署、用户手册、备份恢复、发布清单已交付；
6. 遗留风险均有缓解说明，不构成 V1.0 阻断。

**最终结论：V1.0 M6 通过，可按 `docs/RELEASE_CHECKLIST.md` 执行上线。**

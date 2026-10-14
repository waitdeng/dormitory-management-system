# DMS V1.0 代码审查修复报告

> 修复窗口：2026-10-14  
> 范围：`DMS_V1_CODE_REVIEW_AND_MIMO_FIX_TASK.md` 中 DMS-P1-001 … DMS-P3-011  
> 部署场景：公司内网、单 backend 实例  
> 约束：不改登录机制大改、不做公网安全体系、不做多实例架构重写；不重置数据库/删卷/覆盖正式数据；API 格式、状态机、MySQL 约束、审计、部门数据范围、历史记录保持兼容。

---

## 0. 执行摘要

| 类别 | 数量 | 结果 |
|---|---|---|
| P1 必修 | 4 | 全部修复并通过失败复现 → 修复 → 回归 |
| P2 业务健壮性/部署 | 6 | 5 项修复/说明；2 项条件触发仅补文档 |
| P3 文档 | 1 | README/DEPLOYMENT/DECISIONS/.env.example 已对齐 |
| 后端 pytest | — | **97 passed**（隔离库 `dms_p1fix_test`） |
| 前端 typecheck / Vitest / build | — | 通过 / **4 passed** / 通过 |
| Playwright E2E | — | **6 passed**（本地 Docker 栈） |
| Compose 校验 | — | `compose.yaml` + `compose.production.yaml` 通过 |
| 备份/恢复演练 | — | 隔离库备份 → `dms_p1fix_restore`，行数/约束/迁移版本一致 |

**生产数据**：`dms` 库未做破坏性变更（未 TRUNCATE/DELETE/迁移回滚/删卷）。Playwright E2E 按既有套件设计在本地开发栈上创建了少量测试员工/床位（+4 员工 / +6 床位），未删除或覆盖既有记录。

---

## 1. 逐条问题

### DMS-P1-001 — 批量提交缺少单行事务隔离

| 项 | 内容 |
|---|---|
| **修复状态** | 已修复 |
| **触发场景** | 三行导入（有效工号、超长工号触发 MySQL `DataError`、有效工号），或任意单行 `IntegrityError`/`DataError` |
| **根因** | `commit_employee_import` 逐行 `db.add()`/`flush()`，`except Exception` 后继续；无 SAVEPOINT。一旦某行 flush 失败，Session 进入 `PendingRollbackError`，后续行与最终 `commit()` 全部失败，先前成功行一并丢失 |
| **修改文件** | `backend/app/services/employee_service.py` |
| **关键实现** | 每行包在 `async with db.begin_nested():`（SAVEPOINT）内；成功 `RELEASE` 后才累加 `created/updated/applied`；失败行收集后不影响外层事务；禁止循环内 `db.rollback()` |
| **测试** | `tests/test_code_review_p1.py::test_p1_001_import_partial_success_after_db_error`、`::test_p1_001_import_audit_matches_persisted_rows` |
| **结果** | 修复前：`PendingRollbackError`，0 行落库、job 仍 `previewed`；修复后：2 成功 1 失败，job=`completed_with_errors`，审计 `created=2/errors=1` 与落库一致 |
| **风险/未完成** | 无。批量更新语义未变 |

### DMS-P1-002 — 预览“新增”提交时静默变成“覆盖更新”

| 项 | 内容 |
|---|---|
| **修复状态** | 已修复 |
| **触发场景** | A：preview=create 后另一会话插入同工号 → 提交曾静默 update 覆盖姓名/电话；B：preview=update 后目标被删 → 提交曾静默 create |
| **根因** | commit 中 `if action == "create" and existing is not None: action = "update"` 及反向翻转，违反 preview/commit 意图一致 |
| **修改文件** | `backend/app/services/employee_service.py` |
| **关键实现** | 去掉 create↔update 翻转；状态漂移按行 `ConflictError`（message 含 `conflict`、工号、需重新预览）；preview=update 且目标仍存在时**继续允许批量更新**（既有产品语义） |
| **测试** | `test_p1_002_preview_create_not_silently_updated`、`test_p1_002_preview_update_not_silently_recreated`、`test_p1_002_bulk_update_still_works_when_preview_matches` |
| **结果** | 覆盖/重建均不再发生；对方写入字段保持不变；批量更新路径 1/1 通过 |
| **风险/未完成** | 操作员需在漂移后重新预览。未引入“强制覆盖”策略（未获批准） |

### DMS-P1-003 — 预留扫描与入住锁顺序不一致

| 项 | 内容 |
|---|---|
| **修复状态** | 已修复（预防性对齐设计锁序） |
| **触发场景** | 扫描过期同一预留 vs `confirm_checkin` 并发 |
| **根因** | `_expire_one_reservation` 先锁 `BedReservation` 再锁床位；`confirm_checkin` 为 员工→床位→预留。交叉持有可形成锁等待环（证据 B） |
| **修改文件** | `backend/app/services/scanner_service.py` |
| **关键实现** | 无锁 peek 拿 employee_id/bed_id → `lock_employee` → `lock_beds`（id 升序）→ 预留/住宿 `FOR UPDATE` → 重检后过期。与 `occupancy.py` 文档锁序一致 |
| **测试** | `test_p1_003_scanner_lock_order_matches_design`（spy 断言 employee 先于 bed）、`test_p1_003_concurrent_confirm_vs_scan_many_rounds`（5 轮竞态，15s 超时）、`test_p1_003_confirm_and_expiry_scan_do_not_deadlock`、`test_p1_003_successful_checkin_not_undone_by_scan` |
| **结果** | 锁序断言通过；5 轮竞态无死锁/无永久等待；已确认入住不被扫描撤销 |
| **是否复现原死锁** | **本轮竞态测试未直接打出 InnoDB 死锁**（单实例 + 快事务）。按任务单 B 级要求：给出测试设计与结果，不以“未复现”否定锁逆序风险；以设计文档锁序为准做最小对齐，不推翻现有事务实现 |
| **风险/未完成** | 未做多实例/高负载死锁注入；保留“不释放已入住床位”不变量 |

### DMS-P1-004 — 确认入住/调宿前未校验预留有效期

| 项 | 内容 |
|---|---|
| **修复状态** | 已修复 |
| **触发场景** | `expires_at` 已过但扫描未跑，仍可确认入住/完成调宿 |
| **根因** | `confirm_checkin` / `complete_transfer` 只检查 `status == "active"`，未判断 `expires_at` |
| **修改文件** | `backend/app/services/checkin_service.py`、`backend/app/services/transfer_service.py`、`backend/app/schemas/accommodation.py`、`backend/app/api/v1/endpoints/transfers.py` |
| **关键实现** | 锁内：`expires_at is not None and expires_at <= utcnow()` → `ConflictError`（409）。`expires_at is None` = 无有效期，行为不变。调宿预留增加**可选** `expires_at`（向后兼容，默认无过期）。不提供管理员静默越权 |
| **测试** | `test_p1_004_confirm_rejects_expired_reservation`、`test_p1_004_transfer_complete_rejects_expired_reservation`、`test_p1_004_no_expiry_and_future_expiry_still_confirm`；并更新 `test_m4_workflow.py::test_checked_in_bed_not_released_by_expiry_scan`（原用例依赖过期后确认，改为确认后再把 expires_at 推到过去再扫描） |
| **结果** | 过期确认/完成返回 409；无过期与未到期仍 200；已入住床不被扫描释放 |
| **风险/未完成** | 临界时刻以 `<=` 判定（比扫描的 `<` 略严一拍）。业务上需重新预留后再确认 |

### DMS-P2-005 — 导入任务并发提交

| 项 | 内容 |
|---|---|
| **修复状态** | 已修复 |
| **触发场景** | 两个请求同时 commit 同一 `import_job` |
| **根因** | 读 `ImportJob` 无行锁，状态检查可被并发穿透 |
| **修改文件** | `backend/app/services/employee_service.py` |
| **关键实现** | `SELECT … FOR UPDATE` + 同事务认领 `status`；第二笔等待行锁后看到终态并 409 |
| **测试** | `test_p2_005_concurrent_commit_same_import_job`、`test_p2_005_sequential_double_commit_rejected` |
| **结果** | 并发下员工仅 1 条；顺序双提交第二次 409 |

### DMS-P2-006 — Excel 工作簿资源释放

| 项 | 内容 |
|---|---|
| **修复状态** | 已修复 |
| **触发场景** | 缺表头 / 空表 / 超 2000 行 / 非 xlsx / >5MB |
| **根因** | `wb.close()` 仅在正常路径末尾；`ValidationError` 提前退出时未关闭 |
| **修改文件** | `backend/app/services/employee_service.py` |
| **关键实现** | 解析+校验整体 `try/finally: wb.close()`；保持 5MB / 2000 行限制 |
| **测试** | `test_p2_006_preview_releases_workbook_on_bad_files` |
| **结果** | 5 类坏文件均 400/422；随后合法 preview 仍 200 |

### DMS-P2-007 — API 文档 production 默认暴露

| 项 | 内容 |
|---|---|
| **修复状态** | 已修复 |
| **触发场景** | `APP_ENV=production` 且未显式关闭时仍可开 `/api/docs` |
| **根因** | `ENABLE_API_DOCS` 默认 `True` |
| **修改文件** | `backend/app/core/config.py`、`compose.yaml`、`compose.production.yaml`、`.env.example`、`docs/DEPLOYMENT.md` |
| **关键实现** | 默认 `False`；`APP_ENV != production` 仍开放；production 需 `ENABLE_API_DOCS=true` 显式打开 |
| **测试** | `test_p2_007_api_docs_setting_defaults` |
| **结果** | 默认生产不暴露；开发/测试不受影响；业务 API 不变 |

### DMS-P2-008 — Docker 数据库端口冲突

| 项 | 内容 |
|---|---|
| **修复状态** | 已修复（双模式） |
| **触发场景** | 宿主机已有 MySQL 占用 3306 |
| **修改文件** | `compose.yaml`（注释）、**新增** `compose.production.yaml`、`docs/DEPLOYMENT.md`、`README.md` |
| **关键实现** | 开发：保留 `127.0.0.1:${MYSQL_HOST_PORT:-3306}`；生产：`compose.production.yaml` 用 `ports: !reset []` 去掉映射。备份仍 `docker exec` |
| **测试** | `docker compose -f compose.yaml config` OK；`-f compose.yaml -f compose.production.yaml config` 显示 mysql **无 ports** |
| **结果** | 未改正在运行容器数据卷；生产模式不依赖宿主机 3306 |

### DMS-P2-009 — Refresh Token 旋转并发保护

| 项 | 内容 |
|---|---|
| **修复状态** | **本轮不修改**（内网暂缓） |
| **触发场景** | 两请求并发 refresh 同一 token |
| **根因** | 读取后置 `revoked_at`，无原子单次消费约束 |
| **不修改依据** | 任务单明确“内网暂缓、不作为业务上线阻断、不做登录机制大改”。单实例 + 短窗口并发概率低 |
| **文档** | `docs/DECISIONS.md` D-046；`docs/DEPLOYMENT.md` 已述认证边界 |
| **后续** | 认证重构时加行锁/条件更新并补并发测试 |

### DMS-P2-010 — 多副本扫描任务重入

| 项 | 内容 |
|---|---|
| **修复状态** | **本轮不修改**（条件触发，仅补部署说明） |
| **触发场景** | 多 worker / 多 backend 副本 |
| **不修改依据** | V1 为单实例；任务单要求“不用为未采用的集群架构重写调度” |
| **文档** | `README.md`、`docs/DEPLOYMENT.md`：明确单实例前提与扩容后果 |
| **后续** | 多副本前改为独立调度或分布式锁 |

### DMS-P3-011 — README 里程碑状态过时

| 项 | 内容 |
|---|---|
| **修复状态** | 已修复 |
| **修改文件** | `README.md`、`docs/DEPLOYMENT.md`、`docs/DECISIONS.md`、`.env.example` |
| **关键实现** | M2–M6 标为已完成并附日期；测试章节区分“命令”与“以报告为准”，避免历史结果冒充本轮；补充生产 Compose 双模式、API 文档默认、单实例扫描说明 |

---

## 2. 回归范围（任务单第 3 节）

| 模块 | 做法 | 结果 |
|---|---|---|
| 入住/调宿/退宿事务 | 既有 `test_accommodation*.py` + 新 P1 用例 | 全部通过 |
| 离职联动 | `test_m4_*` | 通过（含更新后的过期扫描用例） |
| 报表/看板/部门数据范围 | `test_m5_*` | 通过；设施容量全局口径未改动 |
| 备份恢复 | 隔离库备份/恢复演练 | 见 §3 |
| 前端 client/冲突/重复点击 | Vitest + Playwright E2E | 4 + 6 通过 |

---

## 3. 实际执行的命令与结果

> 所有后端 pytest 使用**隔离库** `dms_p1fix_test`（已迁移 + seed），不操作 `dms` 正式库做写入断言。  
> 工作目录：`/Users/easonli/XiaomiMiMoProjects/dormitory-management-system`  
> 说明：本地目录**不是 git 仓库**（`git status` → `fatal: not a git repository`），故无法提供 diff/commit；未推送到 GitHub。

### 3.1 后端

```bash
cd backend && MYSQL_DATABASE=dms_p1fix_test .venv/bin/python -m pytest -q
# 97 passed in ~24–28s
```

含新增：

```bash
cd backend && MYSQL_DATABASE=dms_p1fix_test .venv/bin/python -m pytest tests/test_code_review_p1.py tests/test_code_review_p2.py -q
# 16 passed
```

P1 复现（修复前曾失败）：

| 测试 | 修复前 | 修复后 |
|---|---|---|
| `test_p1_001_import_partial_success_after_db_error` | FAIL `PendingRollbackError` | PASS |
| `test_p1_001_import_audit_matches_persisted_rows` | FAIL | PASS |
| `test_p1_002_preview_create_not_silently_updated` | FAIL 静默覆盖 | PASS |
| `test_p1_002_preview_update_not_silently_recreated` | FAIL 静默重建 | PASS |
| `test_p1_004_confirm_rejects_expired_reservation` | FAIL 200 而非 409 | PASS |
| `test_p1_004_transfer_complete_rejects_expired_reservation` | FAIL 200 而非 409 | PASS |

### 3.2 前端

```bash
cd frontend && npm run typecheck   # 通过（无输出错误）
cd frontend && npm test            # 4 passed（Vitest）
cd frontend && npm run build       # built in ~4.3s
cd frontend && npx playwright test # 6 passed（E2E_BASE_URL=http://127.0.0.1:8080）
```

### 3.3 Docker Compose

```bash
docker compose config                                      # OK
docker compose -f compose.yaml -f compose.production.yaml config
# mysql.ports = 空（!reset 生效）
docker compose build backend frontend && docker compose up -d backend frontend
curl -s http://127.0.0.1:8080/health                       # {"status":"ok",...}
```

### 3.4 备份/恢复（隔离库）

```bash
MYSQL_DATABASE=dms_p1fix_test ./scripts/backup.sh /tmp/dms_backup_drill
./scripts/restore.sh /tmp/dms_backup_drill/dms_p1fix_test_*.sql.gz dms_p1fix_restore
```

| 项 | 源 `dms_p1fix_test` | 目标 `dms_p1fix_restore` |
|---|---|---|
| employees | 423 | 423 |
| import_jobs | 56 | 56 |
| audit_logs | 3914 | 3914 |
| alembic_version | `0005_m5_reports_scope` | `0005_m5_reports_scope` |
| 重复工号 | 0 | 0（UNIQUE 保持） |

**未执行 / 未验证**

- 未对正式库 `dms` 做恢复切换演练（避免覆盖正式数据）。
- 未在多 worker / 多副本下压测扫描重入（P2-010 条件触发）。
- 未实现 refresh token 并发行锁（P2-009 暂缓）。
- 本地无 git，未生成 commit / 未推送 GitHub。
- 死锁注入（强制锁环）未做；P1-003 以锁序 spy + 竞态超时回归为准。

---

## 4. 修改文件清单

| 文件 | 变更 |
|---|---|
| `backend/app/services/employee_service.py` | P1-001 SAVEPOINT；P1-002 禁止翻转；P2-005 FOR UPDATE；P2-006 try/finally |
| `backend/app/services/scanner_service.py` | P1-003 锁顺序 |
| `backend/app/services/checkin_service.py` | P1-004 到期校验 |
| `backend/app/services/transfer_service.py` | P1-004 到期校验 + 预留 `expires_at` |
| `backend/app/schemas/accommodation.py` | `TransferReserveRequest.expires_at`（可选） |
| `backend/app/api/v1/endpoints/transfers.py` | 透传 `expires_at` |
| `backend/app/core/config.py` | `ENABLE_API_DOCS` 默认 false |
| `compose.yaml` | 注释 + `ENABLE_API_DOCS` 环境 |
| `compose.production.yaml` | **新增** 生产覆盖（无 MySQL ports） |
| `.env.example` | 文档/扫描相关变量说明 |
| `README.md` | 里程碑对齐、测试/部署说明 |
| `docs/DEPLOYMENT.md` | 双 Compose 模式、单实例扫描、API 文档 |
| `docs/DECISIONS.md` | D-038 … D-046 |
| `backend/tests/test_code_review_p1.py` | **新增** P1 复现/回归 |
| `backend/tests/test_code_review_p2.py` | **新增** P2 测试 |
| `backend/tests/test_m4_workflow.py` | 适配 P1-004 的过期扫描用例 |

---

## 5. 验收对照（任务单 §5）

- [x] DMS-P1-001：单行失败后部分成功，汇总与审计准确
- [x] DMS-P1-002：预览/提交动作一致，无静默覆盖
- [x] DMS-P1-003：锁顺序对齐；并发无永久等待；成功入住不被撤销
- [x] DMS-P1-004：到期预留不能确认，规则与测试一致
- [x] DMS-P2-005：相同导入任务并发提交安全
- [x] DMS-P2-006：异常 Excel 全路径释放资源
- [x] DMS-P2-007～011：适用项修复/说明（009/010 记录暂缓依据）
- [x] 入住、调宿、退宿、离职相关集成测试通过
- [x] 部门数据范围及报表/导出回归通过（既有 M5 用例）
- [x] MySQL 数据卷与既有员工数据无破坏性变更
- [x] 本报告；测试结果可追溯；未验证项已列出

---

## 6. 后续建议

1. 人工在预发环境走一遍 Excel 导入（含故意造一行超长工号）确认交互提示。
2. 若部署形态变为多 worker/多副本，先做 P2-010 调度改造再扩容。
3. 认证专项时处理 P2-009 refresh 并发。
4. 本地目录纳入 git 后，将本轮变更作为单独提交，便于回溯。

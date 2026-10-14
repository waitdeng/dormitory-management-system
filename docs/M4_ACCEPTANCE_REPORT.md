# M4 验收报告：离职联动、待办、预留过期与异常预警

> 验收日期：2026-10-13  
> 验收范围：`DMS_V1.0_MiMo_Development_Spec.md` §4.5 / §6.2 / §6.7 / §13 + `AGENTS.md` M4 + 用户 P0 场景 A～F  
> 验收方式：真实 MySQL 8.0 自动化测试（含并发）+ Docker 重建 + Nginx 运行时 HTTP 实测（非仅代码审阅）  
> **验收结论：通过**

---

## 1. M4 功能交付清单

| 规格 / 用户要求 | 实现情况 | 结论 |
|---|---|---|
| 员工离职办理及人事状态变更事件 | `POST /employees/{id}/offboarding\|terminate` + `employee_status_events`；PATCH 状态走同一管线 | 通过 |
| 离职后自动生成行政退宿待办 | 在住时自动开 `checkout_records(type=offboarding)` + `workflow_todos(checkout_offboarding)` | 通过 |
| 待办任务管理及待办中心 | `/workflow/todos*` + 前端 `/todos`（待办/预警 Tab） | 通过 |
| 床位预留到期自动扫描与释放 | `scanner_service.expire_reservations` + 进程内定时任务 + `/scanner/*` | 通过 |
| 离职未退宿、超期未入住等异常预警 | `workflow_alerts`（6 类）+ `/workflow/alerts*` | 通过 |
| 业务完成后自动关闭相关待办与预警 | checkout/transfer/checkin 完成时自动 complete todos / resolve alerts | 通过 |
| 业务操作审计及站内通知 | `audit_logs` + `notifications` | 通过 |
| 不提前开发 M5 可视化分床和统计报表 | 未实现 `bed-allocation` / reports 报表 | 通过 |

**P0 强制场景：A～F 全部通过（见 §4）。**

---

## 2. 数据库迁移及 API 变更

### 2.1 数据库（Alembic `0004_m4_workflow`）

| 表名 | 关键约束 |
|---|---|
| `employee_status_events` | `UNIQUE(source, source_event_id)` 事件幂等 |
| `workflow_todos` | 生成列 `open_business_key` + UNIQUE（同一业务至多一条 pending） |
| `workflow_alerts` | 生成列 `active_fingerprint` + UNIQUE（同一指纹至多一条 active） |
| `notifications` | 站内通知（user / role 定向） |

**未改动** M1～M3 既有表结构与数据。`employees.employment_status` 允许值扩展为 `pending / active / probation / offboarding / terminated / resigned / suspended`（规格 §4.3）。

### 2.2 后端 API（前缀 `/api/v1`）

**离职（权限 `employee:offboard`）**
- `POST /employees/{id}/offboarding` — 发起离职办理
- `POST /employees/{id}/terminate` — 确认离职
- `GET /employees/{id}/status-events` — 状态事件（`employee:view`）
- `GET /offboarding/pending-checkouts` — 离职待退宿

**待办 / 预警（`employee:view` / `dorm:view` / `checkout:view` / `report:view` 任一）**
- `GET /workflow/todos`、`GET /workflow/todos/summary`、`GET /workflow/todos/{id}`
- `POST /workflow/todos/{id}/complete|cancel`
- `GET /workflow/alerts`、`GET /workflow/alerts/summary`、`GET /workflow/alerts/{id}`
- `POST /workflow/alerts/{id}/resolve`
- `GET /workflow/notifications`

**扫描（`employee:offboard` 或 `bed:manage`）**
- `POST /scanner/run`、`POST /scanner/expire-reservations`、`POST /scanner/scan-alerts`

### 2.3 权限映射（复用既有权限码，无新增）

| 操作 | 权限码 |
|---|---|
| 发起/确认离职 | `employee:offboard` |
| 查询待办/预警 | `employee:view` 或 `dorm:view` 或 `checkout:view` 或 `report:view` |
| 完成/取消待办、解除预警 | 已认证用户（业务完成仍受原业务权限约束） |
| 执行扫描 | `employee:offboard` / `bed:manage` |

### 2.4 服务层

- `offboarding_service.py`：状态事件、退宿待办生成、离职未退宿预警（**绝不自动释放床位**）
- `workflow_service.py`：待办/预警/通知，`ensure_*` / `resolve_*` 幂等
- `scanner_service.py`：预留过期 + 5 类异常扫描；行锁下重检，可安全重试
- `checkout_service` / `transfer_service` / `checkin_service`：业务完成时自动关闭待办与预警
- `tasks/scanner.py`：进程内 asyncio 周期任务（默认 60s）

### 2.5 前端

| 路由 | 页面 | 说明 |
|---|---|---|
| `/todos` | `TodosView.vue` | 待办中心：待办/预警列表、完成/取消/解除、扫描触发 |
| `/employees` | `EmployeesView.vue` | 增加「发起离职 / 确认离职」；状态含 offboarding/terminated |

---

## 3. 测试项目、执行命令与结果

### 3.1 后端静态检查

| 项目 | 命令 | 结果 |
|---|---|---|
| 代码风格 | `ruff check app tests` | **All checks passed** |
| 语法编译 | `python -m compileall app` | **通过** |

### 3.2 后端自动化测试（真实 MySQL 8.0）

| 项目 | 命令 | 结果 |
|---|---|---|
| M4 专项（P0+扫描） | `pytest tests/test_m4_offboarding_p0.py tests/test_m4_workflow.py -q` | **18 passed** |
| M1～M4 全量回归 | `pytest -q` | **60 passed** |

M4 新增 18 项（全部 PASSED）：

| 用例 | 覆盖 |
|---|---|
| `test_p0_a_offboarding_creates_checkout_todo_keeps_bed` | P0 A |
| `test_p0_b_terminated_still_housed_alert` | P0 B |
| `test_p0_c_repeated_events_idempotent` | P0 C |
| `test_p0_d_admin_checkout_closes_todo_and_alert` | P0 D |
| `test_p0_e_duplicate_checkout_confirm_idempotent` | P0 E |
| `test_p0_f_permission_hr_cannot_checkout_admin_cannot_offboard` | P0 F 权限 |
| `test_p0_f_concurrent_offboarding_and_checkout` | P0 F 并发 |
| `test_p0_f_concurrent_duplicate_offboarding_events` | P0 F 并发幂等 |
| `test_p0_f_concurrent_checkout_complete_and_alert_scan` | P0 F 并发 |
| `test_reservation_expiry_releases_bed` | 专项 1 |
| `test_checked_in_bed_not_released_by_expiry_scan` | 专项 2 |
| `test_cancelled_reservation_not_expired_again` | 专项 3 |
| `test_overdue_checkin_alert` | 专项 4 |
| `test_completed_todo_not_listed_as_pending` | 专项 5 |
| `test_repeated_scans_do_not_duplicate` | 专项 6 |
| `test_scanner_safe_retry_after_partial_failure` | 专项 7 |
| `test_offboarding_pending_checkouts_endpoint` | 离职待退宿 |
| `test_todo_complete_and_alert_resolve_apis` | 待办/预警 API |

全量回归 60 = M3 时 42 + M4 新增 18。

### 3.3 前端

| 项目 | 命令 | 结果 |
|---|---|---|
| TypeScript 严格检查 | `npm run typecheck` | **通过（0 error）** |
| 生产构建 | `npm run build` | **成功**（含 TodosView / EmployeesView 离职按钮） |

### 3.4 数据库迁移

| 项目 | 命令 | 结果 |
|---|---|---|
| 迁移前版本 | `alembic current` | `0003_m3_accommodation` |
| 执行迁移 | `alembic upgrade head` | **成功** → `0004_m4_workflow` |

### 3.5 Docker Compose

| 项目 | 命令 | 结果 |
|---|---|---|
| 镜像重建 | `docker compose build backend` / `frontend --no-cache` | **成功** |
| 全栈启动 | `docker compose up -d` | mysql/backend/frontend **全部 healthy** |

---

## 4. P0 场景 A～F 逐项测试结果

### A. 员工进入离职办理 — **通过**

- `POST /employees/{id}/offboarding` → `employment_status=offboarding`
- 自动生成退宿单 + 1 条 pending `checkout_offboarding` 待办
- 床位 `occupied=true`、`available=false`；住宿记录 `active`
- 其他员工分配该床位 → **409**

### B. 员工正式离职但未退宿 — **通过**

- `employment_status=terminated`；住宿仍 `active`；床位仍 `occupied`
- 产生 `terminated_still_housed`（severity=critical）预警 1 条
- 原退宿待办仍为 `pending`
- `accommodation_status=in_dorm`（系统未自动释放）

### C. 重复离职事件 — **通过**

- 重复 `offboarding` / `terminate`（含相同 `idempotency_key`）→ `event_created=false`
- pending 待办数保持 1；active 预警数保持 1
- 住宿记录与床位占用不变
- `status-events` 无重复 `source_event_id`

### D. 行政确认实际退宿 — **通过**

- 住宿 `ended`（`end_reason=offboarding`，历史保留）
- 床位 `available=true`
- 关联待办自动 `completed`；`terminated_still_housed` 自动 `resolved`
- `employment_status` 仍为 `terminated`

### E. 重复退宿确认 — **通过**

- 再次 `POST .../complete` → 200 `completed`（幂等）
- 历史仍 1 条 ended，无重复结束记录
- 完成型业务事件不重复写入（第二次请求短路返回）

### F. 并发操作及权限隔离 — **通过**

| 检查 | 结果 |
|---|---|
| 离职与退宿确认同时执行 | 状态一致，至多 1 条 active 住宿 |
| 重复离职事件并发提交 | 待办恰好 1 条，床位仍占用 |
| 退宿完成与预警扫描同时执行 | 完成后无残留 active 预警 |
| 人事不能越权确认退宿 | HTTP **403** |
| 行政不能越权改离职状态 | `terminate`/`PATCH` → HTTP **403** |
| 超管正常执行 | 离职 + 退宿完成均 200 |

---

## 5. 预留过期和异常预警专项测试结果

| 专项 | 结果 |
|---|---|
| 床位预留到期后自动释放 | PASSED / Nginx scanner 正常 |
| 已正式入住的床位不会被过期扫描错误释放 | PASSED |
| 取消的预留不会再次产生过期事件 | PASSED |
| 超期未入住能够正确产生异常预警 | PASSED（确认入住后自动解除） |
| 待办完成后不会继续显示为未完成 | PASSED |
| 重复运行后台扫描任务不会产生重复记录 | PASSED |
| 扫描任务发生异常后可以安全重试 | PASSED（已过期跳过，可重复执行） |

---

## 6. M1～M4 全量回归测试结果

| 范围 | 命令 | 结果 |
|---|---|---|
| 认证/用户/权限（M1） | `pytest -q` 内含 | 通过 |
| 部门/员工/Excel/宿舍（M2） | 同上 | 通过 |
| 入住/调宿/退宿/并发（M3） | 同上 | 通过 |
| 离职联动/待办/预警（M4） | 同上 | 通过 |
| **合计** | `cd backend && python -m pytest -q` | **60 passed** |

---

## 7. Docker Compose 运行验证

```
docker compose build backend          → 成功
docker compose build --no-cache frontend → 成功
docker compose up -d                  → mysql / backend / frontend 全部 healthy
```

Nginx `http://127.0.0.1:8080` 实测（节选）：

```
GET  /api/v1/health/ready              → ready
POST /employees/{id}/offboarding       → offboarding, todo_id=60
GET  /workflow/todos?status=pending    → 1「离职退宿：张三」
GET  /rooms/{id}/beds                  → occupied=true
POST /employees/{id}/terminate         → terminated, alert_id=46
GET  /workflow/alerts                  → 1 × terminated_still_housed
POST /employees/{id}/terminate（重复）  → event_created=false, todos=1
POST /checkouts/{id}/complete          → completed, bed available, todos=0, alerts=0
POST /checkouts/{id}/complete（重复）   → completed, history_len=1
POST /scanner/run                      → 200
权限：HR offboarding=200 / HR complete=403 / 行政 terminate=403 / 超管=200
```

---

## 8. 问题修复记录

| # | 问题 | 严重程度 | 修复 |
|---|---|---|---|
| 1 | MySQL REPEATABLE READ 下并发事件幂等检查用普通 SELECT，可能看不到对端已提交事件 | 高 | `find_status_event` / `find_pending_todo` / alert 查询改为 `FOR UPDATE` 锁定读 |
| 2 | 自定义 `idempotency_key` 全局唯一，跨员工碰撞导致副作用丢失 | 中 | 键作用域改为 `emp{id}:{key}`；命中已有事件时 `ensure_*` 补齐副作用 |
| 3 | 退宿完成未自动关闭待办/预警 | 高 | `complete_checkout` 集成 `complete_todos_*` + `resolve_alerts` |
| 4 | 人员状态 PATCH 不会生成待办/预警 | 高 | `update_employee` 路由到 `apply_status_change` |
| 5 | 未提供 `offboarding` 人事状态 | 中 | Schema 扩展 `pending`/`offboarding` |

---

## 9. 无法执行 / 受环境限制的检查

| 项目 | 原因 | 影响评估 |
|---|---|---|
| 浏览器 UI 人工点击走查 | 当前环境无法打开图形浏览器 | 已用 HTTP 实测全部业务 API + 前端构建产物；UI 细节留待 M6 |
| 前端 Vitest 组件测试 | M1～M3 遗留 | 登记遗留，不阻塞 M4 |
| 多实例分布式定时任务 | V1.0 单进程部署 | 进程内扫描幂等，多实例重复扫描安全 |

---

## 10. 遗留风险及 M5 准备情况

1. **部门数据范围过滤** — 住宿/待办列表尚未按 `dept_manager` 部门过滤（M1/M2 遗留，属 M5 数据范围）。
2. **前端 Vitest** — 仍无组件用例；建议 M6 前补齐。
3. **预警阈值可配置** — 超期天数目前固定（过期即扫）；如需业务日阈值可在 M5/M6 扩展配置。
4. **M5 就绪** — 可视化分床、台账/统计可复用 `occupancy.derive_bed_flags`、`workflow_alerts` 与既有查询；报表导出仍待实现。

---

## 11. 验收结论

### **M4 验收：通过**

理由：

1. P0 强制场景 A～F **全部通过**（自动化 + Nginx 实测），无「离职自动释放床位 / 重复待办 / 缺失预警 / 退宿后预警未解除 / 越权 / 历史丢失」等一票否决项；
2. 专项测试 7 项全部通过，覆盖预留过期、取消预留、超期入住、待办关闭、扫描幂等与安全重试；
3. M1～M4 全量回归 **60/60 通过**，`ruff` 与 `vue-tsc` 零错误；
4. Alembic `0004_m4_workflow` 迁移成功，生成列唯一约束在并发测试中生效；
5. Docker 三服务重建后 healthy，经 Nginx 完整走通离职→待办→预警→退宿闭环；
6. 发现的 5 个问题（含 2 个高优先级）均已修复并回归通过。

**最终结论：M4 通过，可进入 M5。**

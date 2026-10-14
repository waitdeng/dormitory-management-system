# M3 验收报告：完整住宿事务闭环（入住 / 预留 / 调宿 / 退宿 / 历史）

> 验收日期：2026-10-13  
> 验收范围：`DMS_V1.0_MiMo_Development_Spec.md` §4/§5/§6.4–6.6 + `AGENTS.md` M3 要求  
> 验收方式：真实 MySQL 8.0 自动化测试（含并发）+ Docker 重建 + Nginx 运行时 HTTP 实测（非仅代码审阅）  
> **验收结论：通过**

---

## 1. M3 开发目标对照

| 规格 / AGENTS.md 要求 | 实现情况 | 结论 |
|---|---|---|
| 入住申请、批准、预留、确认、取消 | `accommodation_applications` 状态机 + `/checkin-applications/*` | 通过 |
| 床位预留与消耗 | `bed_reservations`（active/consumed/cancelled/expired） | 通过 |
| 入住确认生成住宿记录 | `accommodation_records` status=active | 通过 |
| 调宿：目标预留、原床释放、新旧关联 | `transfer_records` + 同事务 end/create/consume | 通过 |
| 退宿：检查、确认、释放床位 | `checkout_records` + 检查字段 + complete 结束住宿 | 通过 |
| 住宿历史管理 | `/accommodations/history`、`/employees/{id}/history` | 通过 |
| 重复有效入住唯一约束 | 生成列 UNIQUE：active 员工/床位各 1；未完结退宿单 1 | 通过 |
| M2 床位 occupied/reserved 占位替换 | 由 `accommodation_records` / `bed_reservations` 推导 | 通过 |
| 员工当前住宿及历史查询 | `/employees/{id}/accommodation|history` 返回真实数据 | 通过 |
| 统一行级锁顺序 + 事务 | 员工 → 床位升序 → 业务行；`occupancy.py` 共用 | 通过 |
| 幂等 / 防重复 | 确认/完成重复请求返回既有结果；可选 Idempotency-Key | 通过 |
| 不提前开发 M4 | 未建 `workflow_todos` / `employee_status_events` / 过期扫描 | 通过 |

---

## 2. 本次交付范围

### 2.1 数据库（Alembic `0003_m3_accommodation`）

| 表名 | 关键约束 |
|---|---|
| `accommodation_applications` | `UNIQUE(application_no)`、`UNIQUE(idempotency_key)` |
| `bed_reservations` | `UNIQUE(reservation_no)`；生成列 `active_employee_id` / `active_bed_id` + UNIQUE |
| `accommodation_records` | 生成列 `active_employee_id` / `active_bed_id` + UNIQUE；`chk_accommodation_dates` |
| `transfer_records` | `UNIQUE(transfer_no)`；`chk_transfer_beds_different` |
| `checkout_records` | `UNIQUE(checkout_no)`；生成列 `open_accommodation_id` + UNIQUE |

**未创建**（M4）：`employee_status_events`、`workflow_todos`、`idempotency_keys` 独立表。

### 2.2 后端 API（前缀 `/api/v1`）

**入住**
- `GET/POST /checkin-applications`
- `GET /checkin-applications/{id}`
- `POST /checkin-applications/{id}/approve|reject|reserve|confirm|cancel`

**住宿记录**
- `GET /accommodations/active`
- `GET /accommodations/history`
- `GET /accommodations/{id}`

**调宿**
- `GET/POST /transfers`，`GET /transfers/{id}`
- `POST /transfers/{id}/reserve|complete|cancel`

**退宿**
- `GET/POST /checkouts`，`GET /checkouts/{id}`
- `PATCH /checkouts/{id}/inspection`
- `POST /checkouts/{id}/complete|cancel`

**复用 M2 接口增强**
- `GET /employees/{id}/accommodation|history` 真实数据
- `GET /beds/available`、`GET /rooms/{id}/beds`、`GET /buildings/{id}/occupancy` 使用真实占用
- `POST /beds/{id}/disable` 占用/预留时拒绝

### 2.3 权限映射（复用既有权限码，无新增）

| 操作 | 权限码 |
|---|---|
| 入住查询 | `checkin:view` |
| 创建入住申请 | `checkin:create` |
| 批准/驳回/取消申请 | `checkin:approve` |
| 预留床位 | `checkin:allocate` |
| 确认入住 | `checkin:confirm` |
| 调宿查询/创建/预留 | `transfer:view` / `transfer:create` |
| 调宿完成/取消 | `transfer:complete` |
| 退宿查询/创建 | `checkout:view` / `checkout:create` |
| 退宿检查 | `checkout:inspect` |
| 退宿完成/取消 | `checkout:complete` |

### 2.4 服务层与锁

- `app/services/occupancy.py`：`lock_employee` → `lock_beds`（id 升序）→ 跨表冲突复检
- `checkin_service.py` / `transfer_service.py` / `checkout_service.py`：状态机 + 审计 + 幂等
- 冲突统一 `ConflictError`（HTTP 409）；状态非法 `ConflictError`；参数非法 `ValidationError`（400）

### 2.5 前端

| 路由 | 页面 | 说明 |
|---|---|---|
| `/checkins` | `CheckinsView.vue` | 申请列表、新建、批准/驳回、分床预留、确认入住、取消 |
| `/transfers` | `TransfersView.vue` | 调宿列表、新建、预留目标床、确认调宿、取消 |
| `/checkouts` | `CheckoutsView.vue` | 退宿列表、新建、房间检查、完成退宿、取消 |

类型与 API Client：`types/index.ts`（M3 段）、`api/accommodations.ts`。

---

## 3. 测试项目、执行命令与结果

### 3.1 后端静态检查

| 项目 | 命令 | 结果 |
|---|---|---|
| 代码风格 | `ruff check app tests` | **All checks passed** |

### 3.2 后端自动化测试（真实 MySQL 8.0）

| 项目 | 命令 | 结果 |
|---|---|---|
| 全量（M1+M2 回归 + M3） | `pytest -q` | **42 passed** |

M3 新增用例（18）：

| 用例 | 结果 |
|---|---|
| `test_checkin_full_flow` | PASSED |
| `test_checkin_duplicate_confirm_idempotent` | PASSED |
| `test_checkin_rejects_occupied_bed` | PASSED |
| `test_checkin_rejects_employee_already_housed` | PASSED |
| `test_checkin_reserve_requires_approved` | PASSED |
| `test_transfer_flow_keeps_history` | PASSED |
| `test_transfer_target_conflict_rolls_back` | PASSED |
| `test_transfer_same_bed_rejected` | PASSED |
| `test_checkout_flow_frees_bed` | PASSED |
| `test_checkout_duplicate_open_rejected` | PASSED |
| `test_checkout_complete_idempotent` | PASSED |
| `test_cancel_releases_reservation` | PASSED |
| `test_disable_bed_with_occupancy_rejected` | PASSED |
| `test_allocate_blocked_when_parent_disabled` | PASSED |
| `test_permission_denied_for_checkin` | PASSED |
| `test_concurrent_reserve_same_bed` | PASSED（1×200 + 1×409） |
| `test_concurrent_same_employee_allocate` | PASSED（重复确认仅 1 条 active） |
| `test_concurrent_transfer_and_checkout` | PASSED（至多 1 条 active，无悬空预留） |

覆盖的关键路径：
- 完整入住链路 pending→approved→reserved→checked_in
- 预留后确认：预留 consumed、生成 active 住宿
- 重复确认入住：幂等、不重复建 active 住宿
- 已入住房位再分配 → 409
- 同员工重复建单 → 409
- 未批准先预留 → 409
- 调宿：旧住宿 ended（end_reason=transfer）、新住宿 active、历史可查、原床 available
- 调宿目标冲突 → 事务回滚，源住宿不变
- 同床调宿 → 400
- 退宿完成：住宿 ended、床位释放、员工 not_in_dorm
- 同一住宿重复退宿单 → 409（生成列）
- 重复完成退宿 → 幂等
- 取消申请释放预留
- 占用床 disable → 409；上级停用后禁止分配
- 无 `checkin:create` → 403
- **并发同床预留仅一笔成功**
- **调宿/退宿竞态不产生多条 active 或悬空预留**

### 3.3 前端

| 项目 | 命令 | 结果 |
|---|---|---|
| TypeScript 严格检查 | `npm run typecheck` | **通过（0 error）** |
| 生产构建 | `npm run build` | **成功**（含 CheckinsView / TransfersView / CheckoutsView） |

### 3.4 数据库迁移

| 项目 | 命令 | 结果 |
|---|---|---|
| 迁移前版本 | `alembic current` | `0002_m2_master_data` |
| 执行迁移 | `alembic upgrade head` | **成功** → `0003_m3_accommodation` |
| 迁移后版本 | `alembic current` | `0003_m3_accommodation (head)` |

### 3.5 Docker Compose

| 项目 | 命令 | 结果 |
|---|---|---|
| 镜像重建 | `docker compose build backend frontend` | **成功** |
| 全栈启动 | `docker compose up -d` | mysql/backend/frontend **全部 healthy** |

---

## 4. 运行时功能验证（经 Nginx `http://127.0.0.1:8080` 实测）

```
GET  /api/v1/health/ready          → 200 ready
创建 部门/员工/区域→楼→层→房（容量2）→ 2 床   → 201
POST /checkin-applications         → 201 pending
POST .../approve                   → 200 approved
POST .../reserve {bed}             → 200 reserved
POST .../confirm                   → 200 checked_in
GET  /employees/{id}/accommodation → kind=accommodation, status=active
GET  /rooms/{id}/beds              → occupied=true, available=false
POST /transfers + reserve + complete → 200 completed
GET  /employees/{id}/history       → [('active', new_bed), ('ended', old_bed, 'transfer')]
POST /checkouts + inspection + complete → 200 completed
GET  /employees/{id}               → accommodation_status=not_in_dorm
GET  /rooms/{id}/beds              → available=true
并发 POST .../reserve 同一床位      → r1:409  r2:200（仅一笔成功）
```

---

## 5. 本次发现并修复的问题

| # | 问题 | 严重程度 | 修复 |
|---|---|---|---|
| 1 | 调宿/退宿互相独占导致无法构造竞态，且完成阶段缺少裁决 | 中 | 允许两单并存；complete 时检查对方未完结单；住宿被调宿后旧退宿完成返回 409 |
| 2 | 退宿在住宿已被结束后盲目幂等关闭，可能“调走后仍退宿” | 高 | 若员工已有新 active 住宿则拒绝完成 |
| 3 | `approve_application` 残留错误时间戳写法 | 低 | 统一 `utcnow()` |
| 4 | 停用床位未校验占用（M2 占位） | 中 | disable 拒绝 occupied/reserved |

---

## 6. 无法执行 / 受环境限制的检查

| 项目 | 原因 | 影响评估 |
|---|---|---|
| 浏览器 UI 人工点击走查 | 当前环境无法打开图形浏览器 | 已用 HTTP 实测全部业务 API 与前端构建产物；UI 交互细节留待 M6 |
| 前端 Vitest 组件测试 | M1/M2 遗留 | 登记遗留，不阻塞 M3 |
| 预留过期后台扫描 | 属 M4 | M3 预留支持 `expires_at` 字段，扫描任务 M4 实现 |
| 死锁自动重试压测 | 需多连接压测工具 | 事务锁顺序已统一；冲突路径返回 409 可安全重试 |

---

## 7. 遗留问题（不阻塞 M3）

1. **前端 Vitest 仍无用例**——与 M1/M2 遗留一致；建议 M5 后补组件测试。
2. **预留过期未自动释放**——`expires_at` 已建模，扫描任务属 M4。
3. **未建独立 `idempotency_keys` 表**——以状态机幂等 + 单表 `idempotency_key` UNIQUE 等效防重；若需跨接口统一幂等可在 M6 扩展。
4. **部门数据范围（dept_manager 只看本部门）**——M1/M2 已有权限码，住宿列表尚未按部门过滤下发；属 M5 报表/数据范围完善项。
5. **可视化分床 `/bed-allocation`**——属 M5；当前通过「入住管理-分床」对话框选择空闲床。
6. **Git 仓库**——当前工作区非 git 仓库，无法按阶段创建提交；如需版本管理请先 `git init`。

---

## 8. 验收结论

### **M3 验收：通过**

理由：
1. 入住申请→批准→预留→确认、调宿、退宿全链路有真实模型、迁移、Service、API 与 Vue 页面；
2. 自动化测试 **42/42 通过**（含 M1/M2 回归与 18 项 M3，其中 3 项并发），`ruff` 与 `vue-tsc` 零错误；
3. 迁移 `0003_m3_accommodation` 执行成功，生成列唯一索引与 CHECK 在并发测试中被实际触发（同床预留 409）；
4. Docker 三服务重建后 healthy，经 Nginx 实测完整入住→调宿→退宿及并发预留；
5. M2 床位占位状态已替换为真实业务记录推导；员工住宿查询返回真实数据；
6. 未提前引入 M4 待办/离职联动；发现的 4 个问题均已修复并回归通过；无阻塞缺陷。

### M4 开发准备情况：**就绪**

M4 可基于现有闭环继续：
- `employee_status_events` + 离职办理生成退宿待办（不自动释放床位）
- `workflow_todos` + 预留过期扫描 + 异常预警
- 复用 M3 的锁顺序与住宿/退宿服务

# M5 验收报告：可视化分床、Dashboard、台账报表与部门数据范围

> 验收日期：2026-10-13  
> 验收范围：`DMS_V1.0_MiMo_Development_Spec.md` §6.7 / §7 / §8 + `AGENTS.md` M5 + 用户 P0（部门数据隔离 / 可视化分床）  
> 验收方式：真实 MySQL 8.0 自动化测试 + Docker 重建 + Nginx HTTP 实测 + Playwright 浏览器 E2E  
> **验收结论：通过**

---

## 1. M5 功能交付清单

| 规格 / 用户要求 | 实现情况 | 结论 |
|---|---|---|
| 宿舍楼/楼层/房间/床位可视化 | `/bed-allocation` + `GET /floors/{id}/room-cards` + 既有 tree | 通过 |
| 图形化床位分配与入住操作 | 选员工 → 点空闲床 → 确认 → 应用/预留/确认入住 | 通过 |
| 管理首页 Dashboard 及核心指标 | `/dashboard/summary\|occupancy\|trends` + ECharts | 通过 |
| 员工住宿台账、空床、部门住宿 | `/reports/accommodations\|vacant-beds\|departments` | 通过 |
| 入住、退宿、调宿、异常报表 | `/reports/checkin-checkout\|transfers\|exceptions` | 通过 |
| 报表筛选、分页、Excel 导出 | 统一筛选参数 + `/reports/{type}/export` | 通过 |
| 角色权限与部门数据范围 | RBAC + `data_scope`（P0 强制后端过滤） | 通过 |
| 前端组件测试及 E2E | Vitest 4 + Playwright 3 | 通过 |

**P0 强制：部门数据隔离、可视化分床与数据一致性 — 全部通过（见 §2 / §3）。**

---

## 2. 部门数据隔离 P0 测试结果

实现：`sys_user_departments`（迁移 `0005_m5_reports_scope`）+ `app/services/data_scope.py`。  
范围规则：`super_admin`/`hr` 全量；其他角色 = 显式授权部门 ∪ 管理部门（`manager_employee_id`）及下级；空范围默认拒绝。

| P0 要求 | 测试 | 结果 |
|---|---|---|
| 部门负责人只能查授权部门员工及住宿 | `test_p0_dept_manager_scope_isolation` | **通过** |
| 直接访问其他部门详情/住宿历史拒绝 | 同上（403） | **通过** |
| 修改查询参数不得绕过 | `test_p0_dept_manager_cannot_modify_query_to_see_others` + 同上 department_id 过滤 | **通过** |
| Excel 导出遵循数据范围 | 同上（employee export 仅含本部门） | **通过** |
| 待办/预警/统计不泄露其他部门 | `test_p0_scope_blocks_todos_alerts_stats_leak` | **通过** |
| 超管可访问全部部门 | 同上 admin 对照 | **通过** |
| 管理部门自动纳入范围 | `test_p0_manager_of_department_via_manager_employee_id` | **通过** |

覆盖接口：`/employees`（列表/详情/历史/export）、`/accommodations/active`、`/workflow/todos`、`/workflow/alerts`、`/dashboard/summary`、`/reports/*` 与导出。  
**所有过滤与 403 均在后端 Service/查询层强制，不依赖前端隐藏。**

---

## 3. 可视化分床 P0 测试结果

| P0 场景 | 测试 | 结果 |
|---|---|---|
| 1. 空闲/预留/入住/维修/停用正确显示 | `test_p0_room_cards_show_all_bed_states` + Vitest 文案标签 | **通过** |
| 2. 点击空闲床位进入分配流程 | `test_p0_allocate_free_bed_via_flow` + E2E 页面 | **通过** |
| 3. 分配成功后刷新占用状态 | 同上（再次 room-cards `available=false`） | **通过** |
| 4. 两人同选一床仅一笔成功 | `test_p0_concurrent_same_bed_only_one_success`（asyncio gather，200+409） | **通过** |
| 5. 冲突明确提示并刷新 | 前端捕获 409 文案「已被其他管理员分配」+ 刷新 | **通过**（E2E 覆盖入口；冲突文案单测/代码审查） |
| 6. 已入住/预留/停用不可错误分配 | `test_p0_cannot_allocate_taken_or_disabled_bed` | **通过** |
| 7. 页面空床数与后端一致 | `test_p0_vacant_count_matches_db` | **通过** |

后端集成测试 **5/5 通过**；另有 M3 既有并发预留测试继续通过。

---

## 4. 报表统计与导出一致性

| 检查项 | 测试 | 结果 |
|---|---|---|
| 台账与有效住宿记录一致 | `test_accommodation_ledger_matches_active_records` | **通过** |
| 已离职未退宿仍计当前住宿 | 同上（terminate 后仍 1 条台账，summary ≥1） | **通过** |
| 预留床不计入真正空闲 | `test_reserved_bed_not_counted_as_vacant` | **通过** |
| 维修/停用不计入可分配 | `test_maintenance_and_disabled_beds_not_allocatable` | **通过** |
| 调宿/退宿历史完整 | `test_reports_export_and_transfer_history` / `test_checkin_checkout_report_contains_events` | **通过** |
| 导出与权限/筛选一致 | P0 导出用例 + 6 类 export 均返回 xlsx | **通过** |
| 统计口径统一后端 | `report_service` / `dashboard_service` 唯一来源 | **通过** |

---

## 5. 前端组件测试及浏览器 E2E

### Vitest（`npm test`）

| 用例 | 覆盖 | 结果 |
|---|---|---|
| `auth.spec.ts` | 权限码判定 | **通过** |
| `bed-status.spec.ts` | 五态文案标签 + 分床页渲染 | **通过**（2） |
| `reports.spec.ts` | 六报表 Tab + 导出按钮 | **通过** |
| **合计** | | **4 passed** |

### Playwright E2E（`npm run e2e`，Chrome，`http://127.0.0.1:8080`）

| 用例 | 覆盖 | 结果 |
|---|---|---|
| dashboard shows KPI cards | 登录 + 首页指标 | **通过** |
| bed allocation page shows room cards | 可视化分床导航 | **通过** |
| reports page lists six tabs and export | 报表页 | **通过** |
| **合计** | | **3 passed** |

---

## 6. M1～M5 全量回归测试结果

| 范围 | 命令 | 结果 |
|---|---|---|
| 后端 M1～M5（含并发） | `cd backend && python -m pytest -q` | **75 passed** |
| 前端类型检查 | `npm run typecheck` | **0 error** |
| 前端构建 | `npm run build` | **成功** |
| 前端 Vitest | `npm test` | **4 passed** |
| Playwright E2E | `npx playwright test` | **3 passed** |

后端 75 = M4 时 60 + M5 新增 15（数据隔离 4 + 报表 6 + 分床 5）。

---

## 7. 数据库迁移及 Docker 验证

### 迁移

| 项目 | 命令 | 结果 |
|---|---|---|
| 迁移前 | `alembic current` | `0004_m4_workflow` |
| 执行 | `alembic upgrade head` | **成功** → `0005_m5_reports_scope` |
| 表 | `sys_user_departments`（UNIQUE user+department，CASCADE） | **已创建** |

未改动 M1～M4 既有表结构。

### Docker Compose

```
docker compose build backend   → 成功
docker compose build frontend  → 成功
docker compose up -d           → mysql / backend / frontend 全部 healthy
```

Nginx `http://127.0.0.1:8080` 实测：

```
POST /api/v1/auth/login                     → token
GET  /api/v1/dashboard/summary              → 200（含 vacant/occupied/rate）
GET  /api/v1/reports/accommodations         → 200
GET  /api/v1/reports/vacant-beds            → 200
GET  /api/v1/reports/departments            → 200
GET  /api/v1/reports/{6 类}/export          → 200 xlsx
GET  /api/v1/floors/{id}/room-cards         → 200（含 occupied/reserved/available）
```

---

## 8. 问题修复和遗留风险

| # | 问题 | 严重程度 | 处理 |
|---|---|---|---|
| 1 | `SysUserDepartment` 从错误模块导入导致 ImportError | 高 | 改为 `app.models.data_scope`，全量测试恢复 |
| 2 | `dept_manager`/`finance_viewer` 缺少 `report:export`，P0 导出 403 | 中 | 按规格 §8 矩阵补权限（D-035） |
| 3 | 报表服务 Transfer 字段名误用 old/new_bed_id | 中 | 改为 `source_bed_id`/`target_bed_id` |
| 4 | Vacant 查询构造中间态破损 | 中 | 重写 `report_vacant_beds` |
| 5 | Playwright 登录按钮文案「登 录」选择器不匹配 | 低 | 改为 `/登\s*录/`，E2E 通过 |

### 遗留风险

1. **Playwright 浏览器**：使用系统 Chrome channel（`channel: 'chrome'`）；未下载独立 Chromium（安装超时）。CI 可改用 `npx playwright install chromium`。
2. **部门数据范围 UI**：后端 `PUT /users/{id}/departments` 已可用；设置页暂未提供授权部门编辑器（可用 API/种子数据配置）。
3. **Dashboard 全局床位指标**：床位总量/占用为全局资源数（空床为真正可分配）；`housed_employees` 已按范围过滤。
4. **预警阈值可配置**：仍为固定扫描策略（M4 遗留），不影响 M5 P0。

---

## 9. M6 上线准备情况

| 项 | 状态 |
|---|---|
| Docker Compose 三服务构建/启动 | 已验证 |
| Alembic 迁移可重复 `upgrade head` | 已验证至 `0005` |
| 全量自动化测试 | 后端 75 + Vitest 4 + E2E 3 |
| 报表导出脱敏/公式注入防护 | 复用 `_safe_excel_value` |
| 生产备份/恢复演练 | **未做**（属 M6） |
| 历史 Excel 台账迁移演练 | **未做**（属 M6） |
| HTTPS/密钥轮换/多实例任务 | **未做**（属 M6，不提前） |

---

## 10. 已修改 / 新增文件摘要

### 后端

- 迁移：`alembic/versions/0005_m5_reports_scope.py`
- 模型：`app/models/data_scope.py`
- 服务：`app/services/data_scope.py`、`report_service.py`、`dashboard_service.py`；`employee/workflow/checkin/checkout/transfer/user` 增加 scope
- API：`endpoints/dashboard.py`、`reports.py`；`dormitories.py` room-cards；`users.py` departments；`router.py` 注册
- 权限：`permissions.py`（dept_manager/finance_viewer 导出）
- 测试：`test_m5_data_scope_p0.py`、`test_m5_reports.py`、`test_m5_allocation_p0.py`

### 前端

- 页面：`views/allocation/BedAllocationView.vue`、`views/reports/ReportsView.vue`、`views/dashboard/DashboardView.vue`
- API/类型：`api/reports.ts`、`dormitories.ts` room-cards、`types/index.ts` M5 类型
- 路由/导航：`/bed-allocation`，Reports 挂真实页面
- 测试：`vitest.config.ts`、`src/**/**.spec.ts`、`playwright.config.ts`、`e2e/m5.spec.ts`

### 文档

- `docs/IMPLEMENTATION_PLAN.md`、`docs/DECISIONS.md`（D-033～D-035）、本报告

---

## 11. 验收结论

### **M5 验收：通过**

理由：

1. **部门数据隔离 P0 全部通过**：授权范围过滤、详情 403、参数绕不过、导出一致、待办/预警/统计不泄露、超管全量；
2. **可视化分床 P0 全部通过**：五态展示、空床分配、并发同床仅一笔成功、占用/预留/停用拒绝分配、空床数与库一致；
3. **报表口径**与有效住宿/预留/维修/离职未退宿规则一致，导出与权限/筛选一致；
4. M1～M5 全量回归 **75 passed**，`vue-tsc` 零错误，Vitest **4**、Playwright **3** 全部通过；
5. Alembic `0005` 迁移成功，Docker 三服务 healthy，Nginx 实测 Dashboard/报表/导出/room-cards 均 200；
6. 过程中 5 个问题均已修复并回归。

**最终结论：M5 通过，可进入 M6。**

# M2 验收报告：基础数据（部门 / 员工 / Excel / 宿舍资源）

> 验收日期：2026-10-13  
> 验收范围：`DMS_V1.0_MiMo_Development_Spec.md` 第 16 节 M2 里程碑 + `AGENTS.md` M2 专项执行顺序  
> 验收方式：实际执行迁移、自动化测试、Docker 重建与运行时 HTTP 接口验证（非仅代码审阅）  
> **验收结论：通过**

---

## 1. M2 开发目标对照

| 规格 / AGENTS.md 要求 | 实现情况 | 结论 |
|---|---|---|
| 部门数据模型、接口、权限和前端页面 | `departments` 表 + `/api/v1/departments` CRUD/树 + 员工页内「部门管理」 | 通过 |
| 员工档案及员工详情，工号唯一性校验 | `employees` 表 + `UNIQUE(employee_no)` + CRUD/详情 | 通过 |
| Excel 模板、预览、校验、提交、错误报告及导出 | 两阶段导入 + `import_jobs` + 模板/导出 xlsx | 通过 |
| 区域→楼栋→楼层→房间→床位基础数据及状态管理 | 5 张层级表 + CRUD + 树 + 床位启停/维修 | 通过 |
| 复用 M1 认证、RBAC（27 权限码）、迁移、审计 | 未新增权限码；全部接口挂既有权限；审计写入 | 通过 |
| 不提前实现 M3 业务 | 未建 `accommodation_*` / `bed_reservations` 等表 | 通过 |
| 唯一约束与外键生效 | `uq_employees_employee_no`、`uq_departments_code`、层级 `uq_*`、`CHECK(capacity>0)` | 通过 |
| 停用禁止新分配 | 上级区域/楼栋/楼层停用时拒绝新建下级资源 | 通过 |
| 空床状态不虚构 M3 数据 | 床位 `occupied/reserved` 固定为空/False，`available` 仅由 `operational_status` 推导 | 通过 |

---

## 2. 本次交付范围

### 2.1 数据库（Alembic `0002_m2_master_data`）

新增表：

| 表名 | 关键约束 |
|---|---|
| `departments` | `UNIQUE(department_code)`，自引用 `parent_id` |
| `employees` | `UNIQUE(employee_no)`，`FK department_id` |
| `dorm_areas` | `UNIQUE(area_code)` |
| `dorm_buildings` | `UNIQUE(area_id, building_code)` |
| `dorm_floors` | `UNIQUE(building_id, floor_no)` |
| `dorm_rooms` | `UNIQUE(floor_id, room_no)`，`CHECK(capacity > 0)` |
| `dorm_beds` | `UNIQUE(room_id, bed_no)` |
| `import_jobs` | 导入批次追踪，`detail` 存预览快照/错误（MySQL MEDIUMTEXT） |

**未创建**（M3/M4）：`accommodation_applications`、`bed_reservations`、`accommodation_records`、`transfer_records`、`checkout_records`、`employee_status_events`、`workflow_todos`、`idempotency_keys`。

### 2.2 后端 API（前缀 `/api/v1`）

**部门**
- `GET /departments`（分页/关键字/状态/parent_id）
- `GET /departments/tree`
- `GET /departments/{id}`
- `POST /departments`（`employee:create`）
- `PATCH /departments/{id}`（`employee:update`）

**员工与 Excel**
- `GET/POST /employees`，`GET/PATCH /employees/{id}`
- `GET /employees/{id}/accommodation`、`GET /employees/{id}/history`（M2 返回空）
- `GET /employees/import/template`
- `POST /employees/import/preview`、`POST /employees/import/commit`
- `GET /employees/export`
- `GET /imports/{id}`、`GET /imports/{id}/errors`

**宿舍资源**
- `GET/POST /dorm-areas`，`PATCH /dorm-areas/{id}`
- `GET/POST /buildings`，`PATCH /buildings/{id}`，`GET /buildings/{id}/floors`，`GET /buildings/{id}/occupancy`
- `POST /floors`，`PATCH /floors/{id}`
- `GET/POST /rooms`，`GET/PATCH /rooms/{id}`
- `GET/POST /rooms/{id}/beds`，`PATCH /beds/{id}`
- `POST /beds/{id}/disable|enable|maintenance`
- `GET /beds/available`，`GET /dormitories/tree`

### 2.3 权限映射（复用 27 既有权限码，见 D-021）

| 操作 | 权限码 |
|---|---|
| 部门/员工查询 | `employee:view` |
| 部门/员工创建 | `employee:create` |
| 部门/员工更新 | `employee:update` |
| Excel 导入 | `employee:import` |
| Excel 导出 | `employee:export` |
| 宿舍查询 | `dorm:view` |
| 宿舍创建 | `dorm:create` |
| 宿舍更新 | `dorm:update` |
| 床位启停 | `bed:manage` |

### 2.4 前端

| 页面 | 说明 |
|---|---|
| `/employees` `EmployeesView.vue` | 员工列表筛选、新建/编辑、部门管理弹窗、Excel 导入两阶段、导出 |
| `/dormitories` `DormitoriesView.vue` | 层级树、区域/楼栋/楼层/房间维护、房间表、床位管理与启停 |

类型与 API Client：`types/index.ts`、`api/departments.ts`、`api/employees.ts`、`api/dormitories.ts`。

---

## 3. 测试项目、执行命令与结果

### 3.1 后端静态检查

| 项目 | 命令 | 结果 |
|---|---|---|
| 代码风格 | `ruff check app tests` | **All checks passed** |

### 3.2 后端自动化测试（真实 MySQL 8.0）

| 项目 | 命令 | 结果 |
|---|---|---|
| 全量（M1 回归 + M2） | `pytest -q` | **24 passed** |

用例明细：

| 用例 | 结果 |
|---|---|
| M1 全部 16 项（health/security/auth/users） | PASSED |
| `test_department_crud_and_tree` | PASSED |
| `test_department_not_found` | PASSED |
| `test_employee_crud_and_unique_no` | PASSED |
| `test_employee_date_validation` | PASSED |
| `test_employee_import_template_and_two_phase` | PASSED |
| `test_employee_export` | PASSED |
| `test_dorm_hierarchy_crud` | PASSED |
| `test_disabled_parent_blocks_new_children` | PASSED |

覆盖的关键路径：
- 重复部门编码 → 409
- 部门父子环 → 400/422
- 存在活动子部门时禁用父部门 → 拒绝
- 重复工号 → 409
- 入职/离职日期倒置 → 400/422
- Excel 空工号 / 未知部门 / 坏日期 → 预览报错
- 导入 preview 不写正式表，commit 后才落库
- 重复 commit 导入批次 → 409
- 楼内重复楼栋/楼层/房间编号 → 409
- capacity=0 → 422；容量小于已有床位数 → 422
- 床位超过容量新增 → 422
- 禁用区域后新建楼栋 → 拒绝
- 床位 disable/maintenance/enable 状态与 `available` 推导

### 3.3 前端

| 项目 | 命令 | 结果 |
|---|---|---|
| TypeScript 严格检查 | `npm run typecheck` | **通过（0 error）** |
| 生产构建 | `npm run build` | **成功**（含 EmployeesView / DormitoriesView） |

### 3.4 数据库迁移

| 项目 | 命令 | 结果 |
|---|---|---|
| 迁移前版本 | `alembic current` | `0001_initial_auth` |
| 执行迁移 | `alembic upgrade head` | **成功** → `0002_m2_master_data` |
| 新表核对 | `SHOW TABLES` | 新增 8 张 M2 表 |

### 3.5 Docker Compose

| 项目 | 命令 | 结果 |
|---|---|---|
| 镜像重建 | `docker compose build backend frontend` | **成功** |
| 全栈启动 | `docker compose up -d` | mysql/backend/frontend **全部 healthy** |

---

## 4. 运行时功能验证（经 Nginx `http://127.0.0.1:8080` 实测）

### 4.1 健康与认证

```
GET  /health              → 200 {"status":"ok",...}
GET  /api/v1/health/ready → 200 {"status":"ready","database":"ok"}
POST /api/v1/auth/login   → 200 admin / 27 权限
```

### 4.2 部门 / 员工

| 场景 | 结果 |
|---|---|
| 创建部门 | 201 |
| 创建员工（关联部门） | 201，返回 `department_code/name` |
| 重复 `employee_no` | **409** `conflict` |
| 员工列表 / 详情 | 200 |

### 4.3 宿舍资源

| 场景 | 结果 |
|---|---|
| 区域→楼栋→楼层→房间（容量 4，自动生成 4 床） | 201 |
| 床位列表 `B1..B4` | 200 |
| 停用床位 | `operational_status=disabled`，`available=false` |
| 启用床位 | `active`，`available=true` |
| `GET /dormitories/tree` | 200，返回层级树 |

### 4.4 Excel

| 场景 | 结果 |
|---|---|
| 下载模板 | 200，`PK` xlsx |
| 预览（1 新增 + 1 空工号错误） | 200，`create=1 error=1`，**未写正式表** |
| 提交 | `completed_with_errors`，`created=1 failed=1` |
| 错误清单 | 返回 `employee_no is required` |
| 重复提交同一批次 | **409** |
| 导出 | 200，xlsx |

### 4.5 权限门禁（实测）

| 主体 | 操作 | 结果 |
|---|---|---|
| `finance_viewer` | `GET /employees` | 200（有 `employee:view`） |
| `finance_viewer` | `POST /employees` | **403** `permission_denied: employee:create` |
| `finance_viewer` | `POST /dorm-areas` | **403** |

---

## 5. 本次发现并修复的问题

| # | 问题 | 严重程度 | 修复 |
|---|---|---|---|
| 1 | 审计 `after_data` 含 `datetime` 导致 JSON 序列化失败 | 高 | `audit_service._jsonable` 递归转 ISO 字符串 |
| 2 | 部门自引用环检测逻辑冗余且易错 | 中 | 简化为沿 `parent_id` 链上溯 + visited 集合 |
| 3 | `import_jobs.detail` 在大批量下可能超 TEXT 64KB | 中 | MySQL 使用 `MEDIUMTEXT` |
| 4 | Excel 循环内闭包捕获循环变量（ruff B023） | 低 | 默认参数绑定 `row_values` |
| 5 | 前端部门弹窗误留占位 dialog | 低 | 拆为 `deptListVisible` / `deptFormVisible` |

---

## 6. 无法执行 / 受环境限制的检查

| 项目 | 原因 | 影响评估 |
|---|---|---|
| 浏览器 UI 人工点击走查 | 当前环境无法打开图形浏览器 | 已用 HTTP 实测全部 API 与前端构建产物；UI 交互细节留待 M6 |
| 前端 Vitest 组件测试 | M1 遗留，M2 页面以 typecheck+build 为准 | 登记遗留，不阻塞 M2 |
| 并发占床 / 预留冲突 | 属 M3 业务表 | 不在 M2 范围 |
| 上传超大文件压测 | 属 M6 非功能验收 | 已限制 5MB / 2000 行 |

---

## 7. 遗留问题（不阻塞 M2）

1. **前端 `npm run test`（Vitest）仍无用例**——与 M1 遗留一致；建议 M5 页面稳定后补组件测试。
2. **`/employees/{id}/accommodation|history` 为空实现**——等待 M3 `accommodation_records` 落地后填充。
3. **床位 `occupied/reserved` 恒为 False**——M3 引入关联表后改为按 `active` 记录推导。
4. **员工离职办理未生成待办**——M2 仅支持 `employment_status` 字段变更；`/employees/{id}/offboarding|terminate` 与 `workflow_todos` 属 M4。
5. **部门无独立权限码**——按 D-021 复用 `employee:*`；若后续需要更细粒度，须同步 seed 与前端。
6. **导入快照存于 `import_jobs.detail` JSON**——V1.0 够用；若单批次远超数千行，可改为对象存储 + 明细表。

---

## 8. 验收结论

### **M2 验收：通过**

理由：
1. 部门 / 员工 / Excel / 宿舍层级全部有真实模型、迁移、API、服务与 Vue 页面；
2. 自动化测试 **24/24 通过**（含 M1 全量回归），`ruff` 与 `vue-tsc` 零错误；
3. 迁移 `0002_m2_master_data` 执行成功，唯一约束与外键在测试中被实际触发（409）；
4. Docker 三服务重建后 healthy，经 Nginx 实测 CRUD、床位状态、Excel 两阶段、权限 403；
5. 未提前引入 M3 住宿业务表，空床/住宿状态展示诚实；
6. 发现的 5 个问题均已修复并回归通过；无阻塞缺陷。

### M3 开发准备情况：**就绪**

M3 可基于现有骨架继续：
- `accommodation_applications` / `bed_reservations` / `accommodation_records` + 生成列唯一索引
- 入住申请状态机、预留、确认入住、调宿、退宿
- Service 层统一锁顺序与幂等
- 并发占床集成测试

# 公司宿舍入住管理系统（DMS）V1.0 开发规格说明书

> 文档版本：V1.0  | 适用对象：小米 MiMo Code / 软件开发人员  
> 系统定位：企业内部行政、人事办理员工入职住宿、在住调整及离职退宿的 Web 管理平台。  
> 交付目标：可在 Docker Compose 环境部署、具备真实数据库与自动化测试的可运行软件，禁止仅交付 UI Demo。

## 0. 给 MiMo Code 的执行指令

请以本文作为项目的**唯一初始开发基线**，从零实现完整项目，技术栈统一为 Vue 3 + TypeScript + Vite + Element Plus + Pinia、Python FastAPI + Pydantic v2 + SQLAlchemy 2.x（async）+ Alembic、MySQL 8.0、Docker Compose。

开发规则：

1. 首先阅读全文，建立 `docs/IMPLEMENTATION_PLAN.md`，按本文第 16 节的里程碑逐阶段实现；不要一次性生成无法验证的大量伪代码。
2. 所有代码必须保存为实际项目文件；不允许只输出代码片段、伪代码、空实现或假数据演示来替代真实功能。
3. 每完成一个里程碑，运行格式检查、类型检查、数据库迁移和相关测试，修复错误，再进入下个里程碑。
4. 使用真实 MySQL 数据库存储业务数据；任何修改入住、预留、调宿、退宿的操作都必须以事务执行。
5. 数据模型、API Schema、权限码、前端类型必须保持一致。接口变更时同步文档、测试及前端调用。
6. 不得在源码中写死密码、令牌和数据库连接凭据；使用 `.env.example` 演示配置。
7. 优先完成基础架构和核心业务闭环，再完善可视化页面及报表；避免添加第一版范围以外的收费、资产、维修等模块。
8. 每阶段完成后汇报：已实现文件、已实现功能、测试结果、剩余任务及阻塞原因。
9. 保留数据库迁移记录、审计日志和业务历史，禁止直接覆盖已完成入住历史。
10. 如规范存在不明确处，采用本文件中的业务约束，并在 `docs/DECISIONS.md` 记录具体取舍，不要擅自扩大需求。

---

## 1. 项目目标与范围

### 1.1 项目背景

公司行政、人事需要在员工入职时安排宿舍，离职时办理退宿。目前若依赖 Excel 管理，容易发生重复分床、房间实际人数不清、离职人员占床未清理、调宿历史遗失、统计口径不一致等问题。

### 1.2 V1.0 必须实现

| 模块 | 交付要求 | 优先级 |
|---|---|---|
| 员工档案 | 增删改查（有历史关联时禁止物理删除）、Excel 模板、预览、校验、批量导入、导出 | P0 |
| 宿舍资源 | 区域、宿舍楼、楼层、房间、床位层级管理，状态与容量校验 | P0 |
| 入住管理 | 申请、批准、预留、确认入住、取消、入住历史 | P0 |
| 调宿管理 | 申请、目标床位预留、搬迁确认、原床释放、历史保留 | P0 |
| 退宿管理 | 发起、检查、确认、床位释放、历史保留 | P0 |
| 离职联动 | 离职办理触发退宿待办、异常预警，不直接释放床位 | P0 |
| 住宿台账/报表 | 当前住宿、空床、部门住宿、入退宿明细、调宿明细、异常报表和 Excel 导出 | P0 |
| 可视化分配 | 楼栋/楼层导航、房间卡片、床位状态、分床交互、并发冲突提示 | P1（V1 必交） |
| 权限与审计 | 用户、角色、权限、数据范围、关键操作日志 | P0 |

**不在 V1.0 范围：** 住宿费、水电费、押金、薪酬代扣、资产领用、维修工单、宿舍巡检、员工自助小程序、企业微信消息推送及外部 HR/ERP 对接。保留可扩展架构即可。

### 1.3 使用角色

超级管理员、人事专员、行政宿管、财务只读用户、部门负责人。一个用户允许拥有多个角色。

---

## 2. 架构与技术栈

| 层 | 技术 | 说明 |
|---|---|---|
| 前端 | Vue 3 / TypeScript / Vite | Composition API、严格类型检查 |
| UI | Element Plus / ECharts | 后台组件与统计图 |
| 状态管理 | Pinia / Vue Router | 用户会话、权限及页面路由 |
| HTTP | Axios | 统一 API Client、异常处理 |
| 后端 | Python FastAPI | REST API、OpenAPI 文档 |
| 校验 | Pydantic v2 | 请求/响应数据 Schema |
| ORM | SQLAlchemy 2.x AsyncSession | 异步数据库访问 |
| MySQL 驱动 | asyncmy | 与异步 ORM 一致 |
| 迁移 | Alembic | 正式迁移，不以 create_all 替代 |
| 数据库 | MySQL 8.0 / InnoDB / utf8mb4 | 权威业务数据源 |
| Excel | openpyxl | 模板生成、导入校验、导出 |
| 部署 | Docker Compose、Nginx | 统一入口，私有化运行 |
| 测试 | pytest、httpx、Vitest | 单元、接口及并发测试 |
| Redis | 可选 | 首版不作核心业务状态的唯一依据 |

采用**模块化单体**：Vue 管理后台 → Nginx → FastAPI API 层 → Service 业务层 → Repository 数据层 → MySQL。权限与状态变更逻辑在后端执行，不由前端决定。

---

## 3. 项目目录结构

```text
dormitory-management-system/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── core/
│   │   │   ├── config.py
│   │   │   ├── database.py
│   │   │   ├── security.py
│   │   │   ├── permissions.py
│   │   │   ├── exceptions.py
│   │   │   └── logging.py
│   │   ├── api/
│   │   │   ├── deps.py
│   │   │   └── v1/
│   │   │       ├── router.py
│   │   │       └── endpoints/
│   │   │           ├── auth.py
│   │   │           ├── users.py
│   │   │           ├── employees.py
│   │   │           ├── dormitories.py
│   │   │           ├── beds.py
│   │   │           ├── checkins.py
│   │   │           ├── transfers.py
│   │   │           ├── checkouts.py
│   │   │           ├── todos.py
│   │   │           ├── dashboard.py
│   │   │           └── reports.py
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── repositories/
│   │   ├── services/
│   │   ├── tasks/
│   │   └── utils/
│   ├── tests/
│   ├── alembic/versions/
│   ├── alembic.ini
│   ├── pyproject.toml
│   ├── Dockerfile
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── api/
│   │   ├── assets/
│   │   ├── components/{common,dormitory,employee}/
│   │   ├── composables/
│   │   ├── layouts/
│   │   ├── router/
│   │   ├── stores/
│   │   ├── types/
│   │   ├── utils/
│   │   └── views/{login,dashboard,employees,dormitories,checkins,transfers,checkouts,todos,reports,settings}/
│   ├── public/
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   └── Dockerfile
├── deploy/
│   └── nginx/default.conf
├── docs/
│   ├── TECHNICAL_DESIGN.md
│   ├── DATABASE_DESIGN.md
│   ├── API_SPECIFICATION.md
│   ├── PERMISSIONS.md
│   ├── DEPLOYMENT.md
│   ├── IMPLEMENTATION_PLAN.md
│   └── DECISIONS.md
├── scripts/{backup.sh,restore.sh}
├── compose.yaml
├── .env.example
├── .gitignore
└── README.md
```

API 只负责参数处理、鉴权和返回；Service 负责事务、状态机与业务规则；Repository 负责查询、行锁及持久化；Schema 负责数据验证。所有关键业务操作写入审计日志。

---

## 4. 核心业务规则与状态机

### 4.1 强制业务约束

- **BR-001**：员工工号全局唯一；员工不可因同名而合并。
- **BR-002**：同一床位同一时刻最多一名有效入住员工。
- **BR-003**：同一员工同一时刻最多一条有效住宿记录。
- **BR-004**：同一床位、同一员工最多一条有效预留。
- **BR-005**：被预留床位不得被其他入住流程占用，已正式入住床位不可再次预留。
- **BR-006**：员工离职只生成退宿待办，不自动释放床位。
- **BR-007**：调宿必须在同一事务内结束旧住宿并创建新住宿记录。
- **BR-008**：已发生业务的住宿记录禁止物理删除，改为结束、撤销或冲正并留下审计。
- **BR-009**：房间、楼层、宿舍楼、床位停用后禁止新增分配；在住人员不自动消失。
- **BR-010**：所有入住、预留、调宿、退宿必须在事务内对床位、员工重新校验。
- **BR-011**：前端的房间人数、空床数量仅用于展示，后端始终负责最终校验。
- **BR-012**：员工人事状态和住宿状态分开管理，住宿状态从有效住宿和预留推导。

### 4.2 状态机

**员工任职：** `pending` 待入职 → `active` 在职 → `offboarding` 离职办理中 → `terminated` 已离职；如需撤回离职，单独记录逆向变更事件。

**入住申请：** `pending` → `approved` → `reserved` → `checked_in`；可按规则进入 `rejected`、`cancelled`、`expired`。

**床位预留：** `active` → `consumed` / `cancelled` / `expired`。

**住宿记录：** `active` → `ended`（正常退宿/调宿）；错误业务采用受控 `voided` 处理，不物理删除。

**调宿：** `pending` → `reserved` → `completed`；完成前可 `cancelled`。

**退宿：** `pending` → `inspection` → `completed`；完成前可 `cancelled`。

**待办：** `pending` → `completed` / `cancelled`，业务未完成不能仅凭“已读”关闭。

### 4.3 场景 A：新员工入职住宿

人事创建员工 → 选择“需要住宿” → 行政创建/批准入住申请 → 查看可用床位 → 预留床位 → 员工到达后确认入住 → 生成住宿记录 → 消耗预留 → 更新展示和待办。

### 4.4 场景 B：在职调宿

创建调宿申请 → 检查当前有效住宿 → 预留目标床位 → 实际搬迁确认 → 同一事务内结束旧住宿/创建新住宿/消耗预留 → 保留旧住宿完整历史。

### 4.5 场景 C：员工离职退宿

人事设置离职办理中 → 状态事件幂等处理 → 有在住记录则生成退宿单与行政待办 → 行政检查钥匙/门禁卡/房间物品 → 确认实际退宿 → 结束住宿并释放空床 → 关闭待办。员工即使已标记 `terminated` 但仍在住，系统仍保留占用并发出异常预警。

---

## 5. MySQL 数据库设计

数据库：`dms`；引擎：InnoDB；字符集：utf8mb4。主键建议 `BIGINT UNSIGNED`；`created_at`、`updated_at` 为 `DATETIME(6)`，时间在应用层统一使用 UTC 语义。业务操作表增加 `created_by`、`updated_by`；敏感信息最小化存储。

### 5.1 表清单及字段

| 表名 | 核心字段（省略通用审计时间字段） | 关键约束 |
|---|---|---|
| `sys_users` | id, username, password_hash, display_name, employee_id, status, last_login_at | UNIQUE(username) |
| `sys_roles` | id, code, name, description, status | UNIQUE(code) |
| `sys_permissions` | id, code, name, module, description | UNIQUE(code) |
| `sys_user_roles` | user_id, role_id | UNIQUE(user_id, role_id)，外键 |
| `sys_role_permissions` | role_id, permission_id | UNIQUE(role_id, permission_id)，外键 |
| `departments` | id, department_code, department_name, parent_id, manager_employee_id, status | UNIQUE(department_code)，禁止部门层级循环 |
| `employees` | id, employee_no, full_name, gender, department_id, position, employment_type, phone, join_date, termination_date, employment_status, accommodation_required, shift_type, notes | UNIQUE(employee_no)，部门外键 |
| `dorm_areas` | id, area_code, area_name, address, status, description | UNIQUE(area_code) |
| `dorm_buildings` | id, area_id, building_code, building_name, total_floors, gender_policy, manager_user_id, status, description | UNIQUE(area_id, building_code) |
| `dorm_floors` | id, building_id, floor_no, floor_name, gender_policy, status | UNIQUE(building_id, floor_no) |
| `dorm_rooms` | id, floor_id, room_no, room_type, capacity, gender_policy, status, description | UNIQUE(floor_id, room_no)，CHECK(capacity > 0) |
| `dorm_beds` | id, room_id, bed_no, operational_status, version, description | UNIQUE(room_id, bed_no) |
| `accommodation_applications` | id, application_no, employee_id, application_type, requested_checkin_date, assigned_bed_id, status, reason, notes, submitted_by, processed_by, processed_at | UNIQUE(application_no) |
| `bed_reservations` | id, reservation_no, application_id, employee_id, bed_id, status, reserved_at, expires_at, released_at, release_reason, created_by | UNIQUE(reservation_no)，active 唯一约束 |
| `accommodation_records` | id, employee_id, bed_id, application_id, checkin_at, checkout_at, status, end_reason, created_by, ended_by, notes | active 员工/床位唯一，日期校验 |
| `transfer_records` | id, transfer_no, employee_id, source_accommodation_id, source_bed_id, target_bed_id, target_reservation_id, target_accommodation_id, reason, status, requested_at, completed_at, cancelled_at, processed_by, notes | UNIQUE(transfer_no)，源/目标不同 |
| `checkout_records` | id, checkout_no, employee_id, accommodation_id, checkout_type, reason, status, expected_checkout_date, actual_checkout_at, key_returned, access_card_returned, belongings_cleared, room_inspected, inspection_notes, processed_by, completed_at | UNIQUE(checkout_no)，未完结单据防重复 |
| `employee_status_events` | id, employee_id, from_status, to_status, effective_at, source, source_event_id, processed_at, created_by | UNIQUE(source, source_event_id)（可空来源 ID 需额外处理） |
| `workflow_todos` | id, todo_type, business_type, business_id, assignee_role, assignee_user_id, status, priority, due_at, completed_at | 同业务待办不得重复待处理 |
| `import_jobs` | id, import_type, filename, file_hash, status, total_rows, success_rows, failed_rows, result_file_path, created_by, completed_at | 导入批次可追踪 |
| `audit_logs` | id, actor_user_id, action, resource_type, resource_id, request_id, before_data, after_data, ip_address, occurred_at | 仅追加，敏感字段脱敏 |
| `idempotency_keys` | id, actor_user_id, key_value, request_fingerprint, status, response_code, response_body, expires_at | UNIQUE(actor_user_id, key_value) |

### 5.2 数据关系

区域 1:N 宿舍楼；宿舍楼 1:N 楼层；楼层 1:N 房间；房间 1:N 床位。部门 1:N 员工；员工 1:N 历史住宿记录；一个 `active` 住宿记录对应一个员工和一个床位。调宿记录引用原、新住宿记录，退宿记录关联被结束的住宿记录。对被业务引用的主数据仅允许停用/归档，不允许直接删除。

### 5.3 真正有效的唯一性约束

MySQL 8.0 可通过生成列 + UNIQUE 模拟仅对 `status = 'active'` 生效的唯一索引：

```sql
ALTER TABLE accommodation_records
ADD COLUMN active_employee_id BIGINT UNSIGNED
    GENERATED ALWAYS AS (
      CASE WHEN status = 'active' THEN employee_id ELSE NULL END
    ) STORED,
ADD COLUMN active_bed_id BIGINT UNSIGNED
    GENERATED ALWAYS AS (
      CASE WHEN status = 'active' THEN bed_id ELSE NULL END
    ) STORED;

CREATE UNIQUE INDEX uq_active_accommodation_employee
  ON accommodation_records(active_employee_id);
CREATE UNIQUE INDEX uq_active_accommodation_bed
  ON accommodation_records(active_bed_id);

ALTER TABLE bed_reservations
ADD COLUMN active_employee_id BIGINT UNSIGNED
    GENERATED ALWAYS AS (
      CASE WHEN status = 'active' THEN employee_id ELSE NULL END
    ) STORED,
ADD COLUMN active_bed_id BIGINT UNSIGNED
    GENERATED ALWAYS AS (
      CASE WHEN status = 'active' THEN bed_id ELSE NULL END
    ) STORED;

CREATE UNIQUE INDEX uq_active_reservation_employee
  ON bed_reservations(active_employee_id);
CREATE UNIQUE INDEX uq_active_reservation_bed
  ON bed_reservations(active_bed_id);
```

> **重要**：上述四个索引分别约束两张表内部，**不能单独阻止预留与正式入住跨表冲突**。必须使用统一事务和床位行锁，在所有资源变更入口重新检查两张表。

可以为住宿记录增加检查约束（具体按迁移模型同步）：

```sql
ALTER TABLE accommodation_records
ADD CONSTRAINT chk_accommodation_dates CHECK (
   (status = 'active' AND checkout_at IS NULL)
   OR
   (status = 'ended' AND checkout_at IS NOT NULL
      AND checkout_at >= checkin_at)
   OR status = 'voided'
);
```

`checkout_records` 中同一住宿记录只能存在一个未完结退宿单，可采用同类生成列唯一约束（针对 `pending`、`inspection`）；`workflow_todos` 针对 `pending` 设计业务范围内的唯一性约束。必须为常用外键及报表查询条件建索引。

### 5.4 并发事务和锁顺序

入住房间必须遵守：

1. 开始数据库事务。
2. 以 `SELECT ... FOR UPDATE` 锁定员工行。
3. 锁定涉及的床位行；若多个床位，按 bed_id 从小到大加锁。
4. 检查员工状态、楼栋/楼层/房间/床位启用状态及性别规则。
5. 查询有效入住和有效预留，校验床位及员工都未发生冲突；若为自己的预留，允许按规则消耗。
6. 创建/更新住宿、预留、申请、调宿/退宿业务单据及审计日志。
7. 一并提交或全部回滚。

遇到冲突返回 HTTP 409，客户端刷新床位数据；遇到数据库死锁可按明确策略有限重试，但不得绕过唯一约束。关键动作支持 `Idempotency-Key`，防止重复点击产生重复业务。

### 5.5 床位状态的正确表示

`dorm_beds.operational_status` 仅存 `active / maintenance / disabled`。是否已入住与是否已预留由关联表计算。房间页面展示：空闲、预留、已入住、维修、停用；维修中已有住户要额外显示“有在住人员待处理”异常，而不是隐藏占用。

---

## 6. REST API 详细清单

统一前缀 `/api/v1`，常规列表返回 `{items,total,page,page_size}`，业务错误返回 `{code,message,details,request_id}`。分页默认 `page=1,page_size=20`，服务端设置上限。使用 OpenAPI 生成前端类型。

### 6.1 认证、用户与角色

| 方法 | 路径 | 描述 |
|---|---|---|
| POST | `/auth/login` | 登录 |
| POST | `/auth/logout` | 登出 |
| POST | `/auth/refresh` | 刷新会话（若采用可刷新 Token） |
| GET | `/auth/me` | 当前用户 |
| GET | `/auth/permissions` | 当前权限 |
| GET | `/users` | 后台账号列表 |
| POST | `/users` | 创建账号 |
| PATCH | `/users/{id}` | 修改账号 |
| PUT | `/users/{id}/roles` | 授予角色 |
| GET | `/roles` | 角色列表 |
| GET | `/permissions` | 权限字典 |

### 6.2 员工与 Excel

| 方法 | 路径 | 描述 |
|---|---|---|
| GET | `/employees` | 员工列表，支持部门、人事状态、住宿状态、关键字筛选 |
| POST | `/employees` | 创建员工 |
| GET | `/employees/{id}` | 员工详情 |
| PATCH | `/employees/{id}` | 编辑员工 |
| GET | `/employees/{id}/accommodation` | 当前住宿 |
| GET | `/employees/{id}/history` | 住宿历史 |
| POST | `/employees/{id}/offboarding` | 发起离职办理 |
| POST | `/employees/{id}/terminate` | 确认离职 |
| GET | `/employees/import/template` | 下载模板 |
| POST | `/employees/import/preview` | 上传、预检和预览 |
| POST | `/employees/import/commit` | 确认提交导入 |
| GET | `/imports/{id}` | 导入任务状态 |
| GET | `/imports/{id}/errors` | 错误清单 |
| GET | `/employees/export` | 导出员工资料 |

### 6.3 宿舍资源

| 方法 | 路径 | 描述 |
|---|---|---|
| GET/POST | `/dorm-areas` | 查询/新增区域 |
| PATCH | `/dorm-areas/{id}` | 修改区域 |
| GET/POST | `/buildings` | 查询/新增宿舍楼 |
| PATCH | `/buildings/{id}` | 修改宿舍楼 |
| GET | `/buildings/{id}/floors` | 楼层列表 |
| POST | `/floors` | 新增楼层 |
| PATCH | `/floors/{id}` | 修改楼层 |
| GET/POST | `/rooms` | 房间列表/新增房间 |
| GET/PATCH | `/rooms/{id}` | 房间详情/修改 |
| GET/POST | `/rooms/{id}/beds` | 房间床位列表/新增 |
| PATCH | `/beds/{id}` | 修改床位基础信息 |
| POST | `/beds/{id}/disable` | 停用床位（校验当前占用） |
| POST | `/beds/{id}/enable` | 启用床位 |
| GET | `/beds/available` | 查询可分配床位 |
| GET | `/dormitories/tree` | 宿舍层级导航树 |
| GET | `/buildings/{id}/occupancy` | 宿舍楼占用汇总 |

### 6.4 入住

| 方法 | 路径 | 描述 |
|---|---|---|
| GET/POST | `/checkin-applications` | 列表/创建入住申请 |
| GET | `/checkin-applications/{id}` | 申请详情 |
| POST | `/checkin-applications/{id}/approve` | 批准 |
| POST | `/checkin-applications/{id}/reject` | 驳回 |
| POST | `/checkin-applications/{id}/reserve` | 预留床位 |
| POST | `/checkin-applications/{id}/confirm` | 确认入住 |
| POST | `/checkin-applications/{id}/cancel` | 取消 |
| GET | `/accommodations/active` | 在住人员 |
| GET | `/accommodations/{id}` | 住宿记录详情 |
| GET | `/accommodations/history` | 历史住宿记录 |

### 6.5 调宿

| 方法 | 路径 | 描述 |
|---|---|---|
| GET/POST | `/transfers` | 列表/创建调宿申请 |
| GET | `/transfers/{id}` | 调宿详情 |
| POST | `/transfers/{id}/reserve` | 预留目标床位 |
| POST | `/transfers/{id}/complete` | 确认调宿 |
| POST | `/transfers/{id}/cancel` | 取消调宿及预留 |

### 6.6 退宿

| 方法 | 路径 | 描述 |
|---|---|---|
| GET/POST | `/checkouts` | 列表/创建退宿申请 |
| GET | `/checkouts/{id}` | 退宿详情 |
| PATCH | `/checkouts/{id}/inspection` | 录入检查信息 |
| POST | `/checkouts/{id}/complete` | 完成退宿 |
| POST | `/checkouts/{id}/cancel` | 取消退宿 |

### 6.7 待办、预警与报表

| 方法 | 路径 | 描述 |
|---|---|---|
| GET | `/todos` | 我的待办 |
| GET | `/todos/summary` | 待办汇总 |
| POST | `/todos/{id}/acknowledge` | 标记已读（不改变业务完成状态） |
| GET | `/alerts` | 异常预警 |
| GET | `/alerts/summary` | 预警汇总 |
| GET | `/offboarding/pending-checkouts` | 离职待退宿 |
| GET | `/dashboard/summary` | 首页指标 |
| GET | `/dashboard/occupancy` | 入住率 |
| GET | `/dashboard/trends` | 入退宿趋势 |
| GET | `/reports/accommodations` | 住宿台账 |
| GET | `/reports/vacant-beds` | 空床统计 |
| GET | `/reports/departments` | 部门统计 |
| GET | `/reports/checkin-checkout` | 入退宿明细 |
| GET | `/reports/transfers` | 调宿明细 |
| GET | `/reports/exceptions` | 异常报表 |
| GET | `/reports/{report_type}/export` | 报表 Excel 导出 |

API 规范：前端不得自行更新住宿状态。日期与时间使用 ISO 8601；审批/取消等动作须在服务层验证状态转换。对于重复执行的操作明确返回上一次结果或业务冲突，不产生重复数据。

---

## 7. 前端页面与组件规划

采用统一后台布局：顶部栏、左侧导航、主区域、消息/待办入口。所有数据都由真实 API 加载，提供 loading、空状态、错误提示和权限控制。

| 路由 | 页面 | 主要组件 |
|---|---|---|
| `/login` | 登录 | `LoginForm.vue` |
| `/dashboard` | 首页 | `SummaryCards.vue`, `OccupancyChart.vue`, `CheckinTrendChart.vue`, `TodoList.vue`, `AlertList.vue` |
| `/employees` | 员工管理 | `EmployeeTable.vue`, `EmployeeSearchForm.vue`, `EmployeeFormDialog.vue`, `EmployeeDetailDrawer.vue`, `EmployeeImportDialog.vue`, `AccommodationHistory.vue` |
| `/dormitories` | 宿舍资源 | `DormitoryTree.vue`, `RoomTable.vue`, `RoomFormDialog.vue`, `BedGrid.vue`, `BedCard.vue`, `BedDetailDrawer.vue` |
| `/bed-allocation` | 可视化分床 | `AllocationFilter.vue`, `RoomGrid.vue`, `RoomCard.vue`, `BedSelectionDialog.vue`, `EmployeeSelectionDialog.vue`, `AllocationConfirmDialog.vue` |
| `/checkins` | 入住管理 | `CheckinApplicationTable.vue`, `CheckinApplicationForm.vue`, `BedAllocationDialog.vue`, `CheckinConfirmDialog.vue` |
| `/transfers` | 调宿管理 | `TransferTable.vue`, `TransferApplicationDialog.vue`, `TargetBedSelector.vue`, `TransferConfirmDialog.vue` |
| `/checkouts` | 退宿管理 | `CheckoutTable.vue`, `CheckoutInspectionForm.vue`, `CheckoutConfirmDialog.vue` |
| `/todos` | 待办中心 | `TodoSummary.vue`, `TodoTable.vue`, `AlertTable.vue`, `TodoDetailDrawer.vue` |
| `/reports` | 统计报表 | `ReportFilter.vue`, `AccommodationReport.vue`, `VacantBedReport.vue`, `DepartmentAccommodationReport.vue`, `CheckinCheckoutReport.vue`, `TransferReport.vue`, `ExceptionReport.vue`, `ExportButton.vue` |
| `/settings` | 系统设置 | `UserTable.vue`, `RolePermissionEditor.vue` |

### 7.1 可视化床位分配详细交互

1. 选择待入住员工，显示员工姓名、工号、部门及住宿状态。
2. 根据员工和住宿策略筛选可用床位；左侧展示区域 → 宿舍楼 → 楼层树。
3. 右侧以房间卡片展示：房间号、核定容量、当前入住人数、预留数、可分配床位数。
4. 房间内展示床位卡片：`空闲 / 已预留 / 已入住 / 维修 / 停用`，附带文本和图标，不仅依靠颜色。
5. 单击空闲床位 → 确认弹窗 → 调用后端预留 API。
6. 成功后刷新数据；发生 409 资源冲突时提示其他管理员已分配该床位并刷新。
7. 根据角色权限隐藏操作入口；后端仍独立校验权限。

### 7.2 首页指标

房间总数、可用床位总数、已入住数、已预留数、当前可分配空床、入住率、今日待入住、今日待退宿、离职未退宿异常、部门住宿人数、入退宿趋势和个人待办。

---

## 8. 角色权限矩阵

符号：`✓` 允许，`◇` 只限已授权的数据范围，`—` 不允许。

| 功能 | 超级管理员 | 人事 | 行政宿管 | 财务只读 | 部门负责人 |
|---|:---:|:---:|:---:|:---:|:---:|
| 员工档案查询 | ✓ | ✓ | ◇ | — | ◇ |
| 员工新增/编辑 | ✓ | ✓ | — | — | — |
| Excel 导入 | ✓ | ✓ | — | — | — |
| 发起员工离职 | ✓ | ✓ | — | — | — |
| 宿舍资源查询 | ✓ | ✓ | ✓ | ◇ | ◇ |
| 宿舍资源维护 | ✓ | — | ✓ | — | — |
| 分配床位/入住确认 | ✓ | — | ✓ | — | — |
| 调宿办理 | ✓ | — | ✓ | — | — |
| 退宿办理 | ✓ | — | ✓ | — | — |
| 待办查询 | ✓ | ◇ | ✓ | — | ◇ |
| 住宿报表查看 | ✓ | ✓ | ✓ | ◇ | ◇ |
| 报表导出 | ✓ | ◇ | ✓ | ◇ | ◇ |
| 用户/角色管理 | ✓ | — | — | — | — |
| 审计日志 | ✓ | — | — | — | — |

建议权限编码：`employee:view/create/update/import/export/offboard`、`dorm:view/create/update`、`bed:manage`、`checkin:view/create/approve/allocate/confirm`、`transfer:view/create/complete`、`checkout:view/create/inspect/complete`、`report:view/export`、`user:manage`、`role:manage`、`audit:view`。请求在后端校验 RBAC + 部门数据范围。

---

## 9. Excel 导入和初始数据迁移

### 9.1 员工模板字段

员工工号（必填）、员工姓名（必填）、性别、部门编码、岗位、入职日期、联系电话、用工类型、班次、是否需要住宿。

### 9.2 两阶段导入

**预览：** 上传 Excel → 检查表头和文件大小 → 解析数据 → 检查空工号、重复工号、日期格式、部门编码 → 对照已有员工列出 `新增 / 更新 / 跳过 / 错误` → 展示预览，不修改正式员工表。

**提交：** 使用导入批次 ID 再次检查 → 写入数据库 → 记录新增和更新统计 → 生成错误明细。导入过程必须有明确的事务边界及部分失败策略，避免悄悄写入不一致数据。

### 9.3 现有宿舍台账迁移

初始化顺序：部门 → 员工 → 宿舍区域/楼栋/楼层 → 房间与床位 → 既有入住记录 → 一致性检查。初始迁移与日常入住业务使用不同入口，不对历史入住重复触发审批或新入住待办。保留原始台账导入批次标识。

---

## 10. 统计口径

- **当前入住人数**：`accommodation_records.status = 'active'` 的记录数。
- **已入住床位**：存在 `active` 住宿记录的不同床位数。
- **已预留床位**：存在 `active` 预留且未正式占用的不同床位数。
- **可用床位总数**：所属区域、楼栋、楼层、房间及床位均启用，并满足可分配政策的床位数。
- **当前可分配空床**：可用床位中不存在有效入住及有效预留的床位数。
- **入住率**：可用床位范围内的已入住床位数 / 可用床位总数；分母为零显示“不适用”。
- **部门住宿人数**：当前所属部门员工的有效入住人数。
- **异常预警**：离职仍在住、预留到期未释放、停用床位仍有人入住、待退宿超期等。

特别注意：**“可用床位总数”和“全部物理床位总数”不同**，首页和 Excel 使用相同后端统计口径。

---

## 11. 安全和非功能性要求

- 所有业务接口默认要求认证；登录密码使用 Argon2id 等安全哈希；管理员可禁用账号。
- 采用可撤销的认证机制；生产 HTTPS；若采用 Cookie，配置 HttpOnly、Secure、SameSite 并实施必要的 CSRF 防护。
- 数据库不向公网暴露端口；数据库和应用账户最小权限。
- 不存储不必要的身份证信息；手机号等敏感信息根据角色权限脱敏；禁止导出超权限字段。
- 上传 Excel 限制大小、文件类型和内容，不能将用户提供的文件直接当作可执行代码。
- 操作日志覆盖：分配床位、确认入住、调宿、退宿、离职状态变动、数据导入、管理员权限变更。
- 错误响应不包含 SQL、连接密码或堆栈细节；日志带 request_id。
- 目标参考容量：1 万员工、1 万床位、2 千房间、50 并发后台用户。
- 目标参考性能：普通列表和搜索的 95% 请求在 2 秒内完成；分床正常负载下 3 秒内完成。最终性能由部署环境压测验证。
- 每日自动数据库备份、可手动备份和恢复；备份加密存放并定期恢复演练。

---

## 12. Docker Compose 部署结构

生产建议服务：`frontend`（Nginx + 静态文件）、`backend`（FastAPI）、`mysql`，`redis` 为可选 profile。数据库独立内网，不暴露到宿主公网。后台依赖 MySQL 健康检查；正式上线需独立运行 Alembic migration。

### 12.1 `compose.yaml` 参考骨架

```yaml
name: dormitory-management-system
services:
  mysql:
    image: mysql:8.0
    restart: unless-stopped
    environment:
      TZ: UTC
      MYSQL_DATABASE: ${MYSQL_DATABASE:-dms}
      MYSQL_USER: ${MYSQL_USER:-dms_user}
      MYSQL_PASSWORD: ${MYSQL_PASSWORD:?Set MYSQL_PASSWORD}
      MYSQL_ROOT_PASSWORD: ${MYSQL_ROOT_PASSWORD:?Set MYSQL_ROOT_PASSWORD}
    volumes:
      - mysql_data:/var/lib/mysql
    networks: [internal]
    healthcheck:
      test: ["CMD-SHELL", "MYSQL_PWD=\"$$MYSQL_PASSWORD\" mysqladmin ping -h 127.0.0.1 -u \"$$MYSQL_USER\" --silent"]
      interval: 10s
      timeout: 5s
      retries: 10
      start_period: 40s

  backend:
    build: ./backend
    restart: unless-stopped
    environment:
      TZ: UTC
      MYSQL_HOST: mysql
      MYSQL_PORT: 3306
      MYSQL_DATABASE: ${MYSQL_DATABASE:-dms}
      MYSQL_USER: ${MYSQL_USER:-dms_user}
      MYSQL_PASSWORD: ${MYSQL_PASSWORD:?Set MYSQL_PASSWORD}
      SECRET_KEY: ${SECRET_KEY:?Set SECRET_KEY}
      APP_ENV: ${APP_ENV:-production}
    depends_on:
      mysql:
        condition: service_healthy
    networks: [internal, frontend_net]
    expose: ["8000"]
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=3)"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 30s

  frontend:
    build: ./frontend
    restart: unless-stopped
    ports:
      - "${WEB_PORT:-8080}:80"
    depends_on:
      backend:
        condition: service_healthy
    networks: [frontend_net]

  redis:
    image: redis:7-alpine
    restart: unless-stopped
    profiles: [cache]
    volumes: [redis_data:/data]
    networks: [internal]

networks:
  frontend_net:
  internal:
    internal: true

volumes:
  mysql_data:
  redis_data:
```

> 这是基础部署结构示例，并非独立即可运行的完整项目。MiMo 必须补全 Dockerfile、依赖锁定、Nginx 配置、`/health` 接口、Alembic 迁移和初始化管理员流程。注意 MySQL 密码如含 URL 特殊字符，后端应使用安全 URL 构造方法连接数据库。

### 12.2 `deploy/nginx/default.conf` 参考

```nginx
server {
    listen 80;
    server_name _;
    root /usr/share/nginx/html;
    index index.html;

    location /api/ {
        proxy_pass http://backend:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

### 12.3 交付配置

MiMo 应创建 `.env.example`、前后端 Dockerfile、`compose.yaml`、Nginx 配置、数据库迁移、数据库备份/恢复脚本及详细 README。提供 Windows Docker Desktop、macOS 和 Linux 的启动指令。不得将真实 `.env` 加入 Git。

---

## 13. 测试与验收用例

| 测试用例 | 预期结果 |
|---|---|
| 员工 Excel 导入重复工号 | 预览报告冲突，按明确选项新增/更新/跳过，不重复建档 |
| 宿舍楼→楼层→房间→床位创建 | 外键和唯一编号生效，数据可在 UI 查询 |
| 两名管理员同时预留同一床位 | 仅一笔成功，另一笔返回 409 |
| 两名管理员同时为同一员工安排床位 | 仅一笔有效分配成功 |
| 预留后确认入住 | 预留转 consumed，新增 active 住宿记录 |
| 同一入住确认重复请求 | 幂等、不重复新增有效住宿 |
| 已入住床位再次申请入住 | 后端拒绝操作 |
| 调宿确认 | 原住宿 ended，新住宿 active，历史可查询 |
| 目标床位冲突时调宿 | 事务回滚，原住宿保持不变 |
| 退宿完成 | 住宿 ended，床位恢复可分配，历史保留 |
| 调宿与退宿同时执行 | 不产生多条有效住宿或悬空预留 |
| 人事发起离职 | 生成退宿待办但不释放当前床位 |
| 已离职但仍在住 | 首页与异常报表显示异常 |
| 停用房间分配床位 | 后端拒绝新分配 |
| 部门负责人查询其他部门 | 不允许读取越权数据 |
| 无权限调用退宿 API | 返回 403 |
| 报表 Excel 导出 | 数据与筛选口径一致且按权限脱敏 |
| 备份→恢复→查询历史 | 数据完整，能正确恢复服务 |

使用 pytest + httpx 覆盖服务及接口，MySQL 集成测试必须运行在真实 MySQL 8.0 上，不能仅用 SQLite 测试并发语义。

---

## 14. 业务异常处理

- **预留超期：** 通过定时后台任务（或定时调度容器）定期扫描，锁定预留后将其标记 expired；处理过程幂等。
- **员工已离职却仍在住：** 保留占用记录，生成预警和退宿待办。
- **维修床位仍在住：** 显示异常，不自动删除在住关系。
- **管理员多人同时分床：** 事务串行化关键床位资源，冲突返回 409。
- **操作重复提交：** 对关键写入提供幂等键；不得简单重复建单。
- **系统异常中断：** 事务全部回滚，前端可安全重试。
- **房间容量变更：** 不得小于既有床位定义或在住人数，不得直接删除已占用床位。
- **变更员工部门：** 当前住宿台账按最新部门统计；历史快照需要额外设计时明确说明。

---

## 15. 交付文件清单

1. 完整前端源码与页面。
2. 完整 FastAPI 后端源码。
3. 所有 SQLAlchemy ORM 模型与 Alembic 迁移。
4. 所有 REST API、OpenAPI 文档、统一错误处理。
5. 可运行的 Dockerfile、Compose 和 Nginx 配置。
6. `.env.example` 及首次初始化管理员脚本。
7. 员工 Excel 导入模板及示例数据（不得使用真实个人信息）。
8. 各业务自动化测试及测试结果。
9. 部署、启动、升级、备份、恢复操作文档。
10. 数据库结构、权限矩阵、业务状态机和 API 说明。
11. 首版功能验收清单与已知限制。

---

## 16. 分阶段开发指令（MiMo 执行顺序）

### M1：项目骨架与认证

建立仓库及目录、前后端基本工程、Docker Compose、MySQL、数据库迁移、认证、用户/角色/权限、统一 API 格式、审计基础、健康检查。完成后验证能打开登录页、登录成功、连接数据库，迁移可重复执行。

### M2：基础数据

实现部门、员工档案、Excel 导入和宿舍区域/楼栋/楼层/房间/床位 CRUD；写入唯一约束和外键；补全基础数据 API 与 Vue 页面。完成后能够建立真实宿舍结构并导入员工。

### M3：完整住宿事务闭环

实现入住申请、预留、入住确认、调宿和退宿；所有操作封装 Service、统一行锁及状态机；配套幂等与并发测试。完成后能通过真实页面从入职分床一直办理到退宿。

### M4：离职联动与预警

人事状态事件、离职待办、预留到期、异常预警、待办查询与审计事件。完成后离职员工的宿舍状态不会被无故清空，行政可在待办中处理。

### M5：可视化与报表

实现宿舍树、房间/床位卡片、可视化分配、仪表盘、住宿台账和各类统计、Excel 导出。所有展示使用真实后端计算结果。

### M6：联调、迁移和上线验证

运行后端单元/集成/并发测试、前端类型检查、端到端验收、原 Excel 历史数据迁移演练、备份恢复与 Docker 全量重建测试。修复失败后才可标记 V1.0 可交付。

### 每个阶段必须输出的结果

- 新增/修改的实际文件列表。
- API 和数据库变更摘要。
- 运行命令与测试结果（成功/失败如实报告）。
- 已实现功能清单、尚未实现功能清单。
- 若存在阻塞，仅给出可复现问题与下一步建议，不虚报完成。

---

## 17. V1.0 最终验收标准

- [ ] 可以登录并按角色限制访问功能与数据。
- [ ] 可以从 Excel 批量导入、编辑及查询员工。
- [ ] 可以新增及维护宿舍楼、楼层、房间和床位。
- [ ] 可以实时查看空闲、预留、已入住及停用床位。
- [ ] 可以创建入住申请、预留床位并确认入住。
- [ ] 可以完整办理调宿并保留原住宿历史。
- [ ] 可以完整办理退宿并正确释放床位。
- [ ] 离职人员自动进入行政待退宿流程。
- [ ] 已离职但未退宿的人员能够触发异常预警。
- [ ] 可以查询和导出住宿台账、空床及部门统计。
- [ ] 多人同时分床不会产生重复有效占用。
- [ ] 关键操作均具有可追溯的审计日志。
- [ ] 所有业务模块通过必要的自动化测试。
- [ ] 可通过 Docker Compose 在目标机器部署。
- [ ] 经过实际数据库备份及恢复验证。

**最终完成定义：** 以上项目全部验收通过，且源码、迁移脚本、自动化测试、部署说明均可交付，才视为 V1.0 开发完成。

---

## 18. 推荐的首条 MiMo Code 提示词

```text
请读取项目根目录的 DMS_V1.0_MiMo_Development_Spec.md，严格依据文档从零开发公司宿舍入住管理系统。

请先完成以下事项：
1. 复述已确定的 V1.0 范围和必须满足的关键业务约束；
2. 创建 docs/IMPLEMENTATION_PLAN.md 和 docs/DECISIONS.md；
3. 按第16节从 M1 开始建立真实项目文件，而不是仅输出示例代码；
4. 使用 Vue3+TS+Element Plus、FastAPI+SQLAlchemy2 async、MySQL8、Alembic、Docker Compose；
5. 不允许遗漏权限控制、事务唯一性、迁移文件、健康检查、环境配置和自动化测试；
6. 每完成一个里程碑运行测试并汇报结果，再继续下一阶段；
7. 全程保持中文说明，代码及字段使用规范英文命名。

现在开始执行 M1：项目骨架与认证。优先给出文件清单并直接创建文件，完成后执行实际验证。
```


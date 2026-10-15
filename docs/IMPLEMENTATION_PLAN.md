# DMS V1.0 实施计划

> 依据：`DMS_V1.0_MiMo_Development_Spec.md` 第 16 节分阶段开发指令  
> 原则：每阶段可验证、先闭环后可视化、禁止伪代码交付

## 1. 里程碑总览

| 里程碑 | 目标 | 完成判据 | 状态 |
|---|---|---|---|
| M1 | 项目骨架与认证 | 登录页可用、JWT 认证、RBAC 基础、迁移可重复执行、`/health` 正常、基础测试通过 | 已完成（2026-10-13） |
| M2 | 基础数据 | 部门/员工/Excel 导入、宿舍区域→床位 CRUD，唯一约束与外键生效 | 已完成（2026-10-13） |
| M3 | 完整住宿事务闭环 | 入住申请→预留→确认入住、调宿、退宿；事务+行锁+状态机+幂等；并发测试通过 | 已完成（2026-10-13） |
| M4 | 离职联动与预警 | 离职状态事件、退宿待办、预留过期扫描、异常预警 | 已完成（2026-10-13） |
| M5 | 可视化与报表 | 宿舍树/床位卡片/可视化分床、仪表盘、台账与 Excel 导出 | 已完成（2026-10-13） |
| M6 | 联调、迁移和上线验证 | 全量测试、历史数据迁移演练、备份恢复、Docker 全量重建 | 已完成（2026-10-14） |

## 2. M1 详细任务

### 2.1 后端

| 任务 | 说明 | 状态 |
|---|---|---|
| 目录与依赖 | `backend/` 工程、`pyproject.toml` | 已完成 |
| 配置与数据库 | Pydantic Settings、SQLAlchemy 2 async engine/session | 已完成 |
| 安全 | Argon2id 密码哈希、JWT 签发/校验、可撤销会话 | 已完成 |
| 权限模型 | sys_users/roles/permissions 及关联表、权限码字典 | 已完成 |
| 统一 API | 错误格式 `{code,message,details,request_id}`、分页信封 | 已完成 |
| 认证接口 | login/logout/refresh/me/permissions | 已完成 |
| 用户与角色接口 | users CRUD、授予角色、roles/permissions 查询 | 已完成 |
| 审计基础 | audit_logs 仅追加表 + 写入服务 | 已完成 |
| Alembic | 初始迁移（认证/审计相关表），可重复执行 | 已完成 |
| 健康检查 | `/health`、`/health/ready` | 已完成 |
| 初始化 | 默认权限/角色种子 + 管理员初始化脚本 | 已完成 |
| 测试 | 认证、用户、权限、健康检查自动化测试 | 已完成（16/16 通过） |

### 2.2 前端

| 任务 | 说明 | 状态 |
|---|---|---|
| Vite + Vue3 + TS 工程 | 严格 TS、Element Plus、Pinia、Vue Router | 已完成 |
| API Client | Axios 统一拦截、401 跳转、错误提示 | 已完成 |
| 登录页 | 真实调用 `/auth/login` | 已完成 |
| 主布局 | 顶栏/侧栏/路由守卫（权限隐藏入口） | 已完成 |
| 用户管理页 | 账号列表、创建、授权角色 | 已完成 |
| 类型定义 | 与后端 Schema 保持一致 | 已完成 |

### 2.3 部署与运维

| 任务 | 说明 | 状态 |
|---|---|---|
| Docker Compose | mysql + backend + frontend，健康检查依赖 | 已完成 |
| Dockerfile | 前后端镜像构建 | 已完成 |
| Nginx | SPA 路由 + `/api/` 反代 | 已完成 |
| 环境配置 | `.env.example`（无真实凭据） | 已完成 |
| 备份脚本 | `scripts/backup.sh` / `restore.sh` | 已完成 |

## 3. 后续里程碑任务分解（概要）

### M2 基础数据（2026-10-13 完成）

| 任务 | 说明 | 状态 |
|---|---|---|
| 迁移 `0002_m2_master_data` | departments / employees / dorm_* / import_jobs，唯一约束与外键 | 已完成 |
| 部门 API + 前端 | 列表/树、创建、编辑；权限复用 `employee:view/create/update` | 已完成 |
| 员工 API + 前端 | CRUD、详情、工号唯一校验、筛选（部门/人事状态/关键字） | 已完成 |
| Excel 模板/导入/导出 | 模板下载、两阶段 preview/commit、错误报告、导出 | 已完成 |
| 宿舍资源 API + 前端 | 区域→楼栋→楼层→房间→床位 CRUD、树导航、床位启停 | 已完成 |
| 测试与回归 | 24/24 通过（含 M1 回归）+ 运行时实测 + `docs/M2_ACCEPTANCE_REPORT.md` | 已完成 |

M2 边界（不做 M3/M4）：不建 `accommodation_*` / `bed_reservations` / `transfer_*` / `checkout_*` / `workflow_todos` 等表；`/employees/{id}/accommodation|history` 返回空；离职办理仅支持 `employment_status` 字段更新，不生成待办。

### M3 住宿事务（2026-10-13 完成）

| 任务 | 说明 | 状态 |
|---|---|---|
| 迁移 `0003_m3_accommodation` | accommodation_applications / bed_reservations / accommodation_records / transfer_records / checkout_records；生成列 UNIQUE（active 员工/床位、未完结退宿单）+ CHECK | 已完成 |
| 入住 API + Service | 创建/批准/驳回/预留/确认/取消，状态机 pending→approved→reserved→checked_in | 已完成 |
| 调宿 API + Service | 创建/预留目标/确认/取消；确认时同事务结束旧住宿、创建新住宿、消耗预留 | 已完成 |
| 退宿 API + Service | 创建/检查录入/完成/取消；完成结束住宿并释放床位 | 已完成 |
| 床位状态推导 | occupied/reserved/available 由关联表计算；停用占用床拒绝 | 已完成 |
| 员工住宿查询 | `/employees/{id}/accommodation|history` 真实数据；列表按 in_dorm/reserved/not_in_dorm 筛选 | 已完成 |
| 锁顺序 | 员工行 → 床位行（bed_id 升序）→ 业务行；跨表冲突事务内复检 | 已完成 |
| 幂等 | 确认入住/完成调宿/完成退宿重复请求返回既有结果；Idempotency-Key 可选去重 | 已完成 |
| 前端 | CheckinsView / TransfersView / CheckoutsView + API Client + 类型 | 已完成 |
| 测试与回归 | M3 集成/并发 18 项 + M1~M3 全量 42/42 通过 + Docker 运行时实测 | 已完成 |

M3 边界（不做 M4/M5）：不建 `employee_status_events` / `workflow_todos` / `idempotency_keys`；预留过期扫描、离职联动待办、可视化分床与报表属 M4/M5。

### M4 离职联动
- employee_status_events（幂等 source+source_event_id）
- workflow_todos
- 预留过期扫描任务
- alerts 接口（离职仍在住、预留超期、停用仍占用、退宿超期）

### M5 可视化与报表
- 宿舍树、房间/床位卡片、可视化分床
- dashboard 指标（统计口径见规格第 10 节）
- reports 六类报表 + Excel 导出

### M6 上线验证（2026-10-14 完成）
- 全量 pytest 81 + Vitest 4 + Playwright 6 + vue-tsc/build
- P0-1 Dashboard/报表部门数据隔离修复与测试
- P0-2 Playwright 真实分床（成功/409/不可用床）
- P0-3 全生命周期（入职→入住→调宿→离职→退宿→归档）
- P0-4 备份恢复演练（隔离库）+ Alembic 全新库迁移
- P0-5 安全加固（HTTPS 样例、生产关文档、上传限制、越权 403）
- 性能 smoke + 历史 Excel 导入演练
- 交付：M6 验收报告 / DEPLOYMENT / USER_MANUAL / BACKUP_RESTORE / RELEASE_CHECKLIST

## 4. 验证与汇报节奏

每个里程碑结束时必须：
1. 运行格式/类型检查（ruff / mypy 或 pyright；vue-tsc）
2. 运行数据库迁移（alembic upgrade head）
3. 运行相关自动化测试并如实报告结果
4. 输出：文件清单、API/DB 变更、已实现/未实现、阻塞项

## 5. 状态标记约定

- `待开始` → `进行中` → `已完成` / `阻塞（原因）`
- 测试失败未修复不得标记完成

### M4 离职联动（2026-10-13 完成）
- employee_status_events（幂等 source+source_event_id）
- workflow_todos / workflow_alerts / notifications
- 离职办理 → 退宿待办；离职未退宿预警
- 预留过期扫描 + 异常预警扫描（进程内定时 + 手动 API）
- 待办中心前端（待办/预警）

### M5 可视化与报表（2026-10-13 完成）
- 部门数据范围：`sys_user_departments` + `data_scope` 服务（超管/HR 全量；其余按授权部门∪管理部门及下级）
- 员工/住宿/调宿/退宿/待办/预警/报表/导出全量按范围过滤；越权详情 403
- Dashboard：summary / occupancy / trends
- 报表：住宿台账、空床、部门、入退宿、调宿、异常 + Excel 导出
- 可视化分床：楼层 room-cards、房间/床位五态、分配冲突 409 提示
- 前端：Dashboard 图表、BedAllocationView、ReportsView
- 测试：后端 15 项 M5（P0 数据隔离 4 + 报表 6 + 分床 5）、Vitest 4、Playwright 3

## V1.0.1 HOTFIX 状态（2026-10-15）

| 项 | 状态 | 说明 |
|---|---|---|
| V1.0.1 BUG-001～FEAT-008 | 已完成 | 见 `V1_0_1_FIX_REPORT.md` / 补强/安全报告 |
| HOTFIX-04/05/06/07A | 已完成 | 含 UX/BUG 修复与预留过期状态同步 |
| HOTFIX-07A 根因修复 | **保留** | 预留过期同步 reserved→approved + 锁序统一 |
| **HOTFIX-07B 历史数据修复** | **已取消（用户决定）** | 开发测试数据不迁生产；不批量修复 C1/C5 |
| 调宿锁序风险 | 记录中 | 正式验收前专项测试（见 07B 报告 §3） |
| 下一步 | 全新库部署演练 + 全业务流程 + 最终验收 | **不**自行宣布 V1.0.1 发布 |

正式部署策略：生产从**空库** Alembic 初始化 + RBAC seed + 真实资料录入，**不迁移**开发测试数据。

# DMS V1.0 技术与业务决策记录

> 规格不明确处的取舍统一记录在此，不擅自扩大需求。

## D-001 密码哈希算法
- **决策**：使用 Argon2id（`argon2-cffi`），而非 bcrypt。
- **依据**：规格 §11「登录密码使用 Argon2id 等安全哈希」。
- **影响**：依赖 `argon2-cffi`；哈希参数使用库默认安全参数。

## D-002 认证令牌机制
- **决策**：采用双 Token：`access_token`（短期，JWT）+ `refresh_token`（较长，可撤销，存数据库）。
- **依据**：规格 §6.1 含 `/auth/refresh`，且 §11 要求「可撤销的认证机制」。
- **影响**：`sys_users` 旁增加刷新令牌关联表 `auth_refresh_tokens`（非规格表名，见 D-003）；登出/禁用账号立即失效。

## D-003 规格外的支撑表
- **决策**：增加 `auth_refresh_tokens` 支撑可撤销会话；不增加其他业务表。
- **依据**：规格允许实现必要支撑结构以满足可撤销认证；业务表严格按 §5.1。
- **影响**：迁移中包含该表；仅存 token 哈希，不存明文。

## D-004 JWT 库
- **决策**：使用 `PyJWT`（而非 python-jose）。
- **依据**：维护活跃、API 简洁；签名算法 HS256，密钥来自 `SECRET_KEY` 环境变量。
- **影响**：生产必须配置足够强度的 `SECRET_KEY`。

## D-005 错误响应格式
- **决策**：业务错误统一 `{code, message, details, request_id}`；HTTP 状态码保留语义（400/401/403/404/409/422/500）。
- **依据**：规格 §6 统一要求。
- **实现**：FastAPI 全局 exception handler。

## D-006 分页信封
- **决策**：列表接口统一 `{items, total, page, page_size}`。
- **依据**：规格 §6。

## D-007 时间与数据库
- **决策**：应用层统一 UTC；MySQL 连接 `TZ=UTC`；`created_at/updated_at` 为 `DATETIME(6)`。
- **依据**：规格 §5。

## D-008 数据库连接串
- **决策**：使用 SQLAlchemy `URL.create()` 构造连接，避免密码含特殊字符时失败。
- **依据**：规格 §12.1 注释。

## D-009 迁移策略
- **决策**：Alembic 为唯一建表方式；禁止 `create_all` 作为正式路径。迁移可重复 `upgrade head`。
- **依据**：规格 §2 与执行指令第 4 条。

## D-010 活动记录唯一性
- **决策**：M1 仅建立认证相关表；M3 落地 `accommodation_records` / `bed_reservations` 生成列 + 唯一索引（规格 §5.3），并强制 Service 层事务 + 行锁校验跨表冲突。
- **依据**：规格 §5.3 明确生成列不能跨表，必须事务内重检。

## D-011 测试策略
- **决策**：
  - 单元测试（安全、Schema、纯逻辑）不依赖数据库；
  - 集成/并发测试必须跑在真实 MySQL 8.0（Docker Compose），禁止 SQLite 充当并发语义验证。
- **依据**：规格 §13。

## D-012 默认权限编码
- **决策**：采用规格 §8 建议编码：`employee:view/create/update/import/export/offboard`、`dorm:view/create/update`、`bed:manage`、`checkin:view/create/approve/allocate/confirm`、`transfer:view/create/complete`、`checkout:view/create/inspect/complete`、`report:view/export`、`user:manage`、`role:manage`、`audit:view`。
- **影响**：种子数据写入上述权限；角色矩阵见 `docs/PERMISSIONS.md`（M2+ 补全文档）。

## D-013 管理员初始化
- **决策**：首次部署通过 `python -m app.seed`（读取环境变量 `DMS_ADMIN_USERNAME` / `DMS_ADMIN_PASSWORD`）初始化超级管理员与 RBAC 目录；不在源码写死密码。Docker 启动命令已包含该步骤。
- **依据**：执行指令第 6 条。

## D-014 前端类型来源
- **决策**：以 OpenAPI/Pydantic Schema 为权威，手工同步 `frontend/src/types`（M1）；M6 联调时可用 openapi-typescript 自动生成校验一致性。
- **影响**：接口变更须同步前端类型与测试。

## D-015 Redis
- **决策**：V1.0 不把 Redis 作为业务状态唯一依据；Compose 中仅作为可选 profile（`cache`）。
- **依据**：规格 §2「Redis 可选」。

## D-016 审计日志
- **决策**：`audit_logs` 仅追加，禁止 UPDATE/DELETE 路由；敏感字段（密码哈希、token）不入库。
- **依据**：规格 §5.1 与 §11。

## D-017 M1 范围边界
- **决策**：M1 只交付骨架 + 认证/用户/角色/权限/审计/健康检查；不实现员工、宿舍、入住业务（M2/M3）。
- **依据**：规格 §16 里程碑划分，避免一次生成无法验证的大量代码。

## D-018 MySQL 端口与网络
- **决策**：`compose.yaml` 中 MySQL 将 3306 绑定到 `127.0.0.1`（默认变量 `MYSQL_HOST_PORT`），network 保持 bridge 而非 `internal: true`。
- **依据**：Docker 的 `internal: true` 网络会阻止端口发布，导致宿主机无法执行集成测试；仅绑定回环地址仍满足「不对公网暴露」（规格 §11）。生产加固时可删除 ports 映射或继续保持 127.0.0.1。
- **影响**：本地 `pytest` 可直连 MySQL；生产部署应确认不要绑定 `0.0.0.0`。

## D-019 测试连接池与事件循环
- **决策**：测试夹具在每个用例后 `await engine.dispose()`，避免 SQLAlchemy 异步连接池跨 pytest-asyncio 事件循环复用。
- **依据**：pytest-asyncio 默认每用例新建 event loop，池化连接会报 "Future attached to a different loop"。
- **影响**：`tests/conftest.py` 含 autouse 夹具；应用运行时不受影响。

## D-020 异步 ORM 禁止懒加载
- **决策**：服务层一律使用 `selectinload` / 显式查询读取关联，禁止依赖 `user.roles` 等懒加载；需要刷新时用 `populate_existing=True`。
- **依据**：SQLAlchemy 2 async 中懒加载会触发 `MissingGreenlet`。
- **影响**：`user_service._assign_roles` 改为查询 `sys_user_roles` 表。

## D-021 M2 权限复用（不新增权限码）
- **决策**：M2 不新增权限码，继续使用 M1 已落地的 27 个权限码。部门管理读操作用 `employee:view`，写操作用 `employee:update`（创建部门用 `employee:create`）；员工用 `employee:*`；宿舍层级用 `dorm:view/create/update`，床位启停用 `bed:manage`。
- **依据**：AGENTS.md 要求复用既有 RBAC；规格 §8 权限矩阵把部门档案归入员工档案能力，未单列 `dept:` 码。
- **影响**：前端菜单/按钮权限与后端依赖注入保持同一套码。

## D-022 部门接口前缀
- **决策**：提供 `GET/POST /api/v1/departments`、`PATCH /api/v1/departments/{id}`、`GET /api/v1/departments/tree`。规格 §6 未单列部门接口，但数据模型与 M2 交付要求部门可维护。
- **依据**：AGENTS.md M2「部门数据模型、接口、权限和前端页面」。
- **影响**：OpenAPI 与前端类型同步增加部门资源。

## D-023 M2 不建住宿业务表
- **决策**：M2 只建 `departments`、`employees`、`dorm_areas/buildings/floors/rooms/beds`、`import_jobs`。`accommodation_records`、`bed_reservations` 等留到 M3。
- **依据**：AGENTS.md「仅开发 M2 范围内的功能，不提前实现 M3 业务」。
- **影响**：员工「当前住宿/住宿历史」接口返回空结果；床位占用状态暂由 `operational_status` 表示，不计算在住/预留。

## D-024 员工匹配键与导入策略
- **决策**：Excel 导入以 **员工工号 employee_no** 为唯一匹配键；两阶段导入（preview → commit），`import_jobs` 记录批次、哈希、统计与错误文件路径；文件名与解析行存元数据，不存原始 Excel 二进制。
- **依据**：AGENTS.md §5「导入员工资料时以员工工号而非姓名匹配」；规格 §9.2。
- **影响**：预览阶段校验空工号/重复工号/日期/部门编码，返回 `新增/更新/跳过/错误`；提交阶段按批次写入并生成错误明细。

## D-025 M3 业务表与生成列唯一索引
- **决策**：M3 新增 `accommodation_applications` / `bed_reservations` / `accommodation_records` / `transfer_records` / `checkout_records`。对 `bed_reservations` 与 `accommodation_records` 使用 MySQL 生成列 `active_employee_id` / `active_bed_id` + UNIQUE，约束单表内 active 唯一；`checkout_records` 用生成列 `open_accommodation_id` 保证同一住宿仅一张未完结退宿单。
- **依据**：规格 §5.1/§5.3；AGENTS.md 要求数据库级唯一约束。
- **影响**：跨表（预留 vs 入住）冲突仍须服务层在事务 + 行锁内复检（规格 §5.3 注记）。

## D-026 行锁顺序
- **决策**：所有入住/预留/调宿/退宿事务统一锁顺序：`employees` FOR UPDATE → 涉及 `dorm_beds` 按 id 升序 FOR UPDATE → 住宿/预留/业务单据行。
- **依据**：AGENTS.md §4 与规格 §5.4，避免死锁。
- **影响**：`app/services/occupancy.py` 提供 `lock_employee` / `lock_beds` 与跨表冲突校验，三个业务服务共用。

## D-027 M3 幂等策略
- **决策**：状态机守护 + 重复完成/确认返回既有结果（不重复建单）；写入接口可选 `Idempotency_KEY` 字段做去重（单表 UNIQUE）。暂不单独建 `idempotency_keys` 表。
- **依据**：AGENTS.md「幂等处理或等效防重机制」；规格 §5.4。
- **影响**：并发同床预留由生成列 UNIQUE + 行锁保证仅一笔成功，另一笔 409。

## D-028 调宿与退宿互斥
- **决策**：允许调宿单与退宿单同时存在（便于竞态裁决）；但 `complete_transfer` 在存在未完结退宿单时拒绝，`complete_checkout` 在存在未完结调宿单时拒绝。住宿被调宿结束后，指向旧住宿的退宿单完成会返回 409，防止“调走后仍按旧床退宿”。
- **依据**：规格验收用例「调宿与退宿同时执行」不得产生多条有效住宿或悬空预留。
- **影响**：前端可先开退宿再开调宿，完成阶段由事务裁决。

## D-029 床位停用与占用
- **决策**：`disable` 在床位存在 active 住宿或预留时返回 409；`maintenance` 允许已有住户，展示层仍标记 occupied。
- **依据**：规格 §6.3「停用床位（校验当前占用）」与 §5.5 维修中住户不隐藏。
- **影响**：M2 的 `set_bed_status` 占位逻辑替换为真实校验。

## D-030 M4 状态事件幂等键作用域
- **决策**：`employee_status_events` 的 `source_event_id` 在使用自定义 `idempotency_key` 时按员工作用域拼为 `emp{employee_id}:{key}`；默认键为 `offboarding:{id}` / `terminate:{id}`。
- **依据**：规格 §5.4 / P0 场景 C 要求重复事件幂等，且同一 key 不应跨员工碰撞。
- **影响**：命中已有事件时仍执行 `ensure_*` 幂等补齐副作用（补齐因部分失败缺失的待办），不重复生成。

## D-031 人事状态变更走事件管线
- **决策**：`PATCH /employees/{id}` 将 `employment_status` 改为 `offboarding`/`terminated` 时，路由到 `offboarding_service.apply_status_change`，与专用接口共用副作用。
- **依据**：P0 场景 A/B「人事将状态修改为 offboarding/terminated」需一致生成退宿待办/预警。
- **影响**：`EMPLOYMENT_STATUS_VALUES` 增加 `pending`、`offboarding`（规格 §4.3）。

## D-032 M4 后台扫描任务
- **决策**：进程内 asyncio 周期任务（默认 60s，`SCANNER_INTERVAL_SECONDS`）+ `POST /api/v1/scanner/run` 手动触发；扫描在行锁下重检状态，可安全重试。
- **依据**：规格 §13「预留超期通过定时后台任务扫描」；AGENTS.md 要求幂等。
- **影响**：预留 `active` 且 `expires_at` 过期 → `expired`；已 `consumed`/`cancelled` 不受影响。预警按 fingerprint 幂等。

## D-033 M5 部门数据范围解析
- **决策**：`super_admin`/`hr` 为全量范围；其他角色范围 = `sys_user_departments` 显式授权 ∪ `departments.manager_employee_id` 匹配用户 `employee_id` 的部门及其下级。空范围默认拒绝（看不到任何员工/住宿数据）。
- **依据**：AGENTS.md M5 P0「部门负责人数据范围控制」；规格 §8 ◇ 表示只限授权数据范围。
- **影响**：`GET /users/{id}/departments`（PUT）管理授权；列表过滤与详情 403 均在后端强制。

## D-034 M5 报表统计口径
- **决策**：空闲床位 = `operational_status=active` 且无 active 住宿且无 active 预留；维修/停用不计入可分配；已离职未退宿仍计入在住；台账与导出共用同一查询与范围过滤。
- **依据**：AGENTS.md 第四节报表一致性要求。
- **影响**：`report_service` / `dashboard_service` 为唯一统计来源，前端不自行计算业务状态。

## D-035 角色导出权限
- **决策**：按规格 §8 矩阵，为 `dept_manager` / `finance_viewer` 增加 `report:export`；`dept_manager` 另授 `employee:export` 以便在数据范围内导出本部门员工。
- **依据**：P0「Excel 导出必须遵循相同的数据范围」需覆盖导出路径。
- **影响**：seed 仅追加权限；既有用户重新登录或跑 seed 后生效。

## D-036 Dashboard 指标范围口径（M6 P0-1）
- **决策**：员工关联指标（`housed_employees`、`today_checkin/checkout`、`terminated_still_housed`、`active_alerts`、`pending_todos`、`department_housed`、trends 序列）一律按部门数据范围过滤；宿舍设施容量指标（`bed_total`/`occupied_beds`/`vacant_beds`/`occupancy_rate`/楼栋房间数）保持全局，因空床库存是分床决策所需资源信息，不暴露员工或其他部门人事数据。`department_housed` 在范围过滤后再按在住人数排序并截断，避免授权部门被无条件 `limit(20)` 丢弃。
- **依据**：M6 P0-1「未经授权不得向部门负责人披露其他部门的敏感数据」；设施容量≠部门敏感数据。
- **影响**：空范围用户员工类 KPI 全为 0；`date.today()` 改为 UTC 日历（与 `utcnow` 存储一致）。

## D-037 Dashboard UTC 日历
- **决策**：Dashboard 今日入住/退宿与趋势图使用 UTC 日历日（`utcnow().date()`），与 `DATETIME(6)` UTC 存储一致，不再使用服务器本地 `date.today()`。
- **依据**：D-007 应用层统一 UTC；本地时区会导致「今日」计数与入库时间错位。
- **影响**：跨时区部署时看板按 UTC 日切；业务报表日期筛选仍按查询参数解释。

## D-038 员工导入逐行 SAVEPOINT（DMS-P1-001）
- **决策**：`commit_employee_import` 每行使用 `db.begin_nested()`（SAVEPOINT），单行数据库异常只回滚该行，已成功行与审计在同一外层事务内提交。
- **依据**：任务单要求「部分成功」语义；禁止在循环内 `db.rollback()`（会撤销先前成功行）。
- **影响**：三行导入（好/坏/好）可得到 2 成功 1 失败；`job.summary` 与审计与落库行一致。API 响应字段不变。

## D-039 导入预览/提交动作禁止静默翻转（DMS-P1-002）
- **决策**：commit 阶段若数据库状态相对 preview 漂移（preview=update 目标消失，或 preview=create 目标已存在），该行报 `conflict` 错误，不自动 create↔update。preview=update 且目标仍存在时仍允许批量更新。
- **依据**：任务单要求 preview/commit 意图一致；不得覆盖他方写入，也不得重建已删除人员。
- **影响**：需重新预览后再提交；既有「批量更新」能力保留。

## D-040 预留过期扫描锁顺序（DMS-P1-003）
- **决策**：`_expire_one_reservation` 改为与入住确认一致的锁顺序：员工行 → 床位行（id 升序）→ 预留/住宿业务行；先无锁 peek 取 employee_id/bed_id 仅用于定序。
- **依据**：AGENTS.md §4 / D-021 统一锁顺序；原实现先锁预留再锁床位，与 confirm_checkin 交叉可形成锁等待环。
- **影响**：并发确认入住 vs 扫描在同一预留上按同一顺序取锁；不释放已入住床位的不变量保持。

## D-041 确认入住/完成调宿校验预留到期（DMS-P1-004）
- **决策**：预留 `expires_at is not None and expires_at <= now` 时，`confirm_checkin` / `complete_transfer` 返回 409，不允许普通操作消费已到期预留；`expires_at is None` 表示无有效期。调宿预留接口新增可选 `expires_at`（向后兼容）。
- **依据**：D-032「expires_at 过期 → expired」；任务单要求扫描延迟时在最终事务内显式校验。
- **影响**：需要先重新预留再确认；无过期时间或未到期行为不变。不提供静默管理员越权确认。

## D-042 导入任务并发提交防护（DMS-P2-005）
- **决策**：`commit_employee_import` 读取 ImportJob 时 `FOR UPDATE`，并在同事务内认领状态；并发第二笔提交得到 409。
- **依据**：任务单 P2-005；单实例下行锁足够，避免重复写入与重复审计。
- **影响**：重复/并发 commit 不重复创建员工；响应格式不变。

## D-043 Excel 工作簿 try/finally 关闭（DMS-P2-006）
- **决策**：`preview_employee_import` 将 workbook 解析与校验置于 `try/finally`，所有异常路径（缺表头、空表、超限、坏文件）均 `wb.close()`。
- **依据**：任务单 P2-006；保持 5MB / 2000 行业务限制。
- **影响**：无 API 变化；资源释放可验证。

## D-044 生产 API 文档默认关闭（DMS-P2-007）
- **决策**：`ENABLE_API_DOCS` 默认 `false`；`APP_ENV != production` 仍自动开放文档；production 需显式 `ENABLE_API_DOCS=true`。Compose/README/`.env.example` 同步。
- **依据**：任务单 P2-007（内网非阻断，但配置与文档须一致）。
- **影响**：不影响业务 API；仅控制 `/api/docs`、`/api/openapi.json`。

## D-045 Compose 生产/开发双模式（DMS-P2-008）
- **决策**：保留 `compose.yaml` 的回环 MySQL 映射供开发/测试；新增 `compose.production.yaml`（`ports: !reset []`）供内网正式部署不发布数据库端口。文档说明两种启动方式。
- **依据**：任务单 P2-008；不得修改正在运行容器的数据卷。
- **影响**：宿主机 3306 被占用时生产可启动；备份脚本经 `docker exec` 仍可用。

## D-046 刷新令牌并发与多副本扫描暂缓（DMS-P2-009/010）
- **决策**：本轮不改 `refresh_tokens` 行锁/条件更新，不在多 worker 下做扫描分布式锁；在 DEPLOYMENT.md 明确「公司内网、单 backend 实例」前提与后续条件。
- **依据**：任务单 P2-009/010 标为条件触发/内网暂缓；避免登录机制大改与多实例架构重写。
- **影响**：若未来上公网认证或多副本部署，须单独立项补行锁与任务调度。

## D-047 BUG-007 accommodation_required 后端统一强制（V1.0.1）
- **决策**：`assert_accommodation_required` 放在 `occupancy.py` 统一入口，覆盖申请/预留/确认/调宿/批量导入；前端过滤仅作体验层。
- **依据**：用户 P0 要求“必须由后端统一校验，不得只做前端过滤”。
- **影响**：已入住员工改为不需要住宿时不自动释放床位，须走退宿。

## D-048 BUG-003 根因修复而非屏蔽提示（V1.0.1）
- **决策**：删除 `floor_id=0` 非法请求；消除 `onTreeSelect`+watch 双请求；全局与局部错误改为 `notifyError` 单次通知（可 `skipErrorToast`）。
- **依据**：任务单要求修复实际根因。

## D-049 FEAT-008 门禁密码（access_code）敏感凭据（V1.0.1）
- **决策**：`access_code_encrypted` Fernet（密钥派生自 SECRET_KEY）；字符串保留前导零；列表仅 `has_access_code`；揭示需 `dorm:access_code:view` 且审计。
- **依据**：门禁密码（非 Wi-Fi）按敏感凭据管理；未授权不得经 API/日志/导出获取明文。

## D-050 宿舍资源删除为硬删除+关联阻断（V1.0.1）
- **决策**：无下级且无住宿/预留/调宿关联时硬删除并审计；否则 422 提示改停用（`status=disabled` 作归档）。
- **依据**：AGENTS.md 禁止随意物理删除有历史的资源；用户要求不可删除时提供停用/归档。

## D-051 批量导入逐行部分成功（V1.0.1 房间/分床）
- **决策**：房间导入与批量分床均为逐行部分成功 + 行级原因；分床复用 checkin_service 状态机，失败行尝试取消申请。
- **依据**：任务单“明确采用逐行部分成功或整批回滚”；与 D-038 一致。

## D-052 FEAT-008 门禁密码密钥与 JWT 分离（复核补强）
- **决策**：`ACCESS_CODE_ENCRYPTION_KEY` 为门禁密码主 Fernet 密钥，与 `SECRET_KEY`（JWT）分离；`ACCESS_CODE_LEGACY_SECRETS` 仅用于解密旧密文；密文 `v2:` 前缀；`POST /rooms/access-code/rotate` 批量重加密且不落明文。
- **依据**：GPT Web 复核要求密钥分离与安全轮换，不得因换钥导致既有门禁密码无法解密。
- **影响**：未配置专用钥时回退 SECRET_KEY 派生（兼容）；生产应配置独立钥并在轮换后执行 rotate。

## D-053 批量分床失败恢复三级策略（复核补强）
- **决策**：行前 rollback → `cancel_application` → 强制释放残留 active 预留；行级结果含 `recovery` 字段；策略 `partial_success_per_row`。
- **依据**：UX-004 要求失败行不得遗留无效预留/不可追溯状态。
- **影响**：汇总含 `recovered`；恢复动作写审计 `checkin.batch_allocate_import.recovery`。

## D-054 门禁密码全局轮换权限收紧（最终安全复核）
- **决策**：新增 `dorm:access_code:rotate` 与角色 `secrets_ops`；`POST /rooms/access-code/rotate` 仅 super_admin / secrets_ops；dorm_admin 保留单房 `view/update` 但不可全局轮换。
- **依据**：GPT Web 第二轮要求全局轮换仅超管或独立运维角色，普通宿管/财务/人事/部门负责人不得调用。
- **影响**：需在生产显式授予 `secrets_ops`；升级后执行 `python -m app.seed` 刷新 RBAC。

## D-055 取消 HOTFIX-07B 历史数据修复（用户决定）
- **决策**：现有库为开发测试数据；取消 C1/C5 批量修复；生产全新空库部署；保留 HOTFIX-07A 与全部测试。
- **依据**：用户最终确认测试数据不进入生产。
- **影响**：HOTFIX-07B 标记为「范围取消」；调宿锁序风险保留至正式验收前专项测试。

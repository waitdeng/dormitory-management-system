# DMS V1.0 代码审查与 MiMo 修复任务总单

> 审查对象：GitHub `waitdeng/dormitory-management-system`，`main` 分支；审查日期：2026-10-14。  
> 适用场景：公司内网单实例部署，员工与宿舍资料属于业务数据。  
> 审查方式：GitHub 连接器只读检查源代码及 M6 验收文档；**没有**在用户的真实 MySQL、Docker、浏览器中运行测试，未完整逐行覆盖仓库全部文件。  
> 本文的“已确认”表示代码行为确定，**不意味着已在运行环境复现故障**。修复前以本地最新代码为准，逐项验证。  
> 所有变更必须保持现有业务规则和 API 兼容；严禁自动重置生产数据库、覆盖真实人员数据、执行破坏性迁移或提交真实 `.env`。

## 0. 审查结论与交付范围

目前最值得处理的是员工 Excel 导入的异常隔离、预览/提交一致性、预留扫描与入住并发，以及预留有效期校验；其次是配置和说明文件不一致的问题。已见到入住、调宿和退宿使用 SQLAlchemy 事务及 MySQL 行锁，不应无证据地推翻现有实现。M6 报告声称 81 项 pytest、4 项 Vitest、6 项 Playwright 通过，这些是**原项目报告记录**，本轮未独立复验。

### 证据等级
- **A（源码确认）**：代码路径和具体行为已读到；是否发生用户可见故障另行说明。
- **B（待复现风险）**：根据实际源码推断的并发/数据风险；先写测试触发，复现后再选择最小改动。
- **C（工程建议）**：不代表已存在 Bug，可视实际部署决定是否采纳。

## 1. 必须优先处理

### DMS-P1-001 — 员工批量提交发生数据库异常后缺少单行事务隔离

- **等级**：P1；**证据**：A（异常处理模式已确认），运行时后果待测试。
- **位置**：`backend/app/services/employee_service.py`，`commit_employee_import()`，约 L806–965，尤其 L886–925、L963。
- **证据**：逐行循环执行 `db.add()` / `await db.flush()`，使用 `except Exception` 收集错误后继续下一行，末尾统一 `await db.commit()`；没有逐行 SAVEPOINT 或数据库错误后的完整事务恢复。
- **风险**：某行出现 `IntegrityError` 等数据库错误时，SQLAlchemy 当前事务可能进入 failed/pending rollback 状态，后续行和最终提交无法可靠继续；此前统计的“成功行数”也可能无法落库。
- **要求**：先构造真实 MySQL 唯一约束或其他 flush 异常的可复现测试；若确定要求“部分成功”，为每行使用 `begin_nested()` SAVEPOINT，并确保在嵌套事务退出后再查询/统计；审计日志应和成功行保持同一事务一致性。不要简单地在循环内调用 `db.rollback()`（会撤销前面成功行）。如果业务改为“全有或全无”，需显式变更验收标准，不可悄悄改变现有产品语义。
- **验收**：有效行、故障行、有效行三行导入：2 行成功、1 行错误；数据库数据、job.summary、success_rows、failed_rows 和审计一致；重复提交不会重复创建。

### DMS-P1-002 — 导入预览为“新增”时，提交阶段可能静默变成“覆盖更新”

- **等级**：P1；**证据**：A。
- **位置**：`backend/app/services/employee_service.py`，约 L865–877。
- **证据**：`if action == "create" and existing is not None: action = "update"`，反向还会把 `update` 改为 `create`。员工资料在 preview 与 commit 之间变化时，最终操作类型不等于用户确认时的操作。
- **风险**：操作员确认新增的员工，有可能在另一个操作/导入已经写入该工号后，被当前提交悄悄修改姓名、部门、电话等字段；反向转换则可能创建本该更新的人员。
- **要求**：preview/commit 的意图保持一致。发现数据库状态漂移时，默认按行报 `conflict`、不给予静默转换；可选择“要求重新预览”或增加显式、可审计的覆盖策略。必须确认现有业务是否允许批量更新，不能无条件改成纯新增。
- **验收**：预览后另一会话插入同工号，提交不能覆盖对方；预览 update 后目标被删除，不得自动重新创建；提示可定位工号和行号。

### DMS-P1-003 — 预留过期扫描与入住/调宿操作锁顺序不一致，存在死锁/等待风险

- **等级**：P1；**证据**：B。
- **位置**：`backend/app/services/scanner_service.py`，`_expire_one_reservation()` 约 L75–121；`backend/app/services/checkin_service.py`，`confirm_checkin()` 约 L445–476；`backend/app/services/occupancy.py`，`lock_employee()` 和 `lock_beds()`。
- **证据**：扫描先 `BedReservation.with_for_update()`，再获取床位锁；入住确认先锁 Employee、Bed，再锁 `BedReservation`。相同记录并发操作可能形成交叉等待。扫描内部 `_expire_one_reservation()` 会 commit；行为必须结合事务边界分析。
- **要求**：优先在真实 MySQL 中编写“确认入住与同一预留到期扫描并发”的阻塞/死锁回归测试；若复现，调整为统一锁顺序（员工→床位→预留/业务记录，按照现有设计规范）或使用合适的 `SKIP LOCKED`/独立事务与死锁重试。注意已持有的锁与 SQLAlchemy 隐式 flush，避免修复引入新的锁逆序。保留“不会释放已入住床位”的业务不变量。
- **验收**：高并发重复运行无永久阻塞；允许可控重试；最终每张床只存在合法状态，成功入住不被扫描撤销，预留、入住、待办、审计一致。

### DMS-P1-004 — 确认入住/调宿前应复查预留时间有效性

- **等级**：P1；**证据**：B（业务契约需核实）。
- **位置**：`backend/app/services/checkin_service.py`，`confirm_checkin()` 约 L464–476；`backend/app/services/transfer_service.py`，`complete_transfer()` 约 L353–367。
- **证据**：读取活跃预留并检查 `res.status == "active"`；在本轮阅读的上述路径中，未见同时判断 `expires_at <= utcnow()`。如果定时扫描有延迟，数据库中可能保留“已超时但状态仍 active”的预留。
- **要求**：核对需求文档对 `expires_at` 的语义。如果到期即失效，在最终事务锁内显式检查到期时间，返回业务冲突；保证前端可提示刷新。若允许管理员逾期确认，必须有明确权限/操作记录和测试。
- **验收**：时间已过而扫描尚未运行的预留不能被普通确认入住/调宿完成消费；临界时刻和无过期时间均有测试。

## 2. 第二优先级：业务健壮性与部署

### DMS-P2-005 — 导入任务的并发提交缺少显式锁/幂等保护确认

- **证据**：B；**位置**：`backend/app/services/employee_service.py`，L806–840。
- **观察**：读取 `ImportJob` 时未见 `with_for_update()`，仅检查状态为 `previewed`/`failed`；两个并发提交可能都通过状态检查。必须先看数据库约束与任务生命周期实际表现。
- **要求**：并发 commit 同一 import_job 的集成测试，必要时任务行加锁/原子状态迁移，重复请求返回确定冲突或既有结果；导入明细和审计不得重复。

### DMS-P2-006 — Excel 工作簿导入过程的资源释放与非法文件处理

- **证据**：A（正常路径 `wb.close()` 已有）；问题触发待验证。
- **位置**：`backend/app/services/employee_service.py`，`preview_employee_import()` L615–795。
- **观察**：`load_workbook(..., read_only=True)` 后进入多个可能 `raise ValidationError` 的分支，`wb.close()` 位于末尾；异常路径未见 `finally` 包裹。超出行数限制、缺少表头等可提前退出。
- **要求**：将 workbook 生命周期置于 `try/finally`，确保所有路径关闭；用畸形、表头缺失、超限工作簿压测资源释放。保持 5MB / 2000 行业务限制。

### DMS-P2-007 — API 文档在 production 下默认仍可能启用

- **证据**：A；**位置**：`backend/app/core/config.py` 与 `backend/app/main.py`。
- **观察**：`ENABLE_API_DOCS` 默认 `True`；`expose_docs = settings.ENABLE_API_DOCS or settings.APP_ENV != "production"`。即使 Compose 默认 `APP_ENV=production`，未传入 `ENABLE_API_DOCS=false` 时仍公开 `/api/docs`。
- **要求**：由于本项目仅用于公司内网，此项非阻断：可以将默认改为生产禁用，开发默认可用，或仅在部署 `.env` 显式标记。统一配置、README 和 M6 报告中的说法；不得影响 API 调用。

### DMS-P2-008 — Docker 数据库端口冲突与不必要映射

- **证据**：A；**位置**：根目录 `compose.yaml`。
- **观察**：MySQL 端口 `127.0.0.1:${MYSQL_HOST_PORT:-3306}:3306`，已有其他本机 MySQL 时可能冲突。仅后端容器访问数据库时，不需要将端口发布到宿主机。
- **要求**：开发/集成测试保留可选回环映射；内网正式部署提供无需 ports 的配置或 profile/override，文档说明两种模式；**不要直接修改正在运行容器的数据卷或删除数据库**。
- **验收**：已有宿主机 3306 占用时正式部署仍可启动；后端通过 Compose 网络连接 MySQL；备份/迁移脚本适配。

### DMS-P2-009 — Refresh Token 旋转并发保护（内网暂缓）

- **证据**：A（无行锁）；**位置**：`backend/app/services/auth_service.py`，`refresh_tokens()`。
- **说明**：读取 token 后更新 revoked_at，没有原子单次消费约束；两请求并发时可能成功签发两个新令牌。本项目当前不对公网，此项不作为本轮业务上线阻断。后续进行认证重构时，使用行锁或条件更新并补测试。

### DMS-P2-010 — 多副本部署的扫描任务重入（条件触发）

- **证据**：A；**位置**：`backend/app/tasks/scanner.py`，`backend/app/main.py`。
- **说明**：扫描任务在每个 FastAPI 进程 lifespan 内启动。V1 单实例部署可维持原状；如以后多 worker、多 backend 副本才需要独立任务调度/分布式锁。
- **验收**：本轮不用为未采用的集群架构重写调度；文档明确单实例前提。

### DMS-P3-011 — README 里程碑状态过时

- **证据**：A；**位置**：根目录 `README.md`。
- **观察**：README 中 M2–M6 仍为“待开始”，而 `docs/IMPLEMENTATION_PLAN.md` 和 `docs/M6_ACCEPTANCE_REPORT.md` 表示已完成。
- **要求**：对齐 M6 验收现状，并说明哪些测试是报告结果、哪些是在本地实际重跑验证；不要把历史报告冒充本轮执行记录。

## 3. 必须回归审查但不预判存在 Bug 的模块

1. **入住事务**：`checkin_service.py`：一人多床、一床多人、预留过期、重复确认、预留取消/重选、锁顺序，所有合法幂等路径。
2. **调宿事务**：`transfer_service.py`：源床释放与目标占用必须同一事务；与退宿并发互斥；重复完成只生成一条目标入住记录。
3. **退宿及离职**：`checkout_service.py`、员工状态联动：退宿待办、预警、历史台账、床位释放一致；不会因离职直接错误释放仍占用床。
4. **报表/看板**：`report_service.py`、`dashboard_service.py`：人数与床位数口径、部门权限、空床数、历史时间边界、无权限人员数据泄露。M6 已明确设施容量指标可以全局显示，不要自行将其改成部门私有。
5. **备份恢复**：`scripts/backup.sh`、`restore.sh`：在隔离数据库验证，禁止覆盖现有 `dms` 生产库；确认恢复后的外键/唯一约束、迁移版本和业务数据数目一致。
6. **前端**：`frontend/src/api/client.ts`、入住/调宿/退宿页面：409 冲突提示、重复点击防护、认证过期后刷新一次、列表与看板刷新、表单失败不显示成功。`localStorage` 存 token 属内网部署可接受的风险取舍，不应在本轮强行重构。

## 4. MiMo 新任务窗口：可直接粘贴的启动指令

> 你现在接手本地 `dormitory-management-system` 项目的一次**缺陷修复和回归验证**，不是新功能开发。首先阅读项目根目录 `AGENTS.md`、开发规格文档、`docs/IMPLEMENTATION_PLAN.md`、`docs/M6_ACCEPTANCE_REPORT.md` 和本文件 `DMS_V1_CODE_REVIEW_AND_MIMO_FIX_TASK.md`。这些文件冲突时，以用户当前最新明确约束为先；不得擅自改变已经确认的业务口径。
>
> 部署场景为**公司内网、单 backend 实例**。本次优先保证宿舍/员工业务数据正确、事务原子性、Excel 导入可靠性和前端回归；**不做登录机制大改、不做公网安全体系、不做多实例架构重写**。
>
> 请按 `DMS-P1-001` 至 `DMS-P1-004` 先逐一定位代码、编写失败复现测试、给出根因、最小化修复并回归。对标为 B 的风险，若无法复现，必须给出测试设计和结果，不得直接声称已存在故障；如果测试证明无需修改，记录“不修改”的技术依据。然后完成 `DMS-P2-005` 至 `DMS-P3-011` 的可执行改动（对条件触发项仅补部署说明即可）。
>
> 在每个业务修改中维持 API 请求/响应格式、既有状态机、MySQL 约束、审计日志、部门数据范围和原有历史记录。不得重置数据库、删除卷、覆盖正式数据、在 README 中虚报测试通过。数据库测试应使用隔离测试库并自动清理测试数据。
>
> 完成后执行：后端 pytest（包含真实 MySQL 并发/异常测试）；前端 `npm run typecheck`、`npm test`、`npm run build`，能运行时再执行 Playwright E2E；Docker Compose 配置校验及必要的隔离备份/恢复测试。提供每条命令的真实运行结果，如环境不满足则明确列为未验证。
>
> 交付 `docs/DMS_CODE_REVIEW_FIX_REPORT.md`：逐条列出问题 ID、修复状态、触发场景、根因、修改文件、关键实现、测试名称与结果、风险及未完成项。同步更新 README/必要文档。**修复前不要自动推送到 GitHub；由用户确认后再提交。**

## 5. 验收检查表

- [ ] DMS-P1-001：数据库级单行失败后可按设计部分成功，汇总与审计准确。
- [ ] DMS-P1-002：预览新增/更新与提交动作一致，无静默覆盖。
- [ ] DMS-P1-003：扫描与入住并发无死锁/永久等待，数据不变量保持。
- [ ] DMS-P1-004：到期预留不能未经授权确认，规则和测试一致。
- [ ] DMS-P2-005：相同导入任务并发提交安全。
- [ ] DMS-P2-006：异常 Excel 解析所有路径释放资源。
- [ ] DMS-P2-007～011：适用项修复，其余说明为何暂缓。
- [ ] 入住、调宿、退宿、离职全生命周期集成测试通过。
- [ ] 部门数据范围及全部报表/导出回归通过。
- [ ] 现有 MySQL 数据卷、真实员工数据未发生破坏性变更。
- [ ] 完成最终修复报告，所有测试结果可追溯，未验证项明确列出。

## 6. 本轮源代码核对位置

- `backend/app/services/employee_service.py`：预览 L615–795；提交 L806–965。
- `backend/app/services/checkin_service.py`：床位预留 L354–434；确认入住 L438–542。
- `backend/app/services/transfer_service.py`：完成调宿 L318–437。
- `backend/app/services/checkout_service.py`：退宿相关事务与锁。
- `backend/app/services/scanner_service.py`：过期扫描 L35–155。
- `backend/app/services/occupancy.py`：行锁辅助 L38–68。
- `backend/app/services/auth_service.py`：刷新/撤销令牌。
- `backend/app/main.py`、`backend/app/core/config.py`、`compose.yaml`。
- `frontend/src/api/client.ts`、`frontend/src/stores/auth.ts`、`frontend/src/router/index.ts`。
- `README.md`、`docs/IMPLEMENTATION_PLAN.md`、`docs/M6_ACCEPTANCE_REPORT.md`。

> 说明：这是**有范围限定的只读审查**的合并修复清单，并非证明全部仓库代码无遗漏的全量审计，也不是已执行的自动化测试报告。MiMo 修复过程应继续审查受影响调用链与测试代码，发现额外缺陷应追加编号并说明依据。

# 项目上下文（PROJECT_CONTEXT）

> 本文件说明 DMS 的业务背景、技术边界与当前状态，供 AI 代理建立统一上下文。  
> 路径均相对于项目根目录。业务细节以 `DMS_V1.0_MiMo_Development_Spec.md` 为准。

## 1. 项目概述

- **项目名称**：公司宿舍入住管理系统（DMS，Dormitory Management System）
- **版本**：V1.0
- **业务目标**：企业内部行政、人事使用的可私有化部署宿舍管理 Web 平台。
- **主链路**：员工 → 宿舍资源 → 预留/入住 → 调宿 → 退宿 → 离职联动 → 台账/报表。
- **使用对象**：行政、人事等内部管理人员（非员工自助产品）。

## 2. 业务边界（V1.0）

### 必做（详见规格文档）

- 部门与员工档案：增改查、Excel 导入（校验/预览/提交/错误报告）、导出、住宿历史关联。
- 宿舍资源：区域、楼栋、楼层、房间、床位层级与可用性管理。
- 入住：申请、批准、预留、确认、取消与历史记录。
- 调宿：目标预留、原位释放、新旧记录关联与历史追溯。
- 退宿：申请、检查、确认、释放床位、历史追溯。
- 离职联动：生成行政退宿待办及异常预警，**离职本身不自动释放床位**。
- 住宿台账、空床/入住率/部门/入退宿/异常统计、Excel 导出。
- 可视化床位分配：楼栋楼层导航、房间/床位状态、冲突处理。
- 登录、RBAC 与数据范围、审计记录、Docker Compose 部署、必要测试。

### 明确不做（V1.0）

住宿费、水电费、押金、薪资代扣、宿舍资产、维修工单、巡检、员工自助小程序、企业微信推送、外部 HR/ERP 集成。可预留接口边界，不得因此增加未经批准的复杂依赖。

## 3. 技术栈与架构

| 层 | 选型 |
|---|---|
| 前端 | Vue 3 + TypeScript + Vite + Element Plus + Pinia + Vue Router；图表 ECharts |
| 后端 | Python FastAPI + Pydantic v2 + SQLAlchemy 2.x（异步）+ asyncmy |
| 数据库 | MySQL 8.0（InnoDB、utf8mb4），Alembic 迁移 |
| Excel | openpyxl |
| 部署 | Docker Compose + Nginx；Redis 仅可选，不得作为唯一业务状态源 |
| 测试 | pytest/httpx；前端 Vitest；Playwright；并发占床集成测试 |
| 架构 | 模块化单体、前后端分离；API → Service → Repository → Model |

- API 前缀：`/api/v1`
- 部署形态：公司内网、单 backend 实例（见 `docs/DEPLOYMENT.md`）

## 4. 当前阶段状态（保持，不重置）

| 里程碑 | 状态 | 证据 |
|---|---|---|
| M1 项目骨架与认证 | 已完成（2026-10-13） | `docs/M1_ACCEPTANCE_REPORT.md` |
| M2 基础数据 | 已完成（2026-10-13） | `docs/M2_ACCEPTANCE_REPORT.md` |
| M3 住宿事务闭环 | 已完成（2026-10-13） | `docs/M3_ACCEPTANCE_REPORT.md` |
| M4 离职联动与预警 | 已完成（2026-10-13） | `docs/M4_ACCEPTANCE_REPORT.md` |
| M5 可视化与报表 | 已完成（2026-10-13） | `docs/M5_ACCEPTANCE_REPORT.md` |
| M6 联调/迁移/上线验证 | 已完成（2026-10-14） | `docs/M6_ACCEPTANCE_REPORT.md` |
| 代码审查修复 | 已处理 | `docs/DMS_CODE_REVIEW_FIX_REPORT.md` |

**禁止**将 M1～M6 重置为待开发，**禁止**删除已有验收报告。未读取验收报告前不得断言“已测试通过”；区分“文档计划完成”与“代码已实现/已验证”。

## 5. 权威文档入口

| 主题 | 路径 |
|---|---|
| 代理协作总则与规则优先级 | `AGENTS.md` |
| 业务开发规格（项目专属权威） | `DMS_V1.0_MiMo_Development_Spec.md` |
| 通用开发规则（AI-SDLC） | `.ai/DEVELOPMENT_RULES.md` |
| 里程碑与阶段状态 | `.ai/MILESTONES.md`（详情在 `docs/IMPLEMENTATION_PLAN.md`） |
| 决策记录 | `.ai/DECISIONS.md` → `docs/DECISIONS.md` |
| 阶段验收报告 | `docs/M1_ACCEPTANCE_REPORT.md` … `docs/M6_ACCEPTANCE_REPORT.md` |
| 部署 / 备份 / 发布 | `docs/DEPLOYMENT.md`、`docs/BACKUP_RESTORE.md`、`docs/RELEASE_CHECKLIST.md` |
| 用户手册 | `docs/USER_MANUAL.md` |
| 阶段指令模板 | `.ai/prompts/` |
| 验收 / 缺陷模板 | `.ai/acceptance/` |
| 最终验收模板 | `.ai/audit/FINAL_WORK_ACCEPTANCE.md` |

## 6. 核心业务不变量（摘要）

完整定义见 `AGENTS.md` §4 与 `DMS_V1.0_MiMo_Development_Spec.md`：

1. 同一员工同一时刻最多一条 active 住宿记录。
2. 同一床位同一时刻最多一条 active 住宿记录。
3. 预留与住宿记录之间不得跨表冲突。
4. 停用/维修/上级不可分配时禁止新增分配。
5. 离职产生退宿待办，**不直接移除当前住宿**。
6. 调宿/退宿保留历史，不覆写删除。
7. 人数/空床/住宿状态由权威业务记录推导。
8. 并发分配在数据库事务中校验（锁顺序：员工行 → bed_id 升序床位行 → 住宿/预留/业务单据）。
9. 重复提交/完成/离职事件须幂等或防重。
10. 关键操作写审计日志（执行人、对象、时间、结果）。

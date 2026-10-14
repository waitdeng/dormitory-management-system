# AI-SDLC v1.0 规范接入迁移报告（DMS）

- **项目**：公司宿舍入住管理系统（DMS）V1.0
- **迁移日期**：2026-10-14
- **迁移性质**：文档规范迁移（非功能开发）
- **执行代理**：MiMo Desktop / MiMo
- **工作区**：`/Users/easonli/XiaomiMiMoProjects/dormitory-management-system`
- **Git**：仓库无既有提交（`master` 尚无 commit）；本任务**未**执行任何 Git commit / push
- **结论**：规范合并完成，M1～M6 状态保持，未修改业务代码；存在一项需人工知悉的源包文件覆盖事项（见 §5.5、§9）

---

## 1. 原有规范文件清单

### 1.1 项目根目录（迁移前已存在）

| 路径 | 作用 |
|---|---|
| `AGENTS.md` | AI 代理协作总则、业务不变量、阶段进入条件、验证规则 |
| `DMS_V1.0_MiMo_Development_Spec.md` | 项目业务/技术开发规格（项目专属权威） |
| `README.md` | 项目说明、快速开始、测试、备份、里程碑表 |
| `DMS_V1_CODE_REVIEW_AND_MIMO_FIX_TASK.md` | 代码审查修复任务单 |
| `compose.yaml` / `compose.production.yaml` | 部署编排 |
| `.env.example` | 环境变量模板 |
| `.gitignore` | Git 忽略规则 |

### 1.2 `docs/`（迁移前已存在，本次**未移动、未删除、未改写**）

| 路径 | 作用 |
|---|---|
| `docs/IMPLEMENTATION_PLAN.md` | 阶段计划与任务拆解 |
| `docs/DECISIONS.md` | 技术/业务决策 D-001 … D-046 |
| `docs/M1_ACCEPTANCE_REPORT.md` … `docs/M6_ACCEPTANCE_REPORT.md` | 阶段验收报告 |
| `docs/DMS_CODE_REVIEW_FIX_REPORT.md` | 代码审查修复报告 |
| `docs/DEPLOYMENT.md` | 部署说明 |
| `docs/BACKUP_RESTORE.md` | 备份恢复 |
| `docs/RELEASE_CHECKLIST.md` | 发布检查清单 |
| `docs/USER_MANUAL.md` | 用户手册 |

### 1.3 AI-SDLC 规范包（迁移输入）

实际路径：`.ai/migration/AI-SDLC-v1.0/`（目录名大小写为 `AI-SDLC-v1.0`，任务描述中写作 `ai-sdlc-v1.0`，以磁盘为准）。

| 迁移包路径 | 作用（按包内定位） |
|---|---|
| `AGENTS.md` | 代理入口样例 |
| `README.md` | 规范包说明 |
| `.ai/PROJECT_CONTEXT.md` | 项目上下文模板 |
| `.ai/DEVELOPMENT_RULES.md` | 通用开发规则 |
| `.ai/MILESTONES.md` | 里程碑约定 |
| `.ai/DECISIONS.md` | 决策记录约定 |
| `.ai/prompts/M01_START.md` | 阶段启动指令模板 |
| `.ai/templates/ACCEPTANCE_TEMPLATE.md` | 阶段验收模板 |
| `.ai/templates/BUG_TEMPLATE.md` | 缺陷条目模板 |
| `.ai/audit/FINAL_WORK_ACCEPTANCE.md` | ChatGPT Mac Work 最终验收模板 |
| `.gitignore.sample` | 忽略规则样例 |

---

## 2. 新增规范文件清单

在项目根建立/完善：

| 路径 | 作用 | 来源 |
|---|---|---|
| `.ai/PROJECT_CONTEXT.md` | DMS 业务边界、技术栈、M1～M6 状态、文档入口 | 项目文档 + 规范包结构 |
| `.ai/DEVELOPMENT_RULES.md` | 通用开发规则**权威定义** | AI-SDLC 通用规则合并 |
| `.ai/MILESTONES.md` | 里程碑状态（保持已完成）+ 状态标记规则 | 项目验收 + 规范包约定 |
| `.ai/DECISIONS.md` | 规范/流程决策索引 + 迁移决策；技术决策正文仍在 `docs/DECISIONS.md` | 合并 |
| `.ai/README.md` | `.ai/` 目录导航 | 新增 |
| `.ai/prompts/STAGE_START_TEMPLATE.md` | 阶段指令详细模板 | 基于规范包工作流补充 |
| `.ai/prompts/M01_START.md` | 阶段启动简版清单 | 规范包 |
| `.ai/acceptance/ACCEPTANCE_TEMPLATE.md` | 阶段验收模板 | 规范包 templates |
| `.ai/acceptance/BUG_TEMPLATE.md` | 缺陷模板 | 规范包 templates |
| `.ai/audit/FINAL_WORK_ACCEPTANCE.md` | 最终验收模板 | 规范包 audit |
| `AGENTS.md`（修改） | 规则优先级、文档导航、AI-SDLC 流程；保留项目约束 | 合并重写 |
| `AI_SDLC_MIGRATION_REPORT.md` | 本报告 | 新增 |

`docs/` 原有结构保持不变。

---

## 3. 修改和合并的规范

### 3.1 合并原则落实

| 原则 | 落实方式 |
|---|---|
| AI-SDLC 提供通用规则 | 写入 `.ai/DEVELOPMENT_RULES.md`（唯一权威） |
| DMS 保留项目专属业务要求 | 保留在 `AGENTS.md` 与 `DMS_V1.0_MiMo_Development_Spec.md` |
| 冲突不覆盖不删除 | 见 §5；记录于 `.ai/DECISIONS.md` |
| 不重置 M1～M6 | `.ai/MILESTONES.md` / `PROJECT_CONTEXT.md` 保持「已完成」 |
| 不删除验收报告 | `docs/M*_ACCEPTANCE_REPORT.md` 原样保留 |
| 通用规则一份权威 | 细则在 `.ai/DEVELOPMENT_RULES.md`，其余路径引用 |
| AGENTS.md 简洁 | 重写为：优先级 → 文档导航 → 工作流 → 项目硬约束 |
| 相对项目根路径 | 全部规范内链接使用相对路径 |
| 不编造测试/提交 | 报告与 `.ai/` 中明确「未测试」标注规则 |

### 3.2 `AGENTS.md` 变更要点

**新增：**

- §0 规则优先级与冲突处理
- §1 文档导航表（含 `.ai/*`）
- §2 AI-SDLC 开发工作流（GPT Web → MiMo → 自检 → 复核 → GitHub 提交）
- 明确自检 ≠ GPT Web 独立验收；Playwright 真测要求

**保留（项目专属，实质未删）：**

- 每次开启任务七步
- V1.0 边界与禁止扩展
- 技术栈与架构约束
- 目录与改动规范
- 业务不变量 1～10 与事务锁顺序
- 数据库迁移安全
- 安全与隐私
- 阶段边界表（并标注 M1～M6 已完成）
- 验证命令与关键路径测试清单
- 文档维护与新任务启动指令

**调整：**

- 通用重复细则改为引用 `.ai/DEVELOPMENT_RULES.md`
- 阶段表旁注明以验收报告为准，禁止重置
- 增加 Playwright、typecheck 等验证命令（与 README 已有测试方式一致）

### 3.3 决策文档分工

- `docs/DECISIONS.md`：技术/业务决策正文（D-001…），**权威，继续追加**
- `.ai/DECISIONS.md`：索引 + 文档迁移/流程类决策（AI-SDLC-Dxxx），避免两份全文

---

## 4. 原有项目特有规则的保留情况

| 类别 | 保留位置 | 状态 |
|---|---|---|
| 业务不变量 10 条 + 锁顺序 | `AGENTS.md` §7 | 保留 |
| V1.0 必做/禁做边界 | `AGENTS.md` §4、`.ai/PROJECT_CONTEXT.md` | 保留 |
| M2 专项执行顺序 | `AGENTS.md` §10（标注为历史参考） | 保留 |
| 迁移/备份/禁止清库 | `AGENTS.md` §8 | 保留 |
| RBAC/401/403/脱敏/公式注入 | `AGENTS.md` §9 | 保留 |
| D-001…D-046 技术决策 | `docs/DECISIONS.md` | 原样未改 |
| M1～M6 验收结论与证据 | `docs/M*_ACCEPTANCE_REPORT.md` | 原样未改 |
| 部署/备份/发布/手册 | `docs/*` | 原样未改 |
| 工号匹配、两阶段导入、审计等 | 规格 + AGENTS + 决策 | 保留 |

---

## 5. 发现的规则冲突和处理建议

### 5.1 流程冲突：阶段验收方

- **现象**：原 AGENTS.md 以「阶段验收报告 + 用户确认」为主；AI-SDLC 增加「GPT Web 复核 + ChatGPT Mac Work 最终验收」。
- **处理**：并存。自检写阶段验收报告；GPT Web 复核为独立验收；最终 UX/E2E 由 ChatGPT Mac Work 在隔离环境执行。自检结论不得写成最终验收结论。
- **建议**：后续阶段报告增加「GPT Web 复核结果」小节，避免与自检混淆。

### 5.2 文档目录：验收模板位置

- **现象**：AI-SDLC 使用 `.ai/acceptance/`；项目验收报告在 `docs/M*_ACCEPTANCE_REPORT.md`。
- **处理**：`.ai/acceptance/` 只放模板；**不移动**已有报告。新阶段可复制模板后仍输出到 `docs/`（与现有命名一致）。
- **建议**：保持 `docs/M*_ACCEPTANCE_REPORT.md` 命名，便于引用连续性。

### 5.3 决策记录双入口

- **现象**：规范包要求 `.ai/DECISIONS.md`，项目已有 `docs/DECISIONS.md`（大量实质决策）。
- **处理**：`.ai/DECISIONS.md` 作索引与迁移决策；技术决策仍写 `docs/DECISIONS.md`。
- **建议**：不要把 D-xxx 正文复制到 `.ai/`，以免出现两份权威。

### 5.4 Git 仓库尚无提交

- **现象**：`master` 无任何 commit，业务与文档均为 untracked。
- **处理**：本任务按禁令**未**自动 commit。
- **建议**：由用户/复核方确认后，可先建立基线提交（例如「M1–M6 代码与文档基线」），再单独提交本次规范迁移，便于回溯。

### 5.5 迁移包源文件被覆盖（过程事故，须知悉）

- **现象**：会话处理中误用写入操作覆盖了 `.ai/migration/AI-SDLC-v1.0/` 下部分**源包**文件，无法从 Git 恢复（仓库无历史）：
  - `AGENTS.md`
  - `README.md`
  - `.ai/PROJECT_CONTEXT.md`
  - `.ai/DEVELOPMENT_RULES.md`
  - `.ai/MILESTONES.md`
  - `.ai/DECISIONS.md`
  - `.ai/prompts/M01_START.md`
- **未改动（保持原字节）**：
  - `.ai/templates/ACCEPTANCE_TEMPLATE.md`
  - `.ai/templates/BUG_TEMPLATE.md`
  - `.ai/audit/FINAL_WORK_ACCEPTANCE.md`
  - `.gitignore.sample`
- **处理**：以任务书要求 + 项目已核实文档 + 保持原样的模板/audit 文件为依据，重建上述源文件，并落地项目根 `.ai/` 合并结果。**不声称**已与 AI-SDLC 官方原文逐字比对。
- **建议**：
  1. 若你有 AI-SDLC v1.0 规范包原件，请覆盖回 `.ai/migration/AI-SDLC-v1.0/` 后做一次 diff 复核；
  2. GPT Web 复核时重点审阅 `.ai/DEVELOPMENT_RULES.md`、`AGENTS.md` §0–§2 是否符合官方 v1.0 条文；
  3. 可将规范包原件只读归档到仓库外或单独分支，避免再次被写入。

### 5.6 轻微表述差异

- **现象**：README 里程碑日期为 2026-10-13/14；部分文件 mtime 显示同日。以验收报告正文为准。
- **处理**：`.ai/MILESTONES.md` 完成日期与 `docs/IMPLEMENTATION_PLAN.md` 一致（2026-10-13 / 2026-10-14）。
- **建议**：无功能影响。

---

## 6. 所有修改文件及修改目的

### 6.1 新增

| 文件 | 目的 |
|---|---|
| `.ai/PROJECT_CONTEXT.md` | 项目上下文与阶段状态 |
| `.ai/DEVELOPMENT_RULES.md` | 通用规则权威定义 |
| `.ai/MILESTONES.md` | 里程碑保持与状态规则 |
| `.ai/DECISIONS.md` | 迁移决策与索引 |
| `.ai/README.md` | `.ai/` 导航 |
| `.ai/prompts/STAGE_START_TEMPLATE.md` | 阶段指令模板 |
| `.ai/prompts/M01_START.md` | 简版启动清单 |
| `.ai/acceptance/ACCEPTANCE_TEMPLATE.md` | 验收模板 |
| `.ai/acceptance/BUG_TEMPLATE.md` | 缺陷模板 |
| `.ai/audit/FINAL_WORK_ACCEPTANCE.md` | 最终验收模板 |
| `AI_SDLC_MIGRATION_REPORT.md` | 本迁移报告 |

### 6.2 修改

| 文件 | 目的 |
|---|---|
| `AGENTS.md` | 增加 AI-SDLC 优先级/导航/工作流；压缩重复；保留项目硬约束 |

### 6.3 有意修改但非交付物（过程事故，见 §5.5）

| 文件 | 说明 |
|---|---|
| `.ai/migration/AI-SDLC-v1.0/AGENTS.md` 等 7 个源文件 | 被重建/覆盖；模板与 audit 未改 |

### 6.4 明确未修改

- `backend/`、`frontend/` 全部业务代码
- Alembic 迁移与数据库模型
- `compose.yaml`、`compose.production.yaml`、`.env`、`.env.example`
- `docs/` 下全部既有文档
- `scripts/`、`deploy/`
- 未执行 Docker 启停/重建/数据清理
- 未执行 Git commit / push

---

## 7. M1～M6 状态保持情况

| 阶段 | 迁移前 | 迁移后 | 证据路径 |
|---|---|---|---|
| M1 | 已完成（2026-10-13） | **已完成（保持）** | `docs/M1_ACCEPTANCE_REPORT.md` |
| M2 | 已完成（2026-10-13） | **已完成（保持）** | `docs/M2_ACCEPTANCE_REPORT.md` |
| M3 | 已完成（2026-10-13） | **已完成（保持）** | `docs/M3_ACCEPTANCE_REPORT.md` |
| M4 | 已完成（2026-10-13） | **已完成（保持）** | `docs/M4_ACCEPTANCE_REPORT.md` |
| M5 | 已完成（2026-10-13） | **已完成（保持）** | `docs/M5_ACCEPTANCE_REPORT.md` |
| M6 | 已完成（2026-10-14）通过（具备上线条件） | **已完成（保持）** | `docs/M6_ACCEPTANCE_REPORT.md` |

- 验收报告文件**未删除、未移动、未改写**。
- `.ai/MILESTONES.md` 等新文档写明「本表来自既有验收，迁移当日未复测业务」。
- **未开始 M7** 或任何新业务阶段。

---

## 8. 验证未修改业务代码的检查结果

### 8.1 实际执行的命令与结果

| 命令 | 结果 |
|---|---|
| `pwd` | `/Users/easonli/XiaomiMiMoProjects/dormitory-management-system` |
| `git status --short` | 无已跟踪文件变更；业务目录为 untracked（仓库无 commit） |
| `git diff --stat` | 空（无已跟踪文件 diff） |
| `git log --oneline` | `fatal: your current branch 'master' does not have any commits yet` |
| `find` + mtime 扫描（近 90 分钟） | `backend/`、`frontend/`、`compose*.yaml`、`.env*`、`scripts/`、`deploy/` **无**本次会话写入；`backend`/`frontend` 最后修改时间约 20:21–20:49，早于本次规范写入（21:00 后） |
| `find docs -type f` | M1～M6 等报告均存在且可读 |
| 模板文件 mtime | `templates/*`、`audit/*`、`.gitignore.sample` 保持 20:37 原始时间戳 |

### 8.2 本次会话实际写入范围（白名单）

仅：`.ai/`（新建规范与误覆盖的 migration 源文件）、`AGENTS.md`、本报告，以及会话笔记。  
**未**写入 `backend/**`、`frontend/**`、数据库、Docker 配置、`.env`。

### 8.3 未执行项（明确标记为未测试/未执行）

| 项目 | 状态 |
|---|---|
| 后端 pytest | **未测试**（文档迁移任务，无业务代码变更） |
| 前端 build / typecheck / vitest | **未测试** |
| Playwright E2E | **未测试** |
| Alembic 迁移 | **未执行** |
| Docker 构建/启动 | **未执行**（禁止项） |
| 数据库写入/清理 | **未执行**（禁止项） |
| Git 提交 | **未执行**（禁止自动提交） |
| 与 AI-SDLC 官方原文逐字 diff | **无法完整执行**（源包部分被覆盖，见 §5.5） |

---

## 9. 后续阶段如何执行 AI-SDLC 工作流

```
GPT Web 编写阶段指令 → MiMo 开发 → MiMo 自动化自检 → GPT Web 复核 → GitHub 提交阶段版本
```

1. **GPT Web** 使用 `.ai/prompts/STAGE_START_TEMPLATE.md`（或 `M01_START.md`）编写阶段指令，明确范围/禁区/验证命令/验收标准。
2. **MiMo** 按 `AGENTS.md` §3 启动任务：确认工作区 → 读基线 → 查实现 → 保护现场 → 计划 → 实施 → 汇报。禁止重新初始化、清库、覆盖未提交更改。
3. **MiMo 自动化自检**：实际运行测试；Web UI 变更必须 Playwright 真实浏览器测试并保存截图/命令/结果；按 `.ai/acceptance/ACCEPTANCE_TEMPLATE.md` 写阶段报告到 `docs/`；未测项标「未测试」。
4. **GPT Web 复核**：独立审阅实现与证据，可要求修复；复核结论与自检结论分开记录。
5. **GitHub 提交阶段版本**：由用户/复核方授权后提交；不 force push。
6. **全部阶段结束后**：ChatGPT Mac Work 按 `.ai/audit/FINAL_WORK_ACCEPTANCE.md` 在隔离测试环境做最终 UI/UX 与 E2E 验收。

### 对当前状态的约束

- M1～M6 已完成，**不得**回退为待开发。
- M7 及其他新阶段在 GPT Web 下发指令前**不得开工**。
- 若需严格对齐 AI-SDLC 官方 v1.0 条文，先恢复规范包原件再复核 `.ai/DEVELOPMENT_RULES.md` 与 `AGENTS.md`。

---

## 10. 验收结论（迁移任务）

| 检查项 | 结论 |
|---|---|
| 规范文件合并并落地 `.ai/` | **完成** |
| AGENTS.md 明确优先级与入口 | **完成** |
| 通用规则单一权威定义 | **完成** |
| M1～M6 状态保持 | **完成** |
| 验收报告未删除 | **完成** |
| 业务代码/迁移/Compose/.env 未改 | **完成**（见 §8） |
| 未自动 Git 提交 | **完成** |
| 未开始 M7 | **完成** |
| 迁移包源文件原文完整性 | **有缺陷**（§5.5，待用官方原件复核） |

**迁移任务结论：有条件通过。**  
条件：GPT Web 复核时用官方 AI-SDLC v1.0 原件核对被重建的源包/合并规则；确认后进入后续阶段。

---

**下一步**：停止业务开发，等待 GPT Web 复核。

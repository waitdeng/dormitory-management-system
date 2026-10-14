# AI-SDLC v1.0 最终修订报告（G1～G6 补齐）

- **项目**：公司宿舍入住管理系统（DMS）V1.0
- **修订日期**：2026-10-14
- **修订性质**：规范与模板补齐（**不含**业务功能开发）
- **执行代理**：MiMo Desktop / MiMo
- **工作区**：`/Users/easonli/XiaomiMiMoProjects/dormitory-management-system`
- **输入依据**：`docs/AI_SDLC_FINAL_VERIFICATION_REPORT.md` 缺口清单 G1～G6
- **Git 操作**：**未**执行 commit / tag / push；**未**修改业务代码、Docker 配置、数据库或历史验收报告

---

## 1. 修订摘要

| 缺口 | 主题 | 主修订位置 | 配套修订 | 状态 |
|---|---|---|---|---|
| G1 | 缺陷分级标准（P0～P3） | `.ai/DEVELOPMENT_RULES.md` §4 | `BUG_TEMPLATE.md`、`ACCEPTANCE_TEMPLATE.md` §5 | **已补齐** |
| G2 | 统一测试结果口径 | `.ai/DEVELOPMENT_RULES.md` §3.2、§5 | 验收模板 §1～§3、§8；阶段指令模板 | **已补齐** |
| G3 | 版本及测试证据 | `.ai/DEVELOPMENT_RULES.md` §3.3、§9 | 验收模板 §0、§5；`BUG_TEMPLATE.md` | **已补齐** |
| G4 | 版本标记 | `.ai/DEVELOPMENT_RULES.md` §10 | 验收模板 §9；阶段指令模板交付物 | **已补齐** |
| G5 | 测试期间版本冻结 | `.ai/DEVELOPMENT_RULES.md` §11 | 验收模板 §0、§7；阶段指令模板验证要求 | **已补齐** |
| G6 | 重大变更控制 | `.ai/DEVELOPMENT_RULES.md` §12、§13 | 验收模板 §6；阶段指令模板「重大变更预判」 | **已补齐** |

M1～M6 里程碑状态**保持不变**（见 `.ai/MILESTONES.md`）。历史验收报告 `docs/M1…M6_ACCEPTANCE_REPORT.md` **未改动**。

---

## 2. G1～G6 修订明细

### 2.1 G1 — 缺陷分级标准

| 项 | 内容 |
|---|---|
| **权威定义位置** | `.ai/DEVELOPMENT_RULES.md` §4「缺陷分级（G1）」 |
| **条文** | P0 阻断级：数据丢失、数据一致性破坏、严重越权、核心业务无法完成 → **禁止验收通过**；P1 高优先级：重要功能故障、可靠性缺陷、可导致错误业务结果 → 原则上必须修复后验收；P2 中优先级：非核心功能异常、局部 UI/UX 缺陷 → 允许经明确确认后延期；P3 低优先级：轻微显示问题、文档问题、非关键优化建议 |
| **判定原则** | 根据实际影响及可复现证据判定；同级争议就高不就低并记入决策 |
| **配套** | `BUG_TEMPLATE.md` 增加「严重程度」判定说明与「验收影响」表；`ACCEPTANCE_TEMPLATE.md` §5 P 级列 + P0 未关闭不得通过 |

### 2.2 G2 — 统一测试结果口径

| 项 | 内容 |
|---|---|
| **权威定义位置** | `.ai/DEVELOPMENT_RULES.md` §3.2；阶段门禁 §5 |
| **条文** | 测试项状态**必须**五选一：**通过 / 失败 / 跳过 / 环境阻塞 / 未执行**；不得将跳过、环境阻塞或未执行计入通过数量；存在未解决 P0 时阶段验收**必须不通过**；测试未完整执行时**不得**声明全量通过；汇总须分列五状态并可对账明细 |
| **配套** | `ACCEPTANCE_TEMPLATE.md` §1/§2/§3 状态列与 §2.1 汇总表；`STAGE_START_TEMPLATE.md` 验证要求与验收标准勾选项 |

### 2.3 G3 — 版本及测试证据

| 项 | 内容 |
|---|---|
| **权威定义位置** | `.ai/DEVELOPMENT_RULES.md` §3.3（缺陷证据最低字段）、§9（版本与测试证据基线） |
| **环境基线字段** | Git commit SHA；当前分支及工作区状态；Docker Compose 项目名称；Docker 镜像版本或 digest；Alembic 当前 revision；Python / Node.js 版本；浏览器及操作系统版本；测试环境与数据库隔离情况 |
| **缺陷六元组** | 测试入口、复现步骤、预期结果、实际结果、证据路径、对应代码版本 |
| **无基线规则** | 尚未建立 Git 提交历史的环境一律标记 **「未建立 Git 基线」**，**禁止虚构 SHA** |
| **配套** | `ACCEPTANCE_TEMPLATE.md` §0 环境与版本基线表（含测试开始/结束 Git 状态）；`BUG_TEMPLATE.md` 六项必填 |

### 2.4 G4 — 版本标记

| 项 | 内容 |
|---|---|
| **权威定义位置** | `.ai/DEVELOPMENT_RULES.md` §10「版本标记约定（G4）」 |
| **条文** | 阶段验收成功后建议 Tag `m1-accepted` / `m2-accepted` / `m3-accepted` …；正式版本 `v1.0.0` 等语义化版本；Tag **必须**指向实际完成复核的提交；**不得覆盖已有 Tag**；未经用户授权不得自动 `commit` / `tag` / `push` |
| **配套** | `ACCEPTANCE_TEMPLATE.md` §9「建议版本标记」；`STAGE_START_TEMPLATE.md` 交付物；`.ai/DEVELOPMENT_RULES.md` §7 交叉引用 |

### 2.5 G5 — 测试期间版本冻结

| 项 | 内容 |
|---|---|
| **权威定义位置** | `.ai/DEVELOPMENT_RULES.md` §11「测试期间版本冻结（G5）」 |
| **条文** | ① 暂停其他 AI 窗口对同一源码目录的并发修改；② 禁止其他任务操作当前测试数据库；③ 记录测试开始与结束时的 Git 状态；④ 测试期间代码变化须重新评估结果有效性；⑤ 写数据测试须在独立测试环境执行 |
| **配套** | `ACCEPTANCE_TEMPLATE.md` §0 开始/结束 Git 状态与「测试期间源码是否变化」；§7 数据安全确认勾选；`STAGE_START_TEMPLATE.md` 验证要求 |

### 2.6 G6 — 重大变更控制

| 项 | 内容 |
|---|---|
| **权威定义位置** | `.ai/DEVELOPMENT_RULES.md` §12「重大变更控制（G6）」+ §13 禁止事项 |
| **须批准事项** | 技术栈调整、数据库破坏性迁移、核心业务规则修改、认证与数据权限模型修改、删除已有功能、改变已验收的接口契约、大规模重构 —— 均须先形成变更建议并取得用户批准 |
| **严禁行为** | 删除失败的测试、跳过重要断言、弱化数据库约束、绕过权限校验、修改原始业务需求、伪造测试报告 |
| **配套** | `ACCEPTANCE_TEMPLATE.md` §6 变更与契约确认；`STAGE_START_TEMPLATE.md`「重大变更预判」勾选表；`BUG_TEMPLATE.md`「是否触及重大变更」 |

---

## 3. 修改文件清单

| 文件 | 修改类型 | 说明 |
|---|---|---|
| `.ai/DEVELOPMENT_RULES.md` | **实质修订** | 新增/重组：§3.2 测试口径、§3.3 证据字段、§4 缺陷分级、§5 阶段门禁、§9 环境基线、§10 Tag、§11 冻结、§12 变更控制、§13 禁止事项扩充；§6 工作流标题保持不变（兼容 `.ai/MILESTONES.md` 引用） |
| `.ai/acceptance/ACCEPTANCE_TEMPLATE.md` | **实质修订** | 新增 §0 环境与版本基线；统一五状态口径；§2.1 汇总对账；§5 缺陷证据列；§6 重大变更；§7 冻结勾选；§9 建议 Tag |
| `.ai/acceptance/BUG_TEMPLATE.md` | **实质修订** | 六元组证据、代码版本/「未建立 Git 基线」、重大变更标记、验收影响表 |
| `.ai/prompts/STAGE_START_TEMPLATE.md` | **实质修订** | 重大变更预判、五状态口径、环境基线、版本冻结、P0 门禁勾选 |
| `.ai/prompts/M01_START.md` | **引用补充** | 头部增加指向 `STAGE_START_TEMPLATE.md` 与 `.ai/DEVELOPMENT_RULES.md`（G1～G6） |
| `.ai/DECISIONS.md` | **索引/决策** | 新增 AI-SDLC-D005（本次修订决策），不改动既有 D-xxx 与迁移决策 |
| `docs/AI_SDLC_V1_FINAL_CORRECTION_REPORT.md` | **新增** | 本报告 |

### 3.1 明确未修改

- 业务代码：`backend/`、`frontend/`
- 部署与数据库：`compose.yaml`、`compose.production.yaml`、`deploy/`、Alembic
- 历史验收：`docs/M1_ACCEPTANCE_REPORT.md` … `docs/M6_ACCEPTANCE_REPORT.md`
- 里程碑状态：`.ai/MILESTONES.md`（M1～M6 仍为「已完成」）
- 项目专属规格：`DMS_V1.0_MiMo_Development_Spec.md`、根 `AGENTS.md`（已通过路径引用 `.ai/DEVELOPMENT_RULES.md`，按任务要求**不**重复写入全文）
- 迁移包源目录：`.ai/migration/AI-SDLC-v1.0/`（保留以便对照）
- 最终校验报告：`docs/AI_SDLC_FINAL_VERIFICATION_REPORT.md`（保留原始结论供追溯）

---

## 4. 引用与路径检查

已核验下列引用路径均存在且可解析：

| 路径 | 结果 |
|---|---|
| `.ai/DEVELOPMENT_RULES.md` | OK |
| `.ai/acceptance/ACCEPTANCE_TEMPLATE.md` | OK |
| `.ai/acceptance/BUG_TEMPLATE.md` | OK |
| `.ai/prompts/STAGE_START_TEMPLATE.md` | OK |
| `.ai/prompts/M01_START.md` | OK |
| `.ai/DECISIONS.md` | OK |
| `.ai/MILESTONES.md` | OK |
| `.ai/PROJECT_CONTEXT.md` | OK |
| `.ai/audit/FINAL_WORK_ACCEPTANCE.md` | OK |
| `AGENTS.md` | OK |
| `DMS_V1.0_MiMo_Development_Spec.md` | OK |
| `docs/DECISIONS.md` | OK |
| `docs/IMPLEMENTATION_PLAN.md` | OK |
| `docs/AI_SDLC_FINAL_VERIFICATION_REPORT.md` | OK |
| `docs/M1_ACCEPTANCE_REPORT.md` … `docs/M6_ACCEPTANCE_REPORT.md` | OK（6/6） |

章节编号兼容性：

- `.ai/MILESTONES.md` 引用 `.ai/DEVELOPMENT_RULES.md` **§6**（AI-SDLC 阶段工作流）——修订后 §6 标题与内容保持为工作流，**引用有效**。
- 根 `AGENTS.md` 仅以路径引用 `.ai/DEVELOPMENT_RULES.md` 与 `.ai/acceptance/ACCEPTANCE_TEMPLATE.md`，无失效锚点。

M1～M6 状态复核：

```
M1 已完成 2026-10-13  docs/M1_ACCEPTANCE_REPORT.md
M2 已完成 2026-10-13  docs/M2_ACCEPTANCE_REPORT.md
M3 已完成 2026-10-13  docs/M3_ACCEPTANCE_REPORT.md
M4 已完成 2026-10-13  docs/M4_ACCEPTANCE_REPORT.md
M5 已完成 2026-10-13  docs/M5_ACCEPTANCE_REPORT.md
M6 已完成 2026-10-14  docs/M6_ACCEPTANCE_REPORT.md
```

---

## 5. G1～G6 落点对照（验收用）

| 要求条目（任务书） | 落点 |
|---|---|
| P0 数据丢失/一致性/越权/核心不可用，禁止验收通过 | RULES §4 表 + §3.2 强制规则 2 |
| P1 重要故障/可靠性/错误业务结果，原则上修复后验收 | RULES §4 |
| P2 非核心异常/局部 UX，明确确认后可延期 | RULES §4 |
| P3 轻微显示/文档/非关键建议 | RULES §4 |
| 分级按实际影响及可复现证据 | RULES §4 判定原则 |
| 五状态：通过/失败/跳过/环境阻塞/未执行 | RULES §3.2；模板全表 |
| 跳过/阻塞/未执行不得计入通过 | RULES §3.2 强制 1 |
| 未解决 P0 → 阶段不通过 | RULES §3.2 强制 2；模板 §5/§8 |
| 未完整执行不得声明全量通过 | RULES §3.2 强制 3 |
| 环境基线八字段 | RULES §9 表；模板 §0 |
| 缺陷六元组 | RULES §3.3；BUG_TEMPLATE |
| 无 Git 历史 →「未建立 Git 基线」，禁虚构 SHA | RULES §9 规则 1；模板 §0/§5 |
| Tag `m*-accepted` / `v1.0.0` | RULES §10 |
| Tag 对应已复核提交；不覆盖已有 Tag | RULES §10 规则 1–2 |
| 未授权不自动 commit/tag/push | RULES §7、§10 规则 3 |
| 冻结：暂停并发修改、禁动测试库、记开始/结束 Git 状态、代码变化重估、独立测试环境 | RULES §11 五条 |
| 重大变更七类须批准 | RULES §12 |
| 严禁删测试/跳断言/弱约束/绕权限/改需求/伪造报告 | RULES §12、§13 |

---

## 6. 仍未解决的问题

| ID | 问题 | 影响 | 建议 | 本次是否处理 |
|---|---|---|---|---|
| R1 | **Git 仍无基线提交**；本地 `main` 零提交、全部 untracked，远程 `origin/main` 有独立历史 | 验收报告无法绑定真实 SHA；Tag 规则（G4）暂无法落地 | 用户确认与远程关系后授权建立基线提交，再单独提交规范修订 | **否**（禁止自动 commit） |
| R2 | 既有 `docs/M1…M6_ACCEPTANCE_REPORT.md` 为修订前格式，未含 §0 环境基线全字段与五状态汇总表 | 历史报告与新模板不完全同构 | **不回改**历史报告（任务禁止）；新阶段起用新模板 | **否**（有意保持） |
| R3 | 原始规范包 `.ai/migration/AI-SDLC-v1.0/` 仍为重建副本，与 `AI-SDLC-v1.0.zip` 非逐字一致 | 对照阅读时需以 ZIP 为准 | 只读归档 ZIP；或在获授权后用 ZIP 覆盖迁移包作对照副本 | **否** |
| R4 | `AI_SDLC_MIGRATION_REPORT.md` 中分支名写作 `master`，实际为 `main` | 轻微表述偏差 | 勘误一行或以本报告 / 校验报告为准 | **否**（非本次修改范围） |
| R5 | 未在真实阶段中演练新模板（无 M7 指令） | 模板字段是否顺手待实践检验 | 下一阶段 GPT Web 下发指令时使用 `STAGE_START_TEMPLATE.md` 并反馈 | **否**（无新阶段授权） |

---

## 7. 本次实际验证

| 检查项 | 方法 | 结果 |
|---|---|---|
| 修改范围合规 | `git status` + 目录清单 | 仅规范/模板/报告/决策索引；未动 backend/frontend/compose/历史验收 |
| M1～M6 状态 | 读取 `.ai/MILESTONES.md` | 全部「已完成」，日期与证据路径未变 |
| 路径引用 | 逐条 `test -f` | 20 个引用路径全部 OK |
| §6 工作流引用 | 章节标题核对 | `.ai/MILESTONES.md` → RULES §6 仍指向工作流 |
| G1～G6 关键词 | 全文检索 | P0 分级、环境阻塞、未建立 Git 基线、m1-accepted、版本冻结、重大变更均已落入 |

**未测试声明**：本次为文档修订，**未**执行 pytest / npm / Playwright / Docker / Alembic；**未**复测业务功能。规范条文的“可执行性”须在下一阶段真实验收中检验。

---

## 8. 结论与下一步

1. **G1～G6 已全部写入**权威定义文件与配套模板，落点见 §2、§5。  
2. **修改范围符合任务约束**：未改业务代码、Docker、数据库与历史验收报告；`AGENTS.md` 经既有路径引用覆盖，无需重复全文。  
3. **M1～M6 状态保留**；Markdown 路径引用有效。  
4. **残留问题 R1～R5** 需人工/后续阶段处理，其中 R1（Git 基线）优先级最高。  
5. **按任务要求停止**：不执行 Git 提交，不开始新阶段开发。等待 **GPT Web 复核**。

---

*报告生成：MiMo Desktop / MiMo · 2026-10-14 · 任务范围：AI-SDLC v1.0 规范迁移最终修订（G1～G6）*

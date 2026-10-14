# 决策记录索引（DECISIONS）— AI-SDLC v1.0

> 项目技术/业务决策的**完整正文**在 `docs/DECISIONS.md`（D-001 … D-046 等），此处只做索引与文档迁移决策，避免两份权威定义。

## 1. 项目已有决策（权威正文）

- 路径：`docs/DECISIONS.md`
- 范围：认证/令牌、错误格式、迁移策略、锁顺序、幂等、导入、扫描、数据范围、报表口径、Compose 双模式等（D-001 起）。
- 新增技术/业务决策时：**继续追加到 `docs/DECISIONS.md`**，倒序或编号递增，不删除历史。

## 2. 文档迁移决策（AI-SDLC v1.0 接入）

### AI-SDLC-D001 规则分层

- **日期**：2026-10-14
- **背景**：需将 AI-SDLC v1.0 通用规范接入 DMS，且不得丢失项目专属规则。
- **决策**：
  - 通用规则权威定义：`.ai/DEVELOPMENT_RULES.md`
  - 项目业务权威定义：`DMS_V1.0_MiMo_Development_Spec.md` + `AGENTS.md`
  - `AGENTS.md` 只保留规则优先级、文档入口与项目不变量/执行约束，通用细则以路径引用。
- **影响**：避免重复定义；冲突时按 `AGENTS.md` 优先级处理并记入本文件。

### AI-SDLC-D002 保留 docs/ 原结构

- **日期**：2026-10-14
- **背景**：AI-SDLC 期望 `acceptance/` 等目录，项目已有 `docs/M*_ACCEPTANCE_REPORT.md`。
- **决策**：不移动、不重命名、不删除 `docs/` 下既有验收与计划文档；`.ai/acceptance/` 只放**模板**，项目验收报告仍以 `docs/` 为准。
- **影响**：M1～M6 状态与证据路径保持不变。

### AI-SDLC-D003 阶段工作流切换

- **日期**：2026-10-14
- **背景**：今后开发采用 AI-SDLC 统一流程。
- **决策**：GPT Web 编写阶段指令 → MiMo 开发 → MiMo 自动化自检 → GPT Web 复核 → GitHub 提交阶段版本；Web UI 变更必须 Playwright 真测；最终由 ChatGPT Mac Work 做 E2E/UX 验收。
- **影响**：写入 `AGENTS.md` 与 `.ai/DEVELOPMENT_RULES.md`；历史阶段验收结论不因流程切换而失效。

### AI-SDLC-D004 迁移包源文件覆盖说明

- **日期**：2026-10-14
- **背景**：会话处理中误覆盖了 `.ai/migration/AI-SDLC-v1.0/` 下部分源文件（详见 `AI_SDLC_MIGRATION_REPORT.md`）。
- **决策**：交付以项目根 `.ai/` 合并结果为准；源包覆盖情况在迁移报告中如实披露，不伪称“已完整比对原文”。
- **影响**：若需严格比对 AI-SDLC 官方原文，请重新提供规范包归档后 diff。

### AI-SDLC-D005 最终校验缺口 G1～G6 修订

- **日期**：2026-10-14
- **背景**：`docs/AI_SDLC_FINAL_VERIFICATION_REPORT.md` 指出通用规则相对原文存在 G1～G6 条文遗漏。
- **决策**：在 `.ai/DEVELOPMENT_RULES.md` 补齐缺陷分级（§4）、测试结果口径（§3.2）、证据字段（§3.3）、版本与环境基线（§9）、Tag 约定（§10）、测试冻结（§11）、重大变更控制（§12）；同步更新 `.ai/acceptance/ACCEPTANCE_TEMPLATE.md`、`.ai/acceptance/BUG_TEMPLATE.md`、`.ai/prompts/STAGE_START_TEMPLATE.md`。**不**用原始通用模板覆盖 DMS 专属规范，**不**改动业务代码与历史验收报告。
- **影响**：后续阶段验收须按五状态口径与环境基线填写；无 Git 基线时标记「未建立 Git 基线」；P0 未关闭不得通过。详见 `docs/AI_SDLC_V1_FINAL_CORRECTION_REPORT.md`。

## 3. 记录格式（新决策模板）

每条决策包含：

- **日期**
- **背景**：问题或约束
- **决策**：选择了什么
- **备选**：考虑过但未采用的方案
- **影响**：兼容性、风险、后续义务
- **状态**：提议 / 已接受 / 已废弃

原则：文档与代码冲突时不静默重写；通用规则与项目规则冲突时记录并给建议；倒序/编号追加，不删历史。

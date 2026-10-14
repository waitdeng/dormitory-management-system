# .ai/ 目录说明（AI-SDLC v1.0）

本目录存放跨项目通用的 AI 开发规范与模板；项目业务规格与阶段文档仍在根目录与 `docs/`。

| 路径 | 作用 |
|---|---|
| `PROJECT_CONTEXT.md` | 项目上下文（业务边界、技术栈、当前阶段） |
| `DEVELOPMENT_RULES.md` | 通用开发规则（**权威定义**） |
| `MILESTONES.md` | 里程碑状态（保持 M1～M6，不重置） |
| `DECISIONS.md` | 决策索引与迁移决策；技术决策正文在 `docs/DECISIONS.md` |
| `prompts/` | GPT Web 阶段指令模板 |
| `acceptance/` | 阶段验收与缺陷模板（正式报告在 `docs/`） |
| `audit/` | ChatGPT Mac Work 最终验收模板 |
| `local/` | （可选）本机私有笔记，已列入 `.gitignore` 建议忽略 |

规则优先级与文档入口见根目录 `AGENTS.md`。

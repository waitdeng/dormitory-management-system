# DMS V1.0.1 Release Checklist

| # | 检查项 | 结果 | 证据 |
|---|---|---|---|
| 1 | 后端完整 pytest | **通过** | 167 passed |
| 2 | 前端 Vitest / typecheck / build | **通过** | 5 passed / 0 error / success |
| 3 | Playwright E2E 回归 | **通过** | 18 passed |
| 4 | Docker Compose 构建与健康 | **通过** | 三服务 healthy；`compose config -q` OK |
| 5 | Alembic 最新迁移 | **通过** | head `0006_v101_room_access_and_types` |
| 6 | 全新库初始化 + RBAC | **通过** | `dms_v101_fresh_drill` 27 表 / 30 权限 / 6 角色 |
| 7 | 生产独立 ACCESS_CODE_ENCRYPTION_KEY | **未配置（当前环境）** | 代码已支持；**上线前必须配置**，否则回退 SECRET_KEY |
| 8 | 无真实密钥/测试密码泄露 | **通过** | 源码扫描无硬编码密钥；包内无 `.env` |
| 9 | 数据库持久化/备份恢复流程 | **通过（文档+脚本）** | `scripts/backup.sh` / `restore.sh`；演练见 M6/07B |
| 10 | 开发测试数据不迁生产 | **通过（策略确认）** | 用户决定；生产空库录入 |

## 版本冻结

| 项 | 值 |
|---|---|
| 版本 | V1.0.1 |
| 冻结 UTC | 2026-10-15T03:44:05Z |
| 快照 | `dms-V1.0.1-freeze-20261015114514.zip` |
| SHA-256 | `f7de68ce252ecebacae6126145908b26f820c143ea5a21031b83b875c55cc520` |
| Git SHA/Tag | **无（未使用 Git）** — 不伪造 |
| 迁移版本 | `0006_v101_room_access_and_types` |

**结论**：除第 7 项须生产环境配置密钥外，发布前检查完成。部署与可访问性由项目负责人确认后实施。

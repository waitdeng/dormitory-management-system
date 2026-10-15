# DMS V1.0.1 Release Notes

> 版本：**V1.0.1**  
> 发布冻结时间（UTC）：2026-10-15T03:44:05Z  
> Git：**未使用**（无 commit SHA / Tag；以源码快照 SHA-256 为准，见 `V1_0_1_FREEZE_MANIFEST.txt`）  
> 范围：M1～M6 + V1.0.1 HOTFIX-01～07A；HOTFIX-07B 历史修复**取消**

---

## 1. 功能范围

### M1～M6
- 认证 / RBAC / 审计 / 部门员工 / Excel 导入导出
- 宿舍区域→床位层级、入住/调宿/退宿事务、离职联动
- 可视化分床、台账报表、备份恢复、Compose 部署

### V1.0.1 修复与增强
| 项 | 摘要 |
|---|---|
| BUG-001 | 宿舍资源删除（关联阻断 + 停用） |
| FEAT-002 | 房型字典 + 房间 Excel 导入 |
| BUG-003 | 房间点击 422 / 双弹窗 / 双请求 |
| UX-004 | 导航筛选 + 批量分床导入 |
| BUG-005 | 调宿床位完整路径 |
| UX-006 | 人事状态中文化 |
| BUG-007 (P0) | 不需住宿员工禁止分床（后端强制） |
| FEAT-008 | 房间门禁密码加密与授权查看 |
| HOTFIX-04 | 层级编辑删除、房型删除、分床筛选、点床选人分配 |
| HOTFIX-05 | 候选仅「在职」+ 仅底部确认分配 |
| HOTFIX-06 | 入住列表床位关联（列表 API 补 bed） |
| HOTFIX-07A | 预留过期同步申请状态 + 锁序统一 |
| HOTFIX-07B | **取消**（测试数据不修复、不迁生产） |

---

## 2. 数据库

- Alembic head：`0006_v101_room_access_and_types`
- 全新库：`alembic upgrade head` → `python -m app.seed`
- **不迁移开发测试数据**

## 3. 构建与验证（真实执行）

| 项 | 结果 |
|---|---|
| backend pytest | **167 passed** |
| frontend vitest | **5 passed** |
| vue-tsc / vite build | 0 error / success |
| Playwright | **18 passed** |
| Docker Compose | backend/frontend/mysql healthy |
| 全新库演练 | 0001→0006 + RBAC seed OK |

## 4. 安全注意

- 生产必须配置独立 `ACCESS_CODE_ENCRYPTION_KEY`（当前运行环境未配置，回退 SECRET_KEY）
- `.env` 不入库；使用 `.env.example`

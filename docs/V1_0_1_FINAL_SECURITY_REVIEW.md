# V1.0.1 最终安全与数据一致性专项核验报告

> 日期：2026-10-14  
> 范围：UX-004 批量分床失败恢复 · FEAT-008 门禁密码全局轮换权限  
> 环境：真实 MySQL 8.0（Docker Compose）+ 真实 Chrome Playwright  
> 约束：不使用 Git；手动备份；**不自行宣布正式发布**，提交 GPT Web 复核。

---

## 0. 结论摘要

| 专项 | 发现问题 | 处理 | 结论 |
|---|---|---|---|
| UX-004 失败恢复 | 未发现数据一致性缺陷；6 类故障注入全部满足不变量 | 无代码修复 | **通过** |
| FEAT-008 轮换权限 | **权限过宽**：原 `POST /rooms/access-code/rotate` 使用 `dorm:access_code:update`，宿管可全局轮换 | 新增 `dorm:access_code:rotate` + `secrets_ops` 角色；宿管仅可维护单房密码 | **已修复并通过** |

**全量回归（非仅新增用例）**：

| 范围 | 命令 | 结果 |
|---|---|---|
| 后端全部 | `cd backend && .venv/bin/python -m pytest -q` | **141 passed** |
| 前端 Vitest | `cd frontend && npm test` | **5 passed** |
| 类型检查 | `npm run typecheck` | **0 error** |
| Playwright 全量 | `./node_modules/.bin/playwright test` | **11 passed** |

---

## 1. UX-004 批量分床失败恢复专项

### 测试文件
`backend/tests/test_v101_final_security_review.py`（UX-004 段，6 条）

### 故障注入与不变量逐项结果

| # | 场景 | 注入方式 | 不变量检查 | 结果 |
|---|---|---|---|---|
| 1 | 申请已创建，**预留失败** | monkeypatch `reserve_bed` 抛错 | 无 active 入住；床 `available=true`；行含 `recovery` | **通过** |
| 2 | 预留成功，**确认入住失败** | monkeypatch `confirm_checkin` 抛错 | **无孤儿有效预留**；床可再分配；recovery=`application_cancelled`/`reservation_released` | **通过** |
| 3 | **取消申请失败** | 同时让 confirm+cancel 抛错 | 强制释放残留预留或 `cancel_failed` 标记；床不残留 `reserved=true` | **通过** |
| 4 | 批量中**数据库/应用异常** | 第 2 行 `create_application` 抛错 | 第 1 行成功保留；第 2 行无占用；错误 message 可追溯 | **通过** |
| 5 | **相同导入重复提交** | 同一 xlsx 连续两次 commit | 第二次 succeeded=0；不双占；错误原因明确 | **通过** |
| 6 | **两批次并发争抢同一床** | `asyncio.gather` 两请求 | `succeeded` 合计 = 1；无重复有效入住 | **通过** |

### 额外不变量（审查清单）

| 要求 | 证据 |
|---|---|
| 不得重复有效入住 | #4/#5/#6：同床最多 1 条 active；重复提交不建第二条 |
| 不得出现无法解释的有效预留 | #2/#3：失败后 bed `reserved=false` |
| 失败申请明确状态 + 可追溯恢复 | 每行 `action/message/recovery`；审计 `checkin.batch_allocate_import` / `.recovery` |
| 人工可发现异常 | 行级错误列表 + `recovery=cancel_failed` 明确标记 + 审计 |
| 重试不重复分床 | #5 |
| 不得改动他人预留 | `test_ux004_no_modify_foreign_active_reservation`：他人 `reserved` 保持 active |

### 数据一致性结论
故障注入下 **未发现** 重复占床、孤儿预留或不可追溯状态。恢复逻辑为：行前 rollback → `cancel_application` → `_release_orphan_reservation`（仅释放**该员工/该申请**的 active 预留）→ 行级 `recovery` 标记。

**本轮 UX-004 无需代码修复。**

---

## 2. FEAT-008 门禁密码全局轮换权限

### 发现问题（已在本轮修复）
原接口 `POST /api/v1/rooms/access-code/rotate` 使用 `PERM_DORM_ACCESS_CODE_UPDATE`（`dorm:access_code:update`），而该权限已授予 **dorm_admin**，导致普通宿管可执行**全局密钥轮换**，不符合“仅超管/独立运维角色”要求。

### 修复内容
| 文件 | 变更 |
|---|---|
| `backend/app/core/permissions.py` | 新增 `dorm:access_code:rotate`；新角色 `secrets_ops`（仅 rotate + audit:view） |
| | `super_admin` 经全量权限自动包含 rotate；**dorm_admin 仍持有 view/update，不含 rotate** |
| `backend/app/api/v1/endpoints/dormitories.py` | rotate 端点改为 `require_permission(dorm:access_code:rotate)` |
| `backend/app/seed.py` | 无改（自动同步 ROLE_CATALOGUE/ROLE_PERMISSIONS） |

### 权限矩阵（实测）

| 角色 | 单房设密/查看 | 全局 rotate | 结果 |
|---|---|---|---|
| super_admin | ✅ | ✅ | 200，且轮换后密码仍可读 |
| secrets_ops | — | ✅ | 200 |
| dorm_admin | ✅（单房维护） | ❌ **403** | 符合要求 |
| hr | ❌ | ❌ **403** | 符合 |
| finance_viewer | ❌ | ❌ **403** | 符合 |
| dept_manager | ❌ | ❌ **403** | 符合 |

### 轮换安全属性（实测）

| 要求 | 结果 |
|---|---|
| 轮换失败**不破坏**原有密文 | 注入 `reencrypt` 抛错后 `failed>=1`，原密文仍可解密为 `009911` |
| 审计不含明文/密钥 | rotate 响应与审计仅 `migrated/already_current/failed/scanned`；用例断言明文不出现 |
| 轮换后现有密码可读 | `001122`/`004455`/`009911` 等轮换前后读取一致 |

### 测试文件
`backend/tests/test_v101_final_security_review.py`（FEAT-008 段，6 条）

---

## 3. 实际执行的测试命令

```text
# 专项
cd backend && .venv/bin/python -m pytest tests/test_v101_final_security_review.py -q
→ 12 passed

# 后端全量（含 M1～M6、V1.0.1、复核补强、本专项）
cd backend && .venv/bin/python -m pytest -q
→ 141 passed

# 前端
cd frontend && npm test          → 5 passed
cd frontend && npm run typecheck → 0 error

# Playwright 全量
cd frontend && ./node_modules/.bin/playwright test
→ 11 passed
```

Docker：`docker compose build backend && docker compose up -d backend` 后 `/health` 正常；RBAC `python -m app.seed` 已刷新（`secrets_ops` 入库）。

---

## 4. 发现问题清单

| ID | 级别 | 描述 | 状态 |
|---|---|---|---|
| SEC-001 | **高** | 全局轮换接口权限过宽（宿管可调用） | **已修复**（独立权限 + secrets_ops） |
| — | — | UX-004 故障注入未发现一致性缺陷 | 无需修复 |

---

## 5. 剩余风险

1. **`ACCESS_CODE_ENCRYPTION_KEY` 未配置时仍回退 SECRET_KEY 派生**（兼容旧部署）；生产必须配置独立钥，否则与 JWT 密钥仍耦合。
2. **`secrets_ops` 为新增角色**，需在生产用户分配中显式授予；默认仅 super_admin 可 rotate。
3. **取消失败极端路径**会留下待人工处理的申请单（行内 `cancel_failed` + recovery 审计）；强释预留保证不双占。
4. **手动备份**：密钥变更前应按 `docs/BACKUP_RESTORE.md` 备份库（含 `access_code_encrypted`）。
5. Playwright 仍使用系统 Chrome（M6 遗留）。

---

## 6. 交付说明

- 本报告为专项核验记录，**不构成 V1.0.1 发布声明**。
- 未执行的检查未标记通过；全部数字来自上表命令的真实输出。
- 提交 GPT Web 复核；通过前不得宣布正式发布。

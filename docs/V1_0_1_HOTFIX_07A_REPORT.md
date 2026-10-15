# DMS V1.0.1 HOTFIX-07A 报告 — 预留过期与申请状态同步根因修复

> 日期：2026-10-15  
> 依据：`docs/V1_0_1_HOTFIX_07_ANALYSIS.md`（GPT Web 有条件通过）  
> **本阶段未对正式历史数据执行批量修复。**  
> 完成后提交 GPT Web 复核。

---

## 1. 根因与修复

| 项 | 说明 |
|---|---|
| 根因 | 扫描器将 `bed_reservations` 置 `expired` 后**不回写** `accommodation_applications`；状态机无 `reserved → approved` |
| 次因 | `_load_app` **先 FOR UPDATE 申请**，再锁员工/床位，违反 employee → bed → business，与扫描器交叉易死锁 |
| 修复 | ① 写路径改为 peek → `lock_employee` → `lock_beds` → `_lock_app`；② 过期事务内同步 `reserved → approved`（条件见下） |

### 过期回退条件（全部满足才迁移）
1. 该预留为本次到期目标，且 `application.assigned_bed_id == res.bed_id`
2. `application.status == 'reserved'`
3. 本申请无 `active` 住宿
4. 员工无 `active` 住宿（防误回退已入住房）
5. 仅 `expired` 路径同步；`consumed` 路径不改申请

`assigned_bed_id` **保留**作历史指针；展示层对「已批准/已预留且无有效预留」显示「未分配」。

---

## 2. 事务锁顺序（统一）

```text
employees FOR UPDATE
  → dorm_beds FOR UPDATE (id 升序)
    → bed_reservations / accommodation_records / applications 等业务行
```

| 文件 | 变更 |
|---|---|
| `backend/app/services/checkin_service.py` | `_peek_app` / `_lock_app`；`reserve_bed`/`confirm_checkin`/`cancel_application` 调整锁序；重复确认对已消费预留走当前读幂等 |
| `backend/app/services/scanner_service.py` | `_sync_app_after_reservation_expiry`（过期主路径 + 占用冲突路径）；审计 `application.reservation_expired_revert` |
| `scripts/repair_stale_reserved_apps.py` | C1 仅 `expired` 预留可入选；**排除 C5**；dry-run 默认 |
| `scripts/classify_stale_reserved_apps.py` | 保持只读 |

**未**吞掉死锁；**未**绕过行锁。历史数据脚本未对正式库 `--apply`。

---

## 3. 并发专项测试（真实 MySQL）

`backend/tests/test_v101_hotfix07a_concurrency.py`（9 条）+ 既有并发套件。

| 场景 | 结果 |
|---|---|
| 确认入住 vs 预留过期 | PASS（单边成功；无双占；床状态一致） |
| 取消 vs 过期 | PASS |
| 重新预留 vs 旧预留过期 | PASS（active 预留 ≤1） |
| 双扫描 | PASS（幂等） |
| 同员工多床并发 | PASS（≤1 成功） |
| 重复确认 | PASS（幂等 200，单 active 入住） |
| 死锁/锁序 | `test_p1_003_concurrent_confirm_vs_scan_many_rounds` PASS |
| 已入住/调宿历史保护 | PASS |
| 过期后无新增 reserved+expired | PASS（app→approved） |

断言检查 **DB 不变量**（active 住宿数、床位 occupied/available、申请状态），不只 HTTP 码。

---

## 4. 历史数据保护（本阶段未修复）

- 分类脚本 / 修复脚本 dry-run 能力保留。  
- C1 入选：`reserved` + 本申请存在 **expired** 预留 + 无 active 入住 + 员工无 active 入住。  
- **C5 默认排除**（cancelled 预留不得仅凭 assigned_bed_id 入选）。  
- 修复前二次校验；审计仅记录状态与 id，不含姓名/工号明文。  
- 正式 `--apply` 仍待 GPT Web/业主授权（HOTFIX-07 §3.4）。

---

## 5. 全量回归

| 命令 | 结果 |
|---|---|
| `cd backend && .venv/bin/python -m pytest -q` | **163 passed** |
| `cd frontend && npm test` | **5 passed** |
| `npm run typecheck` | **0 error** |
| `./node_modules/.bin/playwright test --workers=2` | **18 passed**（M1～M6 + V1.0.1 + HOTFIX-01～06） |

验证预留过期后：预留 `expired`、申请 `approved`、床 `available`、入住列表「未分配」、**不再产生新的 reserved+expired**。

---

## 6. 拟修改文件汇总

- `backend/app/services/checkin_service.py`
- `backend/app/services/scanner_service.py`
- `backend/scripts/repair_stale_reserved_apps.py`
- `backend/tests/test_v101_hotfix07a_concurrency.py`  
- 迁移：**无 DDL**

---

## 7. 遗留风险

1. 正式库历史 C1/C5 仍待授权修复。  
2. `reserve_target`（调宿）仍使用业务行先行锁，建议后续对齐同一顺序。  
3. 高并发下 confirm 幂等依赖 `FOR UPDATE` 当前读；若未来改隔离级别需回归。  
4. 扫描器进程内单实例（M6 遗留）。

---

## 8. 交付声明

- 根因已从源头修复；历史批量修复**未执行**。  
- **不宣布发布**；提交 GPT Web 复核。

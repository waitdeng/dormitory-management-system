# DMS V1.0.1 HOTFIX-07 分析报告 — 历史预留状态一致性

> 日期：2026-10-15  
> 性质：**分析 / 只读核查 / 方案设计 / 隔离库演练**  
> **本阶段未对正式业务库执行 UPDATE、DELETE 或批量修复。**  
> 报告提交 GPT Web 审核后，再决定是否授权正式修复。

---

## 1. 根因分析

### 1.1 为什么会出现「reserved + 预留已过期」

| 环节 | 事实 |
|---|---|
| 预留超时扫描 | `_expire_one_reservation` 只把 `bed_reservations.status` 改为 `expired` 并释放床位 |
| 申请状态机 | **不回写** `accommodation_applications.status` |
| 结果 | 申请停留在 `reserved`，有效预留已不存在 → 展示层按 HOTFIX-06 显示「未分配」 |

**代码证据**
- `scanner_service._expire_one_reservation`：置 `res.status=expired`，审计 `reservation.expire`，**无** application 同步。
- `checkin_service` 状态机：`reserved → checked_in`（confirm）、`reserved → cancelled`（cancel）；**无** `reserved → approved`（预留过期回退）。

### 1.2 是否仍会持续产生

**会。** 只要发生「预留成功后未确认入住，且预留过期被扫描」，且无人 cancel/confirm，就会再产生一条 stale。测试库同类数据已从 HOTFIX-06 的 109 涨至本轮分类 127（含测试流量）。

### 1.3 并发与死锁

| 路径 | 锁顺序 |
|---|---|
| 文档约定（AGENTS.md §4 / D-026） | employees → beds(id asc) → 业务行 |
| `confirm_checkin` / `reserve_bed` | **`_load_app` 先 `FOR UPDATE` 申请**，再 `lock_employee` → `lock_beds` |
| 扫描过期 | employee → bed → reservation |

扫描器若再对申请 `FOR UPDATE`，会与 confirm 的「先锁申请」形成环 → 已在 `test_p1_003_concurrent_confirm_vs_scan_many_rounds` 复现死锁（HOTFIX-06 尝试回写后出现，已撤销）。

**重复过期**：扫描只处理 `active` 且过期的预留，重复扫描幂等（演练 S3 通过）。  
**并发确认 vs 扫描**：单库事务下一方 consume / 一方 expire，演练 S2 不崩溃（业务 409 或成功其一）。

---

## 2. 109/127 条历史数据精确分类（只读）

命令：
```text
cd backend && .venv/bin/python scripts/classify_stale_reserved_apps.py
```

> 快照时间：分析当日；测试流量会使计数漂移。正式修复前须重新分类。

| 类别 | 数量 | 判定 | 能否回退 approved |
|---|---|---|---|
| **C1** 预留 expired，无任何有效住宿，申请仍 assigned_bed | **113** | 标准过期未同步 | **可**（修复时二次校验后） |
| **C2** 员工已有有效住宿 | **0** | — | 不适用 |
| **C3** 存在其他有效预留 | **0** | — | 不适用 |
| **C4** 有调宿/退宿/后续申请 | **0** | — | 不适用 |
| **C5** 预留 `cancelled` 但申请仍 `reserved` | **14** | 半程取消/重预留残留 | **否**，须人工逐单确认后再定 |
| 合计 stale（reserved 无有效预留） | **127** | | |

脱敏样例：
- C1：`app#101/CA-...-3438/E_******a2/res=['expired']/assigned=186`
- C5：`app#1234/CA-...-5828/E_******a0/res=['cancelled']/assigned=2085`

**结论：不得把全部 reserved+expired 一律回退 approved。** C5 的 `cancelled` 预留可能对应取消未完成或换床中途，需人工看审计。

---

## 3. 修复方案设计（未执行）

脚本草稿：`backend/scripts/repair_stale_reserved_apps.py`（默认 **dry-run**，需显式 `--apply`）。

### 3.1 入选条件（修复时再查一次 DB）
1. `application.status = reserved`
2. 无 `active` 预留（本申请）
3. 无 `active` 住宿（本申请）
4. 员工无 `active` 住宿（防双占）
5. 存在 `expired|cancelled|consumed` 预留历史或 `assigned_bed_id` 非空  
6. **C5 默认 skip**（reserved + res=cancelled）→ 人工队列

### 3.2 修复动作（C1）
- `status: reserved → approved`（可重新分床）
- **保留** `assigned_bed_id` 作为历史指针（**不清空**；产品若要求清空须另批）
- **保留** 预留 `expired` 历史行
- 审计 `application.repair_stale_reserved`（before/after 快照）

### 3.3 安全属性
| 要求 | 实现 |
|---|---|
| 仅修复核实异常 | 修复时条件重检 |
| 不改正常入住/调宿/退宿 | 跳过有 active 住宿 / C2–C4 |
| 不清除有效记录 | 仅改申请 status |
| 保留过期预留历史 | 不 DELETE |
| 不默认清空 assigned_bed | 保留 |
| 审计+可恢复 | before 快照；反向脚本可 `approved→reserved`（若业务需要） |
| 幂等 | 二次 apply 返回 0（演练 S4） |

### 3.4 正式执行前置条件（建议）
1. GPT Web 批准本报告  
2. 全量备份（`docs/BACKUP_RESTORE.md`）  
3. 重新跑分类脚本并冻结清单  
4. 在隔离库用**生产导出子集**再演练一次  
5. 维护窗口执行 `--dry-run` 人工抽查 → `--apply`  
6. 复跑一致性脚本至 C1=0，C5 单独跟踪  
7. 出具执行审计报告  

**回滚**：备份还原；或按审计 before 将 `status` 写回 `reserved`（不恢复已过期预留为 active）。

---

## 4. 防止未来重复（方案比较，未改扫描器）

| 方案 | 内容 | 风险 | 建议 |
|---|---|---|---|
| **A. 统一锁顺序** | `_load_app` 改为不先锁申请；employee→beds→app/res/acc 全路径统一 | 改动 confirm/reserve/cancel/transfer，需全量并发测试 | **中期首选** |
| **B. 扫描器条件 UPDATE** | 过期时 `UPDATE apps SET status=approved WHERE id=? AND status='reserved'` 不 `FOR UPDATE` | 与 confirm 竞态下可能短暂双写；需幂等 | 可作过渡，须补并发测试 |
| **C. 补偿任务** | 独立低频 job 修复 reserved+无有效预留 | 只治已产生数据，不堵源头 | 与 A/B 搭配 |
| **D. 状态机显式迁移** | 增加 `reserved --expire--> approved` 并在 expire 事务内完成 | 仍受锁序约束 | 随 A 一起做 |

**结论**：在无完整并发测试前，**不**改扫描器写申请状态（HOTFIX-06 已验证会死锁）。先做补偿/修复脚本 + 方案 A 立项。

---

## 5. 隔离测试库演练结果

```text
库：dms_hotfix07_drill（Alembic 0001→0006）
命令：
  export MYSQL_DATABASE=dms_hotfix07_drill ...
  .venv/bin/alembic upgrade head
  .venv/bin/python scripts/drill_hotfix07_isolated.py
结果：DRILL_OK（12/12 PASS）
```

| 场景 | 结果 |
|---|---|
| S1 正常预留过期 | PASS（res=expired，app 仍 reserved=缺陷复现） |
| S2 过期 vs 确认并发 | PASS（无死锁崩溃） |
| S3 重复过期扫描 | PASS（幂等） |
| S4 修复 dry-run → apply → 再 apply | PASS（2 修、0 二修） |
| S5 保护已入住 | PASS（active 住宿保留） |
| S4 历史预留保留 | PASS（expired 行未删） |
| S4 修复后 app=approved | PASS |

API/床位状态：修复仅动申请状态，床位仍由预留/住宿表决定，报表口径不变。

---

## 6. 拟修改文件与迁移

| 文件 | 阶段 | 说明 |
|---|---|---|
| `scripts/classify_stale_reserved_apps.py` | 已存在 | 只读分类 |
| `scripts/repair_stale_reserved_apps.py` | 草稿 | 仅隔离/授权后 |
| `scripts/check_accommodation_consistency.py` | 已存在 | 一致性复核 |
| 扫描器 / 状态机 | **本阶段不改** | 待方案 A+B 并发测试 |
| 数据库迁移 | **不需要** | 仅数据修复，无 DDL |

---

## 7. 正式数据修复前置条件与回滚

见 §3.4。**当前正式库未做任何修复写操作。**

---

## 8. 遗留风险

1. C5 共 14 条（reserved+cancelled 预留）须人工审审计后单独策略。  
2. 分类计数随测试/业务继续漂移，执行前必须重跑。  
3. 方案 A/B 未实施前，过期后申请仍可能短暂停留 `reserved`（展示为未分配）。  
4. 修复脚本 `--apply` 在正式库执行必须获 GPT Web / 业主书面授权。

---

## 9. 交付声明

- 仅分析、只读、隔离库演练；**未修改正式业务数据**。  
- **不宣布发布**。待 GPT Web 审核后决定是否授权正式修复。

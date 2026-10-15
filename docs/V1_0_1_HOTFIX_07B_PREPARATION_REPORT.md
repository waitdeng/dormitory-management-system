# DMS V1.0.1 HOTFIX-07B 历史数据修复准备报告

> **【状态变更 · 根据用户决定取消】**（2026-10-15）  
> 用户确认当前库内员工/宿舍/入住/预留/调宿/退宿数据均为**开发测试数据**，项目完成后将**全新空库部署**并录入真实业务数据。  
> - **取消** HOTFIX-07B 历史数据修复与正式执行；**不**对 C1/C5 做批量 UPDATE/DELETE。  
> - **不是**「修复失败」，也**不是**「测试通过后完成」——而是**范围取消**。  
> - HOTFIX-07A 的预留过期状态同步修复**保留**；全部自动化/并发测试**保留**。  
> - 后续重点：全新隔离库部署演练、全业务流程测试、V1.0.1 最终验收（待 GPT Web）。  
> - 调宿锁序风险继续记录，正式验收前专项测试。


> 日期：2026-10-15  
> 范围：重新分类 · 隔离库修复演练 · 调宿锁序审查 · **正式执行安全清单**  
> **禁止事项已遵守：未对正式业务库执行 UPDATE/DELETE/批量修复。**  
> 正式修复须用户另行明确授权；本报告交 GPT Web 复核。

---

## 1. 最新异常分类

### 1.1 正式/当前业务库（只读）

| 项 | 值 |
|---|---|
| 分类时间 | 2026-10-15 |
| 环境 | `MYSQL_HOST=127.0.0.1` / 库 `dms`（Docker MySQL 8.0） |
| 脚本 | `scripts/classify_stale_reserved_apps.py` + `check_accommodation_consistency.py` |

| 类别 | 数量 | 脱敏样例 |
|---|---|---|
| **C1** reserved + expired，无有效住宿、无冲突 | **113** | `app#95/CA-...-74BE/E_******23` … `app#203/...` |
| C2 员工已有有效住宿 | 0 | — |
| C3 其他有效预留 | 0 | — |
| C4 调宿/退宿/再申请 | 0 | — |
| **C5** reserved + 预留 cancelled | **18** | `app#1234/CA-...-5828/E_******a0/res=['cancelled']` |
| 无法自动判断 | 0 | — |
| **stale 合计** | **131** | |

> C5 **禁止自动修复**。C1 在正式执行前必须以执行时刻清单为准（数量会变）。

### 1.2 备份恢复隔离库快照

| 项 | 值 |
|---|---|
| 来源 | `backups/dms_20261013T165238Z.sql.gz` → 库 `dms_hotfix07b_restore` |
| 申请/预留行数 | 746 / 702 |
| 恢复后 C1 | **39** |
| 恢复后 C5 | **0**（该备份时点） |

---

## 2. 隔离数据库修复演练（备份恢复库）

```text
export MYSQL_DATABASE=dms_hotfix07b_restore ...
.venv/bin/python scripts/repair_stale_reserved_apps.py           # dry-run
.venv/bin/python scripts/repair_stale_reserved_apps.py --apply
.venv/bin/python scripts/repair_stale_reserved_apps.py --apply   # 幂等
.venv/bin/python scripts/classify_stale_reserved_apps.py
.venv/bin/python scripts/check_accommodation_consistency.py
```

| 步骤 | 结果 |
|---|---|
| dry-run | 列出 39 条 C1，`repaired=39 skipped=55`（含非 C1 跳过） |
| apply | **修复 39**；`status reserved→approved` |
| 重复 apply | **repaired=0**（幂等） |
| 修复后分类 | C1=0，TOTAL_STALE=0 |
| 一致性脚本 | **TOTAL_ANOMALIES=0** |
| `assigned_bed_id` 保留 | approved 且仍带 assigned=**39** |
| 过期预留历史 | **39** 条 `expired` 仍在 |
| 正常入住 | active accommodation **418** 未减 |
| 调宿/退宿 | transfers **55** / checkouts **267** 不变 |
| 业务变化跳过 | 修复时条件重检；非 C1 skip 55 |
| 回滚设计 | 须检查修复后是否有新业务；禁止无条件 `approved→reserved` |

**修复前后数量（恢复库）**：stale 39 → 0。

---

## 3. 调宿加锁顺序专项审查

### 3.1 现状

| 路径 | 当前锁序 | 与规范 |
|---|---|---|
| `reserve_target` / `complete_transfer` | **`_load_tr` FOR UPDATE（业务行）** → `lock_employee` → `lock_beds` | **不一致** |
| `confirm_checkin`（07A 已修） | employee → bed → application | 一致 |
| 扫描过期（07A） | employee → bed → reservation → application | 一致 |
| 退宿 complete | employee → bed → records | 基本一致 |

### 3.2 潜在死锁路径

| 路径 | 场景 | 风险 |
|---|---|---|
| D1 | `complete_transfer` 与 `confirm_checkin`/`cancel` 并发 | **中**：transfer 先锁 TR 行，checkin 先锁 employee；若交叉再取对方已占资源可成环 |
| D2 | `reserve_target` 与扫描 expire | **低–中**：扫描 employee→bed→res；transfer TR→emp→bed |
| D3 | 双 transfer 同员工 | 低（open-transfer 业务互斥） |

受影响业务：调宿预留/完成、入住确认、预留过期扫描。

### 3.3 专项并发测试（未改状态机）

`tests/test_v101_hotfix07b_transfer_locks.py` **4 passed**：
- complete_transfer vs checkout：无死锁；active 住宿 ≤1  
- reserve_target vs expire scan：active 预留 ≤1；源床仍占用  
- 同员工双 transfer 竞态：open transfer ≤1  
- 调宿完成后扫描：当前床正确，历史保留  

**结论**：当前业务互斥下风险可控；**不**在本阶段大范围改调宿锁序。建议后续将 `_load_tr` 改为 peek + employee/bed 后再锁 TR（与 07A 同模式），并跑 `test_p1_003` + 本套件。

---

## 4. 正式修复执行安全清单（须另行授权）

| # | 项 | 要求 |
|---|---|---|
| 1 | 备份 | `scripts/backup.sh` 全量，记录文件哈希与时间 |
| 2 | 恢复验证 | 恢复到 `dms_hotfix07b_restore_YYYYMMDD`，行数/抽样一致 |
| 3 | 维护窗口 | 业务低峰；暂停批量导入/分床高峰操作 |
| 4 | 授权 | 业主/GPT Web 书面授权 + 操作人/复核人双人 |
| 5 | dry-run | 再次 `classify` 冻结 C1 清单 → `repair --dry-run` 人工抽查 ≥20 条 |
| 6 | 执行 | `repair --apply` 单行事务 + 审计 `application.repair_stale_reserved` |
| 7 | 复核 | `check_accommodation_consistency` C1=0；床位/入住列表抽查；报表抽样 |
| 8 | 停止条件 | 任一行失败率 >0、死锁超时、审计写失败、C2–C5 被误触 → **立即停止** |
| 9 | 恢复 | 备份还原；或仅对审计 before 记录且**无新业务**的行 `approved→reserved`；有后续业务禁止逆向 |
| 10 | C5 | **不执行**，单独人工工单 |

**执行命令（示意）**：
```text
cd backend && .venv/bin/python scripts/classify_stale_reserved_apps.py > /tmp/c1.txt
.venv/bin/python scripts/repair_stale_reserved_apps.py
.venv/bin/python scripts/repair_stale_reserved_apps.py --apply
.venv/bin/python scripts/check_accommodation_consistency.py
```

---

## 5. 测试汇总（本阶段）

| 命令 | 结果 |
|---|---|
| `pytest -q` | **167 passed** |
| `npm test` / `typecheck` | **5 passed** / 0 error |
| `playwright test --workers=2` | **18 passed** |
| 隔离修复演练 | 39→0，幂等，历史完整 |

---

## 6. 遗留风险

1. 正式库 C1=113 / C5=18 **尚未修复**（本阶段禁止）。  
2. 调宿 `_load_tr` 锁序未改，存在 D1/D2 理论死锁路径。  
3. 执行时刻分类会漂移，必须以冻结清单为准。

---

## 7. 交付声明

- 只读分类 + **备份恢复隔离库**演练 + 锁序审查；正式数据零写入。  
- **不宣布 V1.0.1 发布**；正式修复待用户明确授权 + GPT Web 复核。

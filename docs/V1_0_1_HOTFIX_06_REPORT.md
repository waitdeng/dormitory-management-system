# DMS V1.0.1 HOTFIX-06 报告 — 入住管理床位关联异常（P0）

> 日期：2026-10-15  
> 类型：数据一致性 / 展示关联专项  
> 约束：只读核查历史数据；不批量改写正式业务数据；**未经 GPT Web 复核不得宣布发布**。

---

## 1. 问题复现与根因

### 复现
入住管理列表：点击「分床」后床位列仍「未分配」；「确认入住」后状态为已入住，床位列仍「未分配」。

### 根因（展示层关联缺失，非虚构数据）
| 层 | 结论 |
|---|---|
| 数据库 | 预留/入住事务正确：`bed_reservations` / `accommodation_records` 有记录（抽样 app#17、#1 证实） |
| **API** | `list_applications` 只返回 `_app_out`，**不包含 `bed`**；仅 `get_application` 详情在 `assigned_bed_id` 上拼床 |
| 前端 | `CheckinsView` 读 `row.bed`，列表恒为「未分配」 |

另发现口径问题：
- **调宿后**不应显示原床，应以 **active accommodation.bed_id** 为准。
- **已预留但预留已过期**不得继续当作有效床位展示。
- **已退宿**历史申请保留可追溯床位路径，但不代表当前占用。

---

## 2. 修复内容

| 文件 | 变更 |
|---|---|
| `backend/app/services/checkin_service.py` | 新增 `_bed_chain_dict` / `_resolve_app_bed_id` / `_attach_bed`；**列表与详情共用** |
| | 展示优先级：active 住宿床（调宿后当前床）→ active 预留床 → 已入住历史床（可追溯）→ `reserved` 无有效预留 → `null`（未分配） |
| | `bed_path` = 区域/楼栋/楼层/房间号/床位号 |
| `frontend/src/views/checkins/CheckinsView.vue` | 床位列输出 `bed_path`（完整路径） |
| `frontend/src/types/index.ts` | `CheckinApplicationOut.bed` 增加 `floor_no`/`bed_path` |
| `backend/scripts/check_accommodation_consistency.py` | **只读**一致性检查（脱敏工号） |
| `backend/services/scanner_service.py` | 评估过期预留回写申请状态会与 `confirm_checkin` 的 `_load_app FOR UPDATE` 锁序冲突（`test_p1_003` 死锁），**不在扫描器改申请状态**；展示层按无有效预留处理 |

**未使用**前端伪造床位或隐藏「未分配」掩盖问题；未改业务状态机事务语义（确认/预留仍以 DB 为准）。

---

## 3. 历史数据一致性检查（只读）

```text
cd backend && .venv/bin/python scripts/check_accommodation_consistency.py
```

| 类别 | 数量 | 说明 |
|---|---|---|
| reserved 申请无有效预留 | **109** | 抽样 `res_statuses=['expired']`：预留已过期但申请仍 `reserved`（历史脏状态） |
| checked_in 无任何住宿记录 | 0 | — |
| active 住宿缺床位 | 0 | — |
| 同一床位多条 active 住宿 | 0 | — |
| 状态不一致（其它） | 0 | — |
| checked_in 仅历史 ended 住宿 | 205 | **正常**（退宿/调宿后历史），不计入异常 |

**未自动清理。** 历史 109 条修复方案（待审核）：
1. 提取 `status=reserved` 且无 `active` 预留的申请列表（脚本已可输出脱敏 ID）。
2. 若存在 `expired` 预留：将申请回置 `approved` 并清空 `assigned_bed_id`（与展示口径一致）。
3. 全程审计 `application.repair_stale_reserved`；单行事务；可回滚脚本 + 备份。
4. 修复后复跑 `check_accommodation_consistency.py` 至 `TOTAL_ANOMALIES=0`。

---

## 4. 测试

### 后端（真实 MySQL）
```text
cd backend && .venv/bin/python -m pytest tests/test_v101_hotfix06_bed_association.py -q
→ 4 passed
```

| 用例 | 覆盖 |
|---|---|
| reserve/checkin 列表床位列 | 审批未分配 → 预留完整路径 → 已入住仍显示 |
| API/DB 一致 | 列表床与 `room/beds` occupied 一致 |
| 调宿后 | 显示目标新床，不回退原床 |
| 过期预留 | 不展示为有效床位 |

### Playwright
```text
cd frontend && ./node_modules/.bin/playwright test e2e/hotfix06-checkin-bed.spec.ts
→ 1 passed
```

浏览器验证：申请→审批「未分配」→ 预留后显示完整路径 → 确认入住 → 刷新后床位仍正确。

### 全量回归（未删改既有用例）
```text
cd backend && .venv/bin/python -m pytest -q     → 154 passed
cd frontend && npm test                        → 5 passed
cd frontend && npm run typecheck               → 0 error
cd frontend && ./node_modules/.bin/playwright test --workers=2 → 18 passed
```

（含并发分床、重复确认、BUG-007 过滤、M6 真实分床流。）

---

## 5. 对既有业务数据的影响

- **无写操作**进入正式库（除测试隔离数据）。
- 历史申请/住宿/预留记录未修改。
- 109 条历史「reserved+expired」仅被脚本读出，待修复方案批准后再处理。

---

## 6. 遗留风险

1. **109 条历史 reserved+expired** 需人工审核后按 §3 方案修复；当前 UI 对其显示「未分配」，不虚构床位。  
2. 扫描器不回写申请状态，避免死锁；若未来要自动回置，须统一申请表锁序（与 `confirm_checkin._load_app` 一并改造）。  
3. 列表床位解析多 1～2 次查询，分页 20 影响可忽略（未做批量 join 优化）。

---

## 7. 交付说明

- 三层（API / DB / 浏览器）已核对一致。  
- **不宣布 V1.0.1 发布**；提交 GPT Web 复核。

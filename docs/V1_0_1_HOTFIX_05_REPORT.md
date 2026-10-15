# DMS V1.0.1 HOTFIX-05 报告（含 BUG-014 筛选规则变更）

> 日期：2026-10-15  
> 覆盖：HOTFIX-05 交互项 + **BUG-014 候选员工人事状态规则（用户最终确认，覆盖旧规则）**  
> 范围限制：仅可视化分床「新增入住分配」入口；**不**改全系统人事状态字典，**不**改既有员工历史数据。

---

## 1. BUG-014 业务规则（最终生效）

「选择待入住员工」弹窗候选必须**同时**满足：

| # | 规则 | 实现层 |
|---|---|---|
| 1 | `employment_status = active` | 后端查询 + 前端查询参数 |
| 2 | `accommodation_required = true` | 同上 |
| 3 | 排除已有有效住宿记录 | `accommodation_status=allocatable` 子查询 |
| 4 | 排除冲突有效床位预留 | 同上 |
| 5 | 排除已停用/已删除员工 | **系统无 is_deleted/停用标记**（仅人事状态与住宿状态）；N/A |
| 6 | `pending/probation/offboarding/terminated/resigned/suspended` 不得入选 | 强制 `employment_status=active` |
| 7 | 后端候选 API 同等过滤 | `list_employees(employment_status=active, accommodation_status=allocatable, accommodation_required=true)` |
| 8 | 实际分床再次校验资格 | `occupancy.assert_eligible_for_new_checkin`（申请/预留/确认） |
| 9 | 搜索仅在合格集合内 | keyword 与 allocatable 过滤同查询 |
| 10 | 状态列 `active` → 「在职」 | 前端展示映射 |

**HOTFIX-05 交互（保持）**
- 删除弹窗右上角「确认分配」
- 仅保留**底部**「确认分配」
- 点床后直接选人确认，无需二次点击床位

---

## 2. 根因与变更

### 根因
- 候选列表原先 `accommodation_status=not_in_dorm` + `accommodation_required=true`，**未限制在职**，`probation/pending/...` 会出现在弹窗。
- 后端分床未强制 `employment_status=active`，存在绕过前端风险。
- 弹窗右上角与底部各有一个「确认分配」。

### 代码变更

| 文件 | 变更 |
|---|---|
| `backend/app/services/employee_service.py` | 新增 `accommodation_status=allocatable`：在职 + 需住宿 + 无 active 入住 + 无 active 预留 |
| `backend/app/services/occupancy.py` | `assert_eligible_for_new_checkin`：仅 **active** 且需住宿可新增分床；`assert_accommodation_required` 仍供调宿使用（不误伤已入住调宿） |
| `backend/app/services/checkin_service.py` | 申请/预留/确认改为 `assert_eligible_for_new_checkin` |
| `frontend/src/views/allocation/BedAllocationView.vue` | 查询 `allocatable + active + required`；状态列「在职」；**去掉右上角确认按钮** |

未修改：人事状态枚举、员工主数据、历史住宿/预留记录。

---

## 3. 测试证据

### 后端（真实 MySQL）
```text
cd backend && .venv/bin/python -m pytest tests/test_v101_hotfix05_bug014.py -q
→ 4 passed
```

| 用例 | 断言 |
|---|---|
| `test_bug014_candidates_only_active_needing_housing` | 6 类非 active 与不需住宿均不在候选；在职需住宿在候选 |
| `test_bug014_exclude_housed_and_reserved` | 已入住/已预留排除，空闲在职保留 |
| `test_bug014_backend_blocks_non_active_allocation` | probation 创建申请被拒 |
| `test_bug014_search_scoped_to_candidates` | 搜索结果不含停职员工 |

### Playwright
```text
cd frontend && ./node_modules/.bin/playwright test e2e/hotfix05-bug014.spec.ts
→ 1 passed
```

覆盖：弹窗无右上确认（仅 1 个「确认分配」）· 仅出现在职甲不含试用乙 · 状态显示「在职」· 底部确认一次分配成功。

### 全量回归（非仅新增）
```text
cd backend && .venv/bin/python -m pytest -q
→ 150 passed

cd frontend && npm test          → 5 passed
cd frontend && npm run typecheck → 0 error
cd frontend && ./node_modules/.bin/playwright test --workers=2
→ 17 passed（m5×3、m6×3、v101×3、remediation×2、hotfix04×4、bug014×1 等）
```

> 并行 E2E 曾出现 1 次 UX-012 资源竞争抖动，串行/复跑通过；建议 CI `workers≤2`。

---

## 4. 权限与绕过防护

| 路径 | 防护 |
|---|---|
| 候选列表 API | 服务端过滤 allocatable + active + required |
| 入住申请 / 预留 / 确认 | `assert_eligible_for_new_checkin` |
| 批量分床导入 | 预览拒绝 + 服务层资格校验（沿用 BUG-007 通道） |
| 调宿 | **不受影响**（已入住员工调宿不强制 active，避免误伤） |

---

## 5. 遗留风险

1. 员工表无独立「停用/软删」字段，规则 5 按 N/A 处理；若未来增加标记需并入 allocatable 查询。  
2. `allocatable` 为专用过滤值，与既有 `not_in_dorm` 并存；其他页面未强制改用。  
3. 并行 Playwright 偶发抖动（见上）。

---

## 6. 交付说明

- 本文件同步 BUG-014 最终规则与验收测试；**不宣布正式发布**。  
- 提交 GPT Web 复核。

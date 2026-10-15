# DMS V1.0.1 HOTFIX-04 整改报告

> 日期：2026-10-15  
> 范围：FIX-009 · FIX-010 · UX-011 · UX-012  
> 约束：不重新初始化、不推翻既有修复、不破坏历史数据；不使用 Git；**未经 GPT Web 复核不得宣布发布**。

---

## 0. 总览

| 项 | 根因 | 结论 | 证据 |
|---|---|---|---|
| FIX-009 层级编辑/删除 | 楼层无编辑入口；床位无编辑/删除；删除保护后被床位弹窗遮挡 | **已修复** | 后端 2 + Playwright 1 |
| FIX-010 房型删除 | 仅停用无删除；无引用检查 API | **已修复** | 后端 3 + Playwright 1 |
| UX-011 分床筛选 | 无筛选栏，仅按楼层加载 | **已修复** | Playwright 1 |
| UX-012 点床分配 | 必须先选人再点床，冗余二次点击 | **已修复** | 后端 1 + Playwright 1 + M6 流程适配 |

**全量回归（M1～M6 + V1.0.1 + HOTFIX-04）**：

| 范围 | 命令 | 结果 |
|---|---|---|
| 后端 pytest | `cd backend && .venv/bin/python -m pytest -q` | **146 passed** |
| 前端 Vitest | `cd frontend && npm test` | **5 passed** |
| 类型检查 | `npm run typecheck` | **0 error** |
| 构建 | `npm run build` | **成功** |
| Playwright | `./node_modules/.bin/playwright test --workers=2` | **16 passed** |

---

## 1. FIX-009 宿舍层级编辑与删除

### 现状与根因
- 树工具栏仅有区域/楼栋编辑；**楼层编辑接口存在但无入口**。
- 床位对话框仅启停/维修，**无编号/备注编辑与删除**。
- 点击房间会打开床位弹窗，遮挡「删除节点」按钮（测试暴露的交互问题）。

### 变更
| 文件 | 内容 |
|---|---|
| `frontend/src/views/dormitories/DormitoriesView.vue` | 增加「编辑楼层」「编辑房间」；床位编辑/删除；删除前 `ElMessageBox` 二次确认 |
| | 编辑保存后 `loadTree()` + `loadRooms()` 自动刷新 |
| | 删除复用后端 `delete_*`：子级/占用/预留/历史阻断，提示停用 |
| `frontend/src/api/dormitories.ts` | `updateBed` |

后端删除与关联检查在 V1.0.1 已实现（`dorm_service.delete_*` + `_has_child_or_business_refs`），本轮未改语义：**有业务关联拒绝物理删除，提示停用；不级联删除历史**。

### 测试
- `tests/test_v101_hotfix04.py::test_fix009_delete_bed_and_room_with_refs`
- Playwright `hotfix04.spec.ts` FIX-009：编辑楼层后树刷新；删有床房间被拒且节点仍在。

---

## 2. FIX-010 房型删除

### 根因
仅提供停用；无 DELETE API/按钮；前端无法清理无用字典。

### 变更
| 文件 | 内容 |
|---|---|
| `backend/app/services/dorm_service.py` | `delete_room_type`：`DormRoom.room_type` 引用计数 >0 → `BusinessRuleError` 提示停用 |
| `backend/app/api/v1/endpoints/dormitories.py` | `DELETE /room-types/{type_id}`，权限 `dorm:update` |
| `DormitoriesView.vue` | 列表「删除」+ 二次确认；删除/停用后 `loadRoomTypes()` 刷新选择列表 |

历史房间保留原 `room_type` 字符串，展示仍正确（`type_name` 映射失败时回退 code）。

### 测试
- 无引用可删 / **被引用禁止删除并提示停用** / finance_viewer **403**
- Playwright：UI 删除被引用房型出现「引用/停用」提示且列表仍在

---

## 3. UX-011 可视化分床筛选

### 根因
仅能按树选择楼层加载 room-cards，无状态/关键词/房型/性别筛选。

### 变更（`BedAllocationView.vue`）
- 筛选：床位状态、性别政策、房型、房间号/床位号关键词；**一键重置**。
- 统计条：房间数 / 床位数 / 空闲数与筛选结果一致。
- 树点选楼层/房间同步筛选上下文；watch 单次加载，**无重复请求**（BUG-003 保持）。
- 筛选仅影响展示，**不改数据库床位状态**。
- 数据仍走既有 API（数据范围/权限与 room-cards 一致）。

### 测试
Playwright：空闲筛选 + 关键词 + 重置。

---

## 4. UX-012 床位分配交互

### 根因
`allocateBed` 要求已选员工，否则只打开员工弹窗；必须**再次点床**才分配。

### 目标流程实现
1. 点击空闲床 → 记录 `targetBed`，打开员工弹窗  
2. 弹窗标题区显示**目标床位完整路径**  
3. 员工列表：`accommodation_required=true` 且 `not_in_dorm`（BUG-007），支持姓名/工号/部门搜索  
4. 单击员工高亮选中（radio）  
5. 右上角与底部「**确认分配**」按钮；未选人或请求中禁用  
6. 确认后仅对 `targetBed` 走 **申请→批准→预留→确认**（复用状态机与权限）  
7. 成功关闭弹窗并刷新  
8. 失败保留床位与已选员工 + 明确错误  
9. **409 冲突**提示并刷新该床状态  
10. **不**在前端直接改床位状态模拟成功  

### 测试
- 后端 `test_ux012_allocation_state_machine_no_frontend_simulation`（状态机/BUG-007/抢床）
- Playwright UX-012：点床 → 弹窗路径 → 禁用确认 → 选人 → 一次确认成功
- **M6 既有 3 条 E2E** 步骤按新交互更新（保留原断言：成功刷新 / 停用不可分 / 409 冲突），非删除用例

---

## 5. 实际执行的测试命令

```text
cd backend && .venv/bin/python -m pytest -q
→ 146 passed

cd backend && .venv/bin/python -m pytest tests/test_v101_hotfix04.py -q
→ 5 passed

cd frontend && npm test                 → 5 passed
cd frontend && npm run typecheck        → 0 error
cd frontend && npm run build            → success
cd frontend && ./node_modules/.bin/playwright test --workers=2
→ 16 passed（含 m5×3、m6×3、v101×3、remediation×2、hotfix04×4、reports 等）
```

Trace/截图：失败时由 Playwright 保留 `test-results/**/trace.zip`（最终全绿）。

---

## 6. 已修复问题

| ID | 描述 |
|---|---|
| FIX-009 | 层级编辑入口不全、床位不可编辑删除、删除入口被弹窗遮挡 |
| FIX-010 | 房型不可删除、无后端引用保护 |
| UX-011 | 分床页无组合筛选与统计 |
| UX-012 | 先选人再点床的冗余步骤；分配需二次点击床位 |

---

## 7. 遗留风险

1. **测试库树节点极多**：区域需逐级展开；超大实例可考虑懒加载树（本轮未做）。  
2. **并行 E2E 偶发 API 登录失败**：建议 `--workers≤2` 或 CI 加重试。  
3. **筛选为前端组合过滤**：跨楼层全局搜索需后端查询（本轮按楼层/房间粒度）。  
4. **M6 E2E 步骤已适配 UX-012**，断言未削弱；若 GPT Web 要求保持旧点击顺序，需产品确认交互变更。

---

## 8. 交付说明

- 本报告为 HOTFIX-04 自检记录，**不宣布正式发布**。  
- 未执行项不标记通过；数字均来自上表命令真实输出。  
- 提交 GPT Web 复核。

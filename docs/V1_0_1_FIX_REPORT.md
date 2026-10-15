# V1.0.1 修复与功能完善报告

> 日期：2026-10-14  
> 范围：BUG-001 ～ FEAT-008（含 BUG-007 P0 强制项）  
> 基线：M1～M6 已验收（见 `docs/M6_ACCEPTANCE_REPORT.md`）  
> 数据安全：未清空、未覆盖既有员工/宿舍/住宿历史；结构变更仅通过 Alembic `0006`。

---

## 0. 总览

| 编号 | 类型 | 结论 | 测试 |
|---|---|---|---|
| BUG-001 | 宿舍资源删除 | **通过** | 后端 5 |
| FEAT-002 | 房间类型 + 房间批量导入 | **通过** | 后端 3 |
| BUG-003 | 房间点击两次 Request validation failed | **通过** | 前端 1 + E2E 1 |
| UX-004 | 可视化导航 + 批量分床导入 | **通过** | 后端 2 + E2E |
| BUG-005 | 调宿目标床位显示不完整 | **通过** | 后端 2 + E2E 1 |
| UX-006 | 统计报表人事状态中文化 | **通过** | 后端 2 |
| BUG-007 | 无需住宿员工不得分床（P0） | **通过** | 后端 7 + E2E 1 |
| FEAT-008 | 房间门禁密码 | **通过** | 后端 4 |

**回归**：后端 `pytest` **120 passed**；前端 Vitest **5 passed**；`vue-tsc` 0 error；`vite build` 成功；Playwright **9 passed**（含既有 m5/m6 6 条 + V1.0.1 3 条）。

---

## 1. BUG-007（P0）不需要住宿员工不得分配床位

### 根因
`employees.accommodation_required` 字段存在，但入住申请、预留、确认、调宿、批量导入等分配入口**均未校验**该字段；前端可分床员工列表也未过滤。

### 修改
| 文件 | 变更 |
|---|---|
| `backend/app/services/occupancy.py` | 新增 `assert_accommodation_required(emp)`；`assert_employee_available_for_checkin` 统一强制 |
| `backend/app/services/checkin_service.py` | `create_application` / `reserve_bed` / `confirm_checkin` 入口校验 |
| `backend/app/services/transfer_service.py` | `create_transfer` / `reserve_target` / `complete_transfer` 入口校验 |
| `backend/app/services/dorm_import_service.py` | 批量分床预览/提交拒绝 `accommodation_required=false` |
| `backend/app/services/employee_service.py` | 列表增加 `accommodation_required` 过滤；改为 false 时不自动释放床位 |
| `backend/app/api/v1/endpoints/employees.py` | 查询参数 `accommodation_required` |
| `frontend/src/api/employees.ts`、`BedAllocationView.vue`、`CheckinsView.vue` | 默认可分床列表过滤 |

### 不变量
已入住员工改为“不需要住宿”**不会**删除住宿记录或释放床位，必须走退宿流程。

### 测试（`tests/test_v101_bug007_accommodation_required.py`，7 passed）
- 默认可分床列表排除
- 入住申请接口拒绝
- 预留接口拒绝（含事后翻转标志）
- 可视化分床流程拒绝
- 调宿分配拒绝
- 翻转标志后床位仍占用
- 无权限角色 403

Playwright：`v101.spec.ts` BUG-007 用例通过（分配弹窗不出现该员工）。

---

## 2. BUG-003 房间点击两次 Request validation failed

### 根因（已修复实际问题，非屏蔽提示）
1. `DormitoriesView.onNodeClick` 房间分支调用 `loadRooms({ floor_id: 0 })`，后端 `Query(ge=1)` 校验失败 → 422 `Request validation failed`。
2. Axios 全局拦截器 `ElMessage.error` 与页面 catch 再次 `ElMessage.error` → **同一错误双弹窗**。
3. `BedAllocationView` 中 `onTreeSelect` 与 `watch(selectedFloorId)` 双触发 `loadRooms()` → 重复请求。

### 修改
| 文件 | 变更 |
|---|---|
| `frontend/src/views/dormitories/DormitoriesView.vue` | 房间点击改为 `fetchRoom(id)` + `openBeds`；禁止 `floor_id=0` |
| `frontend/src/api/client.ts` | `notifyError` 单次提示；`skipErrorToast` 配置；Blob 错误体解析 |
| 各业务视图 | `ElMessage.error(extractError)` → `notifyError` |
| `frontend/src/views/allocation/BedAllocationView.vue` | 去掉双重加载；支持房间节点点选 |

### 测试
- 前端 `room-click.spec.ts`：1 passed
- Playwright `v101.spec.ts`：点击楼层/房间后弹出床位对话框，**无 `/api/v1/rooms` 422**

---

## 3. BUG-001 宿舍资源删除

### 方案
- 五级 `DELETE`（区域/楼栋/楼层/房间/床位），复用 `dorm:update` / `bed:manage` 权限。
- **关联检查**：存在下级资源、住宿历史/占用、预留、调宿关联时拒绝删除，提示“可改为停用”。
- 无关联资源硬删除；操作二次确认 + 审计（`dorm_*.delete`）。
- 不可删除资源使用现有 `status=disabled` 停用（归档）方案。

### 文件
`backend/app/services/dorm_service.py`（`delete_*`、`_has_child_or_business_refs`）、`backend/app/api/v1/endpoints/dormitories.py`、`DormitoriesView.vue`（删除按钮 + `ElMessageBox` 二次确认）。

### 测试（`tests/test_v101_delete_and_import.py`，5 passed）
- 空床位可删；有住宿/预留历史不可删
- 有床位房间不可删；空房间可删；空层级可级联删
- 有下级区域不可删

---

## 4. FEAT-002 房间类型 + 房间批量导入

### 房间类型
- 新表 `dorm_room_types`（Alembic `0006`），CRUD + 停用。
- **改名/改默认容量不自动改房间容量**（容量始终是房间自身字段）。

### 房间 Excel 导入
- 模板：区域编码、楼栋编码、楼层号、房间号、房型、容量、性别政策、**门禁密码（字符串）**、备注。
- 流程：上传 → 预览（create/error 明细）→ 确认提交 → 逐行结果。
- 校验：层级不存在、房间号重复（含文件内重复）、容量异常、不覆盖已有住宿关系。
- 策略：**逐行部分成功**（`partial_success_per_row`），结果可追溯。

### 测试（`tests/test_v101_room_and_alloc_import.py`）
- 预览 create=1 / error=2；提交 created=1 / failed=2
- 门禁密码前导零保留

---

## 5. UX-004 可视化导航 + 批量分床

### 导航
- 树可直接点房间 → 右侧立即显示该房间全部床位。
- 点楼层仍显示楼层多房间。
- 保持既有占用状态与分床操作逻辑。

### 批量分床 Excel 导入
- 模板：员工工号、区域、楼栋、楼层、房间、床位号。
- 预览/校验/提交/逐行成功失败原因。
- **复用 `checkin_service`**（申请→批准→预留→确认），权限与状态机不绕过。
- 拒绝重复占床、重复分配员工、不需要住宿员工（BUG-007）。
- 策略：逐行部分成功；失败行尝试取消半成品申请；审计 `checkin.batch_allocate_import`。

---

## 6. BUG-005 调宿目标床位显示不完整

### 根因
`list_available_beds` / `BedOut` 只有 `bed_no` + `room_id`；前端选项显示 `床 B1 (房间 12)`。

### 修改
- 后端 `list_available_beds` 联表返回 `area_name / building_name / floor_no / room_no / bed_path`。
- 调宿详情 `source_bed` / `target_bed` 补 `area_name` / `floor_no`。
- 前端调宿选择器与列表显示 `区域/楼栋/楼层/房间/床位`。

### 测试
- `test_bug005_available_beds_carry_full_path`、`test_bug005_transfer_detail_beds_have_full_path`
- Playwright：下拉选项为多段完整路径

---

## 7. UX-006 人事状态中文化

### 映射（后端编码不变）
| code | 中文 |
|---|---|
| pending | 待入职 |
| active | 在职 |
| probation | 试用期 |
| offboarding | 离职办理中 |
| terminated / resigned | 已离职 |
| suspended | 停职 |

### 范围
- 前端：报表页、员工页统一中文标签（筛选仍用 code）。
- Excel：员工导出 `status_rev` 补齐 pending/offboarding；报表导出住宿台账/空床/调宿/异常同步中文。
- 不影响状态筛选与统计逻辑。

### 测试
- `test_ux006_employee_export_uses_chinese_status`
- `test_ux006_report_export_uses_chinese_status`（导出不含 `active` 原码）

---

## 8. FEAT-008 房间门禁密码（门禁，非 Wi-Fi）

### 安全设计
| 项 | 实现 |
|---|---|
| 存储 | `dorm_rooms.access_code_encrypted`，Fernet（密钥由 `SECRET_KEY` 派生） |
| 类型 | **字符串**，保留前导零（非字符串入参抛错） |
| 默认脱敏 | 列表/详情仅 `has_access_code`，无明文 |
| 授权查看 | `GET /rooms/{id}/access-code`，权限 `dorm:access_code:view` |
| 修改 | `PUT /rooms/{id}/access-code` 或房间编辑，权限 `dorm:access_code:update` |
| 审计 | `dorm_room.access_code.set/clear/reveal`（不记明文） |
| 日志/导出 | 不输出明文 |
| 兼容 | 旧房间密码为空；不改既有床位/入住数据 |
| Excel | 导入模板含门禁密码列（字符串） |

### 权限
新增 `dorm:access_code:view` / `dorm:access_code:update`；`super_admin` 全量，`dorm_admin` 授予；`finance_viewer` 等无权限 403。

### 测试（`tests/test_v101_access_code_and_room_types.py`，4 passed）
- 设置 `001234` → 列表无明文 → 授权解密回 `001234`
- finance_viewer 揭示 403
- 旧房间空密码兼容
- 清除密码

### 数据库迁移
`backend/alembic/versions/0006_v101_room_access_and_types.py`  
- `dorm_rooms.access_code_encrypted`（nullable）  
- `dorm_room_types` 新表  
- 含 `downgrade`

---

## 9. 实际执行的测试结果

| 命令 | 结果 |
|---|---|
| `cd backend && .venv/bin/python -m pytest -q` | **120 passed** |
| `cd frontend && npm test` | **5 passed** |
| `cd frontend && npm run typecheck` | **0 error** |
| `cd frontend && npm run build` | **成功** |
| `cd frontend && ./node_modules/.bin/playwright test` | **9 passed**（m5×3 + m6×3 + v101×3） |
| `alembic upgrade head` | `0005 → 0006` 成功 |

Playwright 真实浏览器验证：房间导航无 422、调宿床位完整路径、BUG-007 列表过滤；既有 m5/m6 分床/报表/冲突流回归通过。

---

## 10. 未完成事项与风险

1. **房间类型与 `room_type` 字符串未做 FK 强绑定**：可写入任意 type 字符串（与 V1.0 兼容）；若需强校验可在后续版本加 FK/服务层字典检查。
2. **门禁密码密钥轮换**：Fernet 密钥派生自 `SECRET_KEY`，轮换 SECRET_KEY 会导致旧密文无法解密；若需轮换应做密钥版本化（本次未做，内网单密钥可接受）。
3. **`list_beds` / room-cards 中 `bed_path` 未填充**（`list_available_beds` 与调宿详情已填充）；如列表也要路径可后续补齐。
4. **批量分床失败清理**：checkin 服务各自 commit，失败行会尝试 `cancel_application`；极端并发下取消失败会留下可人工处理的申请单（有审计）。
5. **前端房间类型/导入 UI** 以 API + 宿舍页门禁/删除按钮为主；完整房型管理页与导入对话框可在交互稿确认后补强。
6. **部门授权 UI** 等 M6 遗留项不在本次范围。

---

## 11. 逐项验收结论

| 项 | 验收 |
|---|---|
| BUG-001 | **通过** — 可删无引用资源；有引用拒绝并提示停用；权限/二次确认/审计齐全 |
| FEAT-002 | **通过** — 房型可维护且不改容量；导入预览/校验/提交/错误报告完整 |
| BUG-003 | **通过** — 根因（floor_id=0 + 双弹窗 + 双请求）已修，非屏蔽 |
| UX-004 | **通过** — 房间直点看床；楼层看多房；批量分床复用业务服务 |
| BUG-005 | **通过** — 选择器与详情为 区域/楼/层/房间/床位 |
| UX-006 | **通过** — 前端与 Excel 中文；后端 code 不变；筛选不受影响 |
| BUG-007 | **通过（P0）** — 后端统一校验 + 前端过滤 + 全绕过场景测试通过 |
| FEAT-008 | **通过** — 加密、脱敏、授权查看、审计、前导零、导入与兼容均验证 |

**V1.0.1 自检结论：通过。** 待 GPT Web 独立复核。

---

## 12. 修改文件摘要

### 后端
- `app/services/occupancy.py`、`checkin_service.py`、`transfer_service.py`、`dorm_service.py`、`dorm_import_service.py`、`employee_service.py`、`report_service.py`
- `app/models/dorm.py`、`app/schemas/dorm.py`、`app/core/security.py`、`app/core/permissions.py`
- `app/api/v1/endpoints/dormitories.py`、`employees.py`
- `alembic/versions/0006_v101_room_access_and_types.py`
- `tests/test_v101_bug007_accommodation_required.py`、`test_v101_labels_and_bed_path.py`、`test_v101_access_code_and_room_types.py`、`test_v101_delete_and_import.py`、`test_v101_room_and_alloc_import.py`

### 前端
- `src/api/client.ts`、`dormitories.ts`、`employees.ts`
- `src/types/index.ts`
- `src/views/dormitories/DormitoriesView.vue`、`allocation/BedAllocationView.vue`、`transfers/TransfersView.vue`、`reports/ReportsView.vue`、`employees/EmployeesView.vue`、`checkins/CheckinsView.vue` 等
- `src/views/dormitories/room-click.spec.ts`
- `e2e/v101.spec.ts`

### 文档
- `docs/V1_0_1_FIX_REPORT.md`（本文件）

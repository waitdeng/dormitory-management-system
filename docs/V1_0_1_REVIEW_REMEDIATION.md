# V1.0.1 复核补强报告（GPT Web 第一轮审查）

> 日期：2026-10-14  
> 依据：`docs/V1_0_1_FIX_REPORT.md` + GPT Web 第一轮独立审查意见  
> 范围：FEAT-002 前端补齐、UX-004 事务边界、FEAT-008 密钥分离与轮换  
> 约束：不重新开发已通过项；不使用 Git，不伪造 SHA/Tag；**未通过 GPT Web 再次复核前不宣布 V1.0.1 正式发布**。

---

## 0. 补强总览

| 项 | 审查意见 | 结论 | 测试 |
|---|---|---|---|
| FEAT-002 前端 | 房型字典维护 + 房间导入对话框 | **已完成** | Playwright 2 |
| UX-004 事务边界 | 失败行不得遗留无效预留/不可追溯状态 | **已加固** | 后端 4（含并发） |
| FEAT-008 密钥 | 与 JWT SECRET_KEY 分离 + 轮换迁移 | **已完成** | 后端 5 |

**全量回归**：后端 `pytest` **129 passed**（120 + 9 补强）· 前端 Vitest **5 passed** · `vue-tsc` 0 error · `vite build` 成功 · Playwright **11 passed**（m5×3 + m6×3 + v101×3 + remediation×2）。

---

## 1. FEAT-002 前端：房型维护 + 房间 Excel 导入对话框

### 问题
V1.0.1 已提供 `/room-types` 与 `/rooms/import/*` API，但网页无对应操作入口，行政人员必须调 API。

### 代码变更
| 文件 | 变更 |
|---|---|
| `frontend/src/views/dormitories/DormitoriesView.vue` | 新增「房型维护」「批量导入」入口与对话框 |
| | 房型：列表 / 新建 / 编辑 / 停用（二次确认）；容量提示“不会自动修改已有房间容量” |
| | 房间类型下拉改为动态读取房型字典（保留未知 code 显示） |
| | 导入：下载模板 → 选择 Excel → 上传预览（行级结果）→ 确认提交（二次确认）→ 显示 created/failed |
| | 导入表不展示明文门禁密码，仅显示“已填写/—” |
| `frontend/src/api/dormitories.ts` | 已有 `listRoomTypes/create/update/disable`、`preview/commitRoomImport`、模板下载 |

### 测试
**Playwright `e2e/v101-remediation.spec.ts`（2 passed）**
1. 房型创建 → 列表可见 → 编辑改名 → 停用（状态变为停用）
2. 房间导入：上传含 1 成功 + 1 重复房间 → 预览显示待创建/错误 → 提交 → 房间落库，**门禁密码 `0042` 前导零保留**

---

## 2. UX-004：批量分床事务边界与失败恢复

### 审查关注点
失败行是否遗留：无效有效预留、重复占床、不可追溯业务状态。

### 代码变更（`backend/app/services/dorm_import_service.py`）
1. **行前 `db.rollback()`**：丢弃上一行脏事务，保证行隔离。
2. **失败三级恢复**：
   - `cancel_application`（会释放该申请 active 预留）
   - 若取消失败 → `_release_orphan_reservation` 强制释放该员工残留 active 预留（审计 `checkin.batch_allocate_import.recovery`）
   - 仍失败则 `recovery=cancel_failed: ...`，行级可追溯
3. **逐行结果**：每行含 `action` / `message` / `recovery`（`none` | `application_cancelled` | `reservation_released` | `rollback_only` | `cancel_failed: ...`）。
4. **策略字段**：响应 `strategy=partial_success_per_row`；汇总含 `succeeded/failed/recovered/total`。
5. **业务状态机不绕过**：仍走 `create_application → approve → reserve → confirm`（BUG-007、占床唯一、并发 409 均在服务内强制）。

### 测试（`backend/tests/test_v101_remediation.py`，相关 4 条）
| 场景 | 结果 |
|---|---|
| 部分失败（1 成功 + 1 不需住宿） | succeeded=1 / failed=1；失败床 **available=true**，无孤儿预留；每行有 recovery |
| 重复提交同一批 | 第二次 succeeded=0，不双占 |
| 并发抢同一床（两批同时提交） | **仅 1 成功**（`s1+s2==1`） |
| 行级 message/recovery 齐全 | 通过 |

---

## 3. FEAT-008：门禁密码密钥与 JWT 分离 + 轮换

### 原问题
Fernet 密钥由 `SECRET_KEY` 派生；轮换 JWT 密钥会导致门禁密码无法解密。

### 方案
| 项 | 实现 |
|---|---|
| 主密钥 | `ACCESS_CODE_ENCRYPTION_KEY`（独立 Fernet；未配置时回退 SECRET_KEY 派生，兼容旧部署） |
| 仅解密旧钥 | `ACCESS_CODE_LEGACY_SECRETS`（逗号分隔；`SECRET_KEY` 字面量表示纳入 JWT 密钥）+ 自动尝试 SECRET_KEY |
| 密文格式 | `v2:<fernet>`；兼容无前缀 / `v1:` 旧密文 |
| 加密 | 始终用主密钥写 `v2:` |
| 解密 | 依次试主密钥 + 全部 legacy，**错误信息不含 token/明文** |
| 迁移/轮换 | `reencrypt_access_code_token`；`POST /api/v1/rooms/access-code/rotate`（`dorm:access_code:update`）批量重加密 |
| 审计 | `dorm_room.access_code.rotate_keys` 只记 migrated/already_current/failed/scanned |
| 日志/导出 | 不输出明文；列表仅 `has_access_code` |

### 迁移操作顺序（运维）
1. 生成新钥：`python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
2. 设置 `ACCESS_CODE_ENCRYPTION_KEY=<新钥>`，`ACCESS_CODE_LEGACY_SECRETS=SECRET_KEY`（或旧专用钥）
3. 重启后端
4. 调用 `POST /api/v1/rooms/access-code/rotate`（或下次维护窗口）
5. 确认 `failed=0` 后可按需收紧 legacy 列表

**既有密文在迁移前后均可解密；迁移过程不落明文日志。**

### 代码变更
- `backend/app/core/config.py`：新增 `ACCESS_CODE_ENCRYPTION_KEY`、`ACCESS_CODE_LEGACY_SECRETS`
- `backend/app/core/security.py`：密钥环、`v2:` 前缀、多钥解密、`reencrypt_access_code_token`、`access_code_needs_reencrypt`
- `backend/app/services/dorm_service.py`：`migrate_access_code_keys`
- `backend/app/api/v1/endpoints/dormitories.py`：`POST /rooms/access-code/rotate`
- `.env.example`：密钥生成与轮换说明（无明文示例密码）

### 测试（5 条）
| 场景 | 结果 |
|---|---|
| `encrypt → decrypt` 往返 + `reencrypt` 后仍可解 | 通过 |
| **切换专用钥后**，SECRET_KEY 派生的旧密文仍可解密 | 通过 |
| rotate 接口成功，响应与列表**无明文** | 通过 |
| finance_viewer 查看/轮换 **403** | 通过 |
| 员工/报表导出**不含**门禁密码明文 | 通过 |

---

## 4. 实际执行的测试命令与结果

```text
# 后端（真实 MySQL）
cd backend && .venv/bin/python -m pytest -q
→ 129 passed

# 补强专项
cd backend && .venv/bin/python -m pytest tests/test_v101_remediation.py -q
→ 9 passed

# 前端
cd frontend && npm test          → 5 passed
cd frontend && npm run typecheck → 0 error
cd frontend && npm run build     → success

# Playwright（真实 Chrome，Docker 前后端已重建）
cd frontend && ./node_modules/.bin/playwright test
→ 11 passed
```

Playwright 覆盖：
- 房型创建/编辑/停用（浏览器）
- 房间导入模板上传/预览/提交/前导零门禁密码
- 既有 m5/m6 与 v101（BUG-003/005/007）回归

---

## 5. 遗留风险

1. **密钥轮换未做自动化调度**：rotate 需运维在配置切换后调用；未执行时旧密文仍靠 legacy 解密（设计如此）。
2. **`ACCESS_CODE_ENCRYPTION_KEY` 为空时仍回退 SECRET_KEY**：兼容旧部署，但生产应显式配置独立钥。
3. **批量分床取消失败**极端情况下会留下待人工处理的申请单（行内 `recovery=cancel_failed`，并有 recovery 审计；强释预留可兜底防双占）。
4. **Playwright 使用系统 Chrome**（沿用 M6 遗留）。
5. **房型与 `room_type` 字符串仍无 FK 强校验**（V1.0 兼容策略，本轮未改）。

---

## 6. 对 GPT Web 复核的说明

- 三项补强均已落地并附**真实执行**测试结果；未执行项不标记通过。
- 未改动 M1～M6 与 BUG-001～FEAT-008 已通过行为；全量回归保持绿色。
- **本文件不构成 V1.0.1 发布声明**；待 GPT Web 再次复核通过后方可发布。

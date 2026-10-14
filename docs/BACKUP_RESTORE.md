# DMS V1.0 备份与恢复

> 目标：每日逻辑备份、可手动恢复、定期演练。  
> 原则：恢复演练在**隔离数据库**进行，禁止在未授权情况下覆盖正式库。

---

## 1. 备份

### 1.1 手工备份

```bash
# 在项目根目录
export MYSQL_PASSWORD=...          # 与 .env 一致
export MYSQL_ROOT_PASSWORD=...     # restore 建库/授权需要
./scripts/backup.sh ./backups
# 生成 backups/dms_YYYYMMDDThhmmssZ.sql.gz
```

脚本特性：

- `mysqldump --single-transaction --routines --triggers --events --no-tablespaces`
- gzip 压缩；UTC 时间戳文件名
- 不备份二进制日志位置以外的系统库

### 1.2 每日自动备份（cron 示例）

```cron
# 每日 02:30 UTC 备份并保留 14 天
30 2 * * * cd /opt/dms && MYSQL_PASSWORD=... MYSQL_ROOT_PASSWORD=... ./scripts/backup.sh ./backups && find ./backups -name 'dms_*.sql.gz' -mtime +14 -delete
```

生产建议：备份目录挂载到独立卷/对象存储，并对备份文件加密（如 `age`/`gpg`）。

---

## 2. 恢复

### 2.1 恢复到隔离演练库（推荐）

```bash
export MYSQL_PASSWORD=...
export MYSQL_ROOT_PASSWORD=...
./scripts/restore.sh backups/dms_YYYYMMDDThhmmssZ.sql.gz dms_restore_test
```

脚本会：

1. `CREATE DATABASE IF NOT EXISTS dms_restore_test`
2. 授权应用用户
3. 导入 dump

### 2.2 恢复到正式库（维护窗口）

```bash
# 1) 再做一次全量备份
./scripts/backup.sh ./backups
# 2) 停止写入（停 frontend/backend 或摘流量）
docker compose stop frontend backend
# 3) 恢复（覆盖目标库，不可逆）
./scripts/restore.sh backups/<file>.sql.gz dms
# 4) 启动并验证
docker compose up -d
curl -s http://127.0.0.1:8080/health
```

**警告**：恢复会覆盖目标库现有数据。未做演练与二次备份前不要对生产执行。

---

## 3. 恢复演练记录（M6）

| 项目 | 结果 |
|---|---|
| 备份文件 | `backups/dms_20261013T165238Z.sql.gz`（约 756KB） |
| 备份方式 | `scripts/backup.sh`（修复 `--no-tablespaces` 后无 PROCESS 权限报错） |
| 恢复目标 | 隔离库 `dms_restore_test` |
| 恢复方式 | `scripts/restore.sh <file> dms_restore_test` |
| 核对 | employees 857 / dorm_beds 1241 / accommodation_records 569 / checkout_records 267 / sys_users 209 / sys_roles 5 / sys_permissions 27 — **与源库一致** |
| 正式库 | 未覆盖、未清空 |

### 3.1 核对 SQL 示例

```sql
SELECT 'employees', COUNT(*) FROM dms.employees
UNION ALL SELECT 'employees', COUNT(*) FROM dms_restore_test.employees;
-- 逐表对比业务表与权限表
```

---

## 4. 全新环境迁移验证

空库执行：

```bash
docker compose exec -e MYSQL_PWD=$MYSQL_ROOT_PASSWORD mysql \
  mysql -u root -e "CREATE DATABASE dms_migrate_fresh CHARACTER SET utf8mb4;"
# 在 backend 容器/虚拟环境中将 MYSQL_DATABASE 指向新库
alembic upgrade head
```

M6 结果：`0001 → 0005` 全部成功，26 张业务/权限表创建，生成列唯一索引（active 员工/床位等）生效。

---

## 5. 数据完整性检查清单

恢复后至少确认：

- [ ] `alembic_version` 为 `head`
- [ ] 管理员可登录
- [ ] 员工/宿舍/在住记录数量与备份前一致
- [ ] 退宿历史与待办/预警可查询
- [ ] 报表导出可用

---

## 6. 故障与回滚

| 场景 | 处理 |
|---|---|
| 备份文件损坏 | `gunzip -t file.sql.gz`；改用更早备份 |
| 恢复中断 | 删除半成品库，重新 `restore.sh` |
| 误恢复到生产 | 停止服务，用升级前备份恢复；保留现场并记录 |

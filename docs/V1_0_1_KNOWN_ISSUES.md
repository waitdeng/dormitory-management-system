# DMS V1.0.1 Known Issues

| ID | 问题 | 等级 | 状态 |
|---|---|---|---|
| KI-1 | **调宿部分事务锁顺序尚未完全统一**（`_load_tr` 业务行先于 employee；与 confirm/扫描交叉存在理论死锁路径 D1/D2） | 中 | 延后 **V1.0.2** 专项 |
| KI-2 | **并行 Playwright 偶发资源竞争**（建议 `--workers≤2`；串行稳定） | 低 | 运维/CI 缓解 |
| KI-3 | **开发历史测试数据异常不迁移**（C1/C5 stale 仅存在于开发库；HOTFIX-07B 已取消） | 信息 | 生产空库无此问题 |
| KI-4 | **最终 Mac Work 独立浏览器验收尚未完成** | 中 | 待项目负责人/验收方执行 |
| KI-5 | 运行环境 **ACCESS_CODE_ENCRYPTION_KEY 未配置**时回退 SECRET_KEY 派生 | 中 | 上线前必须配置独立钥 |

不影响主流程；均记录于发布包与 V1.0.2 backlog。

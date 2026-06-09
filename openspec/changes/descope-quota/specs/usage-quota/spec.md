## REMOVED Requirements

### Requirement: Per-user and global quotas
**Reason**: 该能力从未接线——`set_quota`/`check_quota`/`record_usage` 在请求路径零调用,配额设不了、不强制、用量不记;v1 descope。
**Migration**: 暂无替代(v1 不限额)。将来需控成本/防滥用时整体重做:在 platform 请求入口接 check/record + 加 admin 配置端点。

### Requirement: Over-quota requests are rejected
**Reason**: 同上——`/chat` 从不调 `check_quota`,超额不会被拒;`_emit_over_quota_event` 仅日志桩、无调用者。
**Migration**: 暂无替代。将来在 platform 入口强制(单机 agent 无 quota),超额返回 429。

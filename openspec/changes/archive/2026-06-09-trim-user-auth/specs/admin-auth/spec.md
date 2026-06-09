## REMOVED Requirements

### Requirement: 2FA for high-risk operations
**Reason**: 2FA 是半成品——step-up 校验虽挂在高危 admin 操作上,但无 enable 端点/无 otpauth-QR 设置/无 disable/无丢失恢复,用户根本开不了,实际用不上;v1 descope。
**Migration**: 暂无替代(高危操作不再要求 2FA)。将来整体重做:补 enable(含 otpauth/QR + confirm)、disable、恢复码/admin 重置,再决定 step-up 与/或 login 强制。

## REMOVED Requirements

### Requirement: One-time invite links
**Reason**: 邀请链是独立、不发邮件、生产无路由(不可达)的自助注册路径,与"admin 手动建用户 + admin 设密码"重叠;v1 纯 admin provisioning,不做自助注册。
**Migration**: 用 admin 手动建用户(`POST /users`)+ admin 设密码(`POST /users/{id}/password`)。将来要自助邀请注册时连邮件送达一起重做。

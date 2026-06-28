# external-credential-vault Specification

## Purpose
该能力已从 platform 侧退役；本 spec 记录退役后的边界，防止旧表、旧 consent 流和旧 provider 被重新接回控制面。

## REMOVED Requirements

### Requirement: 外部服务注册表（单层全局，多协议）
**Reason**: 平台不再维护工具外部服务目录。
**Migration**: drop 旧服务注册表；外部系统定义将来若需要，改由 agent-side 方案承载。

### Requirement: per-principal 加密凭证存储
**Reason**: 平台不再存储工具级 per-principal 凭证。
**Migration**: drop 旧凭证表。

### Requirement: 加密复用既有 Fernet 主密钥
**Reason**: 工具凭证不再由 platform 加密落盘。
**Migration**: 主密钥仍服务其它密文用途，但不再服务该退役能力。

### Requirement: Provider 经 seam 注入并按 principal 解析
**Reason**: platform 启动期不再注入真实 provider。
**Migration**: 删除 platform provider 后，seam 回落默认 `NeedsConsent`。

### Requirement: 最小 OAuth2 授权码 consent 流
**Reason**: platform 不再承载 consent 管理面。
**Migration**: 删除授权与回调端点。

### Requirement: access token 过期自动刷新
**Reason**: 旧 provider 已退役。
**Migration**: 删除 token refresh 路径。

### Requirement: refresh 失效与错误的状态流转
**Reason**: 旧凭证状态机已退役。
**Migration**: 删除对应状态流转逻辑。

### Requirement: 凭证吊销
**Reason**: platform 不再管理该类凭证吊销。
**Migration**: 删除相关管理端点。

### Requirement: 用户提交 API key 凭证
**Reason**: platform 不再提供该录入面。
**Migration**: 删除提交端点。

### Requirement: API-key 凭证解析
**Reason**: 旧 provider 已退役。
**Migration**: 删除相关解析逻辑。

### Requirement: provider 适配层支持多服务
**Reason**: 平台不再保留这套多服务工具凭证适配层。
**Migration**: 若未来恢复，需在 agent side 重新实现。

### Requirement: 禁用的外部服务在凭证解析被门控
**Reason**: 旧服务目录与凭证表已退役。
**Migration**: 相关门控逻辑随之删除。

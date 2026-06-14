# im-connector-config Delta

## REMOVED Requirements

### Requirement: Config resolution with .env fallback
**Reason**: owner-level IM connector 机制 descope（connector_config 随之移除）。
### Requirement: Masked read for management surfaces
**Reason**: 同上。
### Requirement: Update connector config
**Reason**: 同上。
### Requirement: Seed connectors from environment
**Reason**: 同上。
### Requirement: Per-platform credential field schema
**Reason**: 同上（whatsapp 凭据 schema 随机制移除；未来 whatsapp 增量重建时另设）。
### Requirement: Mask all configured credential fields
**Reason**: 同上。

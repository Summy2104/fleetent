## Context

fleetent 已实现 Slack/Telegram IM gateway、用户映射（`im_users`）、用户级 agent 绑定（`user_agents`）。但目前所有 IM 用户都可以无限制使用 bot，且 agent 只能按用户绑定，群聊场景下无法为 channel 统一配置 agent。

当前 agent 查找逻辑：`user_agents` → 裸跑（无 agent）。

## Goals / Non-Goals

**Goals:**
- 为 IM 用户引入准入控制（allowlist），新用户默认待审批
- 支持 channel 级别的 agent 绑定（优先级高于用户绑定）
- 支持全局默认 agent 配置，未绑定时的兜底

**Non-Goals:**
- OAuth 代理授权（用户临时授权 agent 操作其账户）
- 权限与用户取交集的细粒度权限控制
- Web 管理后台（CLI 足够）

## Decisions

### 1. `allowed` 字段加在 `im_users` 而非 `users`

`im_users` 是 IM 平台入口的映射表，准入语义属于 IM 层，不影响直接 API 调用（Bearer key 用户）。如果加在 `users` 表，则 HTTP API 用户也需要审批，超出范围。

**备选**：在 normalizer 里维护独立的 allowlist 配置文件 → 拒绝，运维复杂，无法持久化跨进程状态。

### 2. `channel_agents` 独立表，而非扩展 `user_agents`

`channel_agents(platform, channel_id, agent_id)` 与 `user_agents(user_id, agent_id)` 是不同维度的绑定，不应复用同一张表。channel_id 是平台原生 ID，不对应内部 user 概念。

**备选**：在 `user_agents` 加 `channel_id` 列 → 拒绝，破坏现有语义，查询复杂。

### 3. 默认 agent 通过 `config/settings.yaml` 配置，而非数据库

`default_agent_name` 是运维配置，变更频率低，放 YAML 符合现有 `Settings`（pydantic-settings）模式，无需数据库 migration。

`set-default-agent` CLI 命令直接读写 `config/settings.yaml`。

**备选**：存数据库单行配置表 → 拒绝，过度设计。

### 4. normalizer 中的 agent 查找顺序

```
channel_agents(platform, channel_id) → user_agents(user_id) → default_agent → 裸跑
```

normalizer 已知 platform + channel_id + user_id，可以依次查询。逻辑集中在 `normalizer.py`，server.py 的 `/chat` 接口复用同一函数 `get_agent_for_context(platform, channel_id, user_id)`。

### 5. 数据库 migration 策略

`im_users` 新增 `allowed` 列使用 `ALTER TABLE ... ADD COLUMN allowed BOOLEAN DEFAULT 0`。现有代码在 `_init_db()` 中检测列是否存在后执行 migration，保持向后兼容。

`channel_agents` 是全新表，直接在 `_init_db()` 中 `CREATE TABLE IF NOT EXISTS`。

## Risks / Trade-offs

- **现有 IM 用户被锁定** → Migration 时对已存在的 `im_users` 行执行 `UPDATE im_users SET allowed=1`，保证存量用户不受影响
- **admin CLI 直接写 settings.yaml 可能覆盖注释** → 使用 `ruamel.yaml` 保留注释，或只修改对应 key（`pyyaml` 会丢注释）；MVP 阶段接受注释丢失
- **channel_id 无跨平台唯一性保证** → `(platform, channel_id)` 联合唯一约束已覆盖

## Migration Plan

1. `im_user_store._init_db()` 中加 `ALTER TABLE im_users ADD COLUMN allowed BOOLEAN DEFAULT 0 NOT NULL`（SQLite 支持带 DEFAULT 的 ADD COLUMN），并对存量行设置 `allowed=1`
2. `agent_store._init_db()` 中加 `CREATE TABLE IF NOT EXISTS channel_agents ...`
3. 两处均为幂等操作，可反复执行

回滚：删除 `allowed` 列不被 SQLite 直接支持，但可以通过重建表回滚（开发阶段删 db 文件重置即可）。

## Open Questions

- `set-default-agent` 写 settings.yaml 时是否需要保留注释？MVP 阶段先用 pyyaml（丢注释），后续按需换 ruamel.yaml。

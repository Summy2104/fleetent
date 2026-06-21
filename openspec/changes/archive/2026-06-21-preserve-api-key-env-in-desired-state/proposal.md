## Why

平台 materialize 的 `_strip_secret_plumbing`(`agent_lifecycle/materialize.py:123-133`)在生成下发给 node 的 desired-state 载荷时,用 `key.endswith("_env")` 把 **`api_key_env` 这个非密钥的变量名指针**(其值只是个 env 变量名,如 `ANTHROPIC_API_KEY`)也一并剥掉了。结果:node 据 desired-state 写出的 `agent.yaml` 缺少 `api_key_env`,模型 `resolver.require_api_key` 因 `api_key_env` 为空直接返回 `None`(`model/resolver.py:143-144`)→ **任何走 node 部署的 agent 模型调用都拿不到 key、报 401,连 IM 上都答不了话**。这是一个 born-broken bug:每个托管 agent 默认带病诞生。试用 demobot 时正是手动给 `agent.yaml` 补上 `api_key_env` 才修好,根因就在这里。

## What Changes

- **修 `_strip_secret_plumbing`**:保留 `*_env` 指针字段名(`api_key_env` 等——它们是变量名,不是密钥),只继续剥真正承载密钥值的 `env` 字典(`key == "env"`)与 `credential_ref`。即:删除 `key.endswith("_env")` 这一过度剥离分支,保留 `key == "env"` 与 `endswith("credential_ref")`。
- **不改主权契约**:密钥**值**仍由 `_seed_env`(inject slot / provider inline key / shared secret)落 `.env`,desired-state 仍**不含明文密钥**。本 change 只停止误删非密指针名,不让任何 secret 值进入 desired-state。

## Capabilities

### New Capabilities
(无)

### Modified Capabilities
- `node-desired-state-api`: 「分区期望态拉取」的下发配置载荷契约澄清——非密载荷 MUST 保留非密的 `*_env` 指针字段名(如 `api_key_env`),仅剥离承载密钥值的 `env` 字典与 `credential_ref`;node 据此写出的 `agent.yaml` 能携带 `api_key_env` 指针,运行时方可解析模型 key。

## Impact

- **改动代码**:仅 `src/fleetent/platform/agent_lifecycle/materialize.py` 的 `_strip_secret_plumbing` 一个函数。
- **测试**:断言 ① 含 `api_key_env` 的 agent 经 `desired_state_payload_from_agent_file` 后**仍保留** `api_key_env`;② 承载密钥的 `env` 字典与 `credential_ref` **仍被剥**;③ `materialize_from_store` 产出的 `agent.yaml` 含 `api_key_env`、且当 provider 配了 inline key 时 `.env` 含该值。
- **公共 API 表面**:不变(端点签名不变,只是载荷不再缺字段)。
- **模块边界**:只动 platform `agent_lifecycle`;**不碰 agent 运行时、不碰 `server.py`(与并行的 `admin-frontend-react-foundation` 零文件重叠)、无 schema/迁移**;不破坏 agent↔platform 单向解耦,也不破坏 desired-state 不含明文密钥的契约。
- **不在本切片**:`FLEETENT_TUI_TOKEN` 注入(B2)与 node 端口/agent gateway(B3)——挪到后续 gateway/ingress change。

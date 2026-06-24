## MODIFIED Requirements

### Requirement: Materialize 时 scaffold agent .env / TUI token

`fleetent node start` 在 reconcile 把某个期望 agent 的 home materialize（写 `agent.yaml`）时，SHALL 同时写出一个**完整的 `.env`**（文件权限 `0600`），作为该 agent 所有运行期 env 的单一真相：

- SHALL 列出 `agent.yaml` 引用到的**全部** `*_env` 名——口径为对 agent 定义做 `flatten` 全字段扫描（与平台 `materialize` 同一收集器），**不得**用手枚举子集（消除漏 `embedding`/`rerank`/`telegram`/各 `*_env` 的旧不一致）。
- 对每个名，SHALL 写入其真实值：来自本轮 desired-state 下发的 `secrets`（managed），或既有 operator 值（standalone / operator 手填）。下发 / 已有值缺失的名 SHALL 以空值占位写出（仍可见、可补），node 实现 SHALL 记录"被引用但无值"的名以便排障。
- SHALL 含一个有效的 `FLEETENT_TUI_TOKEN`（`ma-<64 hex>`）：缺则生成、已存在则原样保留（MUST NOT 轮换在跑 agent 的既有 token）。
- 真实 secret 值由此**写入 `.env`**（env-only，见 `node-secret-injection`），不再经进程 env 注入。

该 token 仍是 forwarder（`/forward/agents/{name}/chat`）与 IM-edge 注入 agent loopback `/chat` 的 `Authorization: Bearer` 凭据。

#### Scenario: 新 materialize 的 agent 获得完整 .env

- **WHEN** node reconcile materialize 一个 home 此前不存在 `.env` 的期望 agent
- **THEN** 该 home 出现 `0600` 的 `.env`，含 `agent.yaml` 引用到的全部 `*_env` 名 + `FLEETENT_TUI_TOKEN`
- **AND** 凡本轮 desired-state 下发了值的名，`.env` 中为真实值（非空占位）
- **AND** 经 forwarder `/forward/agents/{name}/chat` 触达该 agent 不再返回 503 `has no env scaffold`

#### Scenario: env 名收集为统一 flatten 口径

- **WHEN** agent 配置同时引用 model `api_key_env`、`embedding.api_key_env`、`rerank.api_key_env`、`telegram.bot_token_env`
- **THEN** materialize 出的 `.env` SHALL 同时列出这四者（flatten 全字段），node 与平台两条路径产物一致

#### Scenario: TUI token 幂等保留

- **WHEN** node reconcile materialize 一个 `.env` 已含 `FLEETENT_TUI_TOKEN=ma-...` 的 agent
- **THEN** 该 `FLEETENT_TUI_TOKEN` 值保持不变，node MUST NOT 因 materialize 而轮换或清空它

## ADDED Requirements

### Requirement: 停用 agent 时擦除其 .env

`fleetent node start` 在某 agent 不再属于本 node 期望集（`unpin` / `disable` / 删除）而被停掉进程时，SHALL 擦除该 agent home 的 `.env`，不为已停用 agent 在盘上保留明文 secret。该擦除 SHALL 舱壁化（单 agent 擦除失败只记日志，不影响其它 agent 的 reconcile）。

#### Scenario: 停用即擦 .env

- **WHEN** agentA 从本 node unpin（或 disable / 删除），node 停掉其进程
- **THEN** agentA home 的 `.env` 被擦除，盘上不再留其明文 secret
- **AND** 单个擦除失败只记日志，不改变进程退出码、不波及其它 agent

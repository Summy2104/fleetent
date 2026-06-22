## ADDED Requirements

### Requirement: platform 经 desired-state 分区下发 per-agent secret

平台 SHALL 在 `GET /nodes/{id}/desired-state` 响应中，为每个返回的 agent 附其所需 secret 值，**与非密 config 分离**（独立字段，不混入 `config`）。secret 来源 SHALL 复用既有凭证源——`credential_slots.list_slots(agent)` 枚举该 agent 的 env 槽位，`secret_store.get_decrypted(agent_id, env_name)`（及共享槽 `agent_id=None`）取值——与 materialize 写 `.env` 同源。下发 SHALL 仍按 node 分区（node 只得到 pin 在其上且 enabled 的 agent 的 secret），不返回其它 node 的 secret。

#### Scenario: 期望态附带 agent 的 secret

- **WHEN** node 拉取期望态，其上 agentA 有已设置的 secret 槽（如 `SLACK_BOT_TOKEN`）
- **THEN** 响应中 agentA 条目含独立 `secrets` 字段 `{SLACK_BOT_TOKEN: <值>}`，且 `config` 中不含该值

#### Scenario: 只下发本 node 的 agent secret

- **WHEN** agentB pin 在另一个 node
- **THEN** 本 node 的期望态不含 agentB 的任何 secret

#### Scenario: 未设置的槽不下发

- **WHEN** agentA 的某槽 `status != "set"`
- **THEN** 该 env 名不出现在 `secrets` 中（不下发空值）

### Requirement: node 注入子进程 env，内存不落盘

`fleetent node start` SHALL 把下发的 secret 作为环境变量注入 `fleetent agent run` 子进程（`Popen(env=...)`），**不写入 agent home 的 `agent.yaml`/`.env` 或任何磁盘文件**。agent 进程经既有 `load_dotenv(override=False)` 读取（已存在的 env 不被覆盖），**agent 进程零改动**。secret SHALL 仅存在于 node 内存与子进程环境。

#### Scenario: secret 经 env 注入而非落盘

- **WHEN** node 拉起 agentA 且其有 secret
- **THEN** secret 作为子进程 env 传入；agentA home 的 `agent.yaml` 不含 secret，磁盘上无 secret 文件

#### Scenario: agent 读到注入的 env

- **WHEN** agentA 进程启动，env 含注入的 `SLACK_BOT_TOKEN`
- **THEN** agent 的 `load_dotenv(override=False)` 不覆盖它，下游消费者读到正确值

### Requirement: 磁盘缓存剥除 secret 与 platform-down 降级

`fleetent node start` 的 desired-state 磁盘缓存（C3 引入，兜 platform 单点）SHALL **只缓存非密 config，剥除 secret**——secret 永不落盘。platform 不可达回落缓存时：已在跑的 agent（secret 已在其进程 env 中）SHALL 继续运行/被 re-adopt；但**需要 secret 才能启动的 agent SHALL NOT 用无 secret 的缓存强行拉起**（缺 secret 的新启动推迟到 platform 恢复），并记录该推迟。

#### Scenario: 缓存不含 secret

- **WHEN** node 写 desired-state 缓存
- **THEN** 缓存内容含 config、不含任何 secret 值

#### Scenario: platform 不可达时维持在跑 agent

- **WHEN** platform 不可达且 agentA 已在跑
- **THEN** node 用缓存 config 维持 agentA（其 env 中 secret 仍在），不重启它、不丢 secret

#### Scenario: platform 不可达时不无 secret 强启

- **WHEN** platform 不可达、agentB 应启动但其 secret 仅能从 platform 取且缓存无
- **THEN** node 推迟启动 agentB 并记录，待 platform 恢复后再带 secret 拉起

### Requirement: secret 传输安全基线

node↔platform 的 secret 传输 SHALL 在传输层加密（TLS；mTLS 更佳），并依赖 node 鉴权 + 按 node 分区授权（C1/C2 已有）确保 node 只能取到自己 agent 的 secret。secret SHALL NOT 出现在日志中。

#### Scenario: 跨 node 取 secret 被拒

- **WHEN** node A 以其 key 请求 node B 的期望态
- **THEN** 按 C2 的 403 自限拒绝，A 取不到 B 的 secret

#### Scenario: secret 不入日志

- **WHEN** node 拉取/注入 secret 过程中产生日志
- **THEN** 日志不含 secret 明文（至多记 env 名或长度）

## MODIFIED Requirements

### Requirement: node 把 secret 写入 agent .env（env-only，0600）

`fleetent node start` SHALL 把下发的 secret 作为真实值**写入 agent home 的 `.env`**（`<home>/agents/<name>/.env`，文件权限 `0600`），由 agent 进程经既有 `load_dotenv` 读取。node SHALL NOT 再经 `Popen(env=...)` 把 secret 注入子进程环境——secret 的唯一落地点是 `.env`（env-only，单一真相）。`.env` SHALL 与 `agent.yaml` 在同一次物化中写出，且在 `backend.spawn` **之前**就位。agent 进程零改动（仍只读 `.env` + 进程环境）。

secret 由此从"仅存于 node 内存与子进程环境（临时）"变为"agent home `.env` 明文落盘（持久）"。`.env` SHALL 仅由物化写出（managed 下是物化产物，非手改权威）；其权威仍是平台 vault（`secret_store`），`.env` 是其派生物化结果，轮换/改配置经重物化覆盖刷新。home 目录 SHALL `0700`、`.env` SHALL `0600`。

#### Scenario: secret 写入 .env 而非注入 env

- **WHEN** node 物化并拉起一个有 secret 的 agentA
- **THEN** agentA home 的 `.env` 含该 secret 的**真实值**且文件权限为 `0600`
- **AND** node 拉起子进程时 SHALL NOT 经 `Popen(env=...)` 额外注入该 secret（agent 从 `.env` 读到）

#### Scenario: .env 在 spawn 前就位

- **WHEN** node reconcile 决定拉起 agentA
- **THEN** 写 `agent.yaml` → 写完整 `.env`（名+值，`0600`）→ 再 `backend.spawn`，agent boot 时 `.env` 已含所有所需值

#### Scenario: 重物化覆盖刷新（轮换/改配置）

- **WHEN** 某 secret 在 vault 轮换后，node 下一轮收到新的 desired-state secrets
- **THEN** node SHALL 重写 `.env` 为新值（覆盖旧值），不残留旧 secret

### Requirement: 磁盘缓存剥除 secret，.env 承担 platform-down 韧性

`fleetent node start` 的 desired-state 磁盘缓存（兜 platform 单点）SHALL **只缓存非密 `config`、剥除 secret**——缓存内容永不含 secret 值（缓存 ≠ `.env`）。platform 不可达回落缓存时：已物化 agent 的 `.env` 已持久含真值，故 agent SHALL 能从盘上 `.env` 继续运行 / 被 re-adopt / 重启，**不再因"缺 secret"而推迟启动**。

#### Scenario: 缓存不含 secret

- **WHEN** node 把 desired-state 写入磁盘缓存
- **THEN** 缓存内容含 `config`、不含任何 secret 值（secret 仅在 agent `.env` 中，不在缓存中）

#### Scenario: platform 不可达时 agent 仍可从 .env 启动

- **WHEN** platform 不可达、agentA 已被物化过（`.env` 在盘上含真值），其进程因故退出
- **THEN** node SHALL 用盘上 `.env` 重新拉起 agentA，不因 platform 不可达而缺 secret

### Requirement: 停用 agent 擦除其 .env

当某 agent 在本 node 上 `disable` / `unpin`（不再属于本 node 期望集）/ 被删除时，`fleetent node start` SHALL 在停掉其进程后**擦除该 agent home 的 `.env`**（连同其中的明文 secret），不为已停用 agent 在盘上保留密钥。

#### Scenario: unpin 后 .env 被擦除

- **WHEN** agentA 从本 node unpin（或 disable / 删除），node 停掉其进程
- **THEN** agentA home 的 `.env` SHALL 被擦除，盘上不再留有其明文 secret

## REMOVED Requirements

### Requirement: node 注入子进程 env，内存不落盘

**Reason**: 与 env-only 目标直接冲突——本 change 明确选择把 secret 写入 agent `.env`（`0600`）作为唯一落地点，以统一 managed/standalone、消除"注入 vs 文件"二元性、并使物化产物透明完整。
**Migration**: 由新 requirement「node 把 secret 写入 agent .env（env-only，0600）」取代。存量在跑 agent 在下一轮 reconcile 被重写 `.env`（含真值），下次重启即走 env-only；过渡期实现可短暂保留注入以便回滚（见 design）。原"secret 永不落盘"的安全前提被显式权衡取代（`.env` `0600` 持久落盘 + 暴露面加固 + 停用擦除）。

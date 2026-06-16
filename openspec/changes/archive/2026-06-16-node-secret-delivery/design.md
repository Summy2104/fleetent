## Context

C2（desired-state API）、C3（node supervisor）已 apply 落 main。C4 让链路真正能连外部：把 agent 所需 secret 安全送到远端 node 并注入进程，agent 进程零改动。真实代码锚点：
- platform 侧 secret 源 = `credential_slots.list_slots(agent)`（枚举 env 槽）+ `secret_store.get_decrypted(agent_id, env_name)`（取值），与 `materialize` 写 `.env` 同源。
- C2 的 `desired_state_payload_from_agent_file` 已经 `_strip_secret_plumbing`（剥 `env`/`*_env`/`*credential_ref`）→ config 确认非密。
- node 注入点：`node/backend.py LocalBackend.spawn`（当前不传 env）、`node/reconcile.py`（_write_home + spawn 串接）、`node/provider.py`（拉取/解析 + **磁盘缓存**）。

## Goals / Non-Goals

**Goals:**
- platform：desired-state 每 agent 附独立 `secrets` 字段（源自 credential_slots+secret_store，分区授权）。
- node：secret 注入 `fleetent agent run` 子进程 env（内存不落盘）；磁盘缓存剥 secret；platform-down 降级。
- 安全：TLS + 分区授权 + secret 不入日志。

**Non-Goals:**
- 不引入 secret 引用间接（`vault://`）、JIT fetch、短期租约（roadmap）。
- 不上 HashiCorp Vault 后端（roadmap，Randy 已拍）。
- 不改 agent 进程（靠 `load_dotenv(override=False)` + env 注入，零改动）。
- 不拆旧 controller（C5）。

## Decisions

1. **secret 与 config 分离的两通道**：config（非密，C2 已剥）→ 写 agent.yaml（落盘）；secret → 独立 `secrets` 字段 → 仅 env 注入（不落盘）。绝不把 secret 混进 config，避免落盘。

2. **复用既有凭证源，不新建**：platform 侧 `credential_slots.list_slots` + `secret_store.get_decrypted`（materialize 写 .env 同源），保证"node 拿到的"与"co-located .env 写的"一致。只下发 `status=="set"` 的槽。

3. **env 注入，agent 零改动**：`backend.spawn` 扩 `env` 参数，`Popen(env={**os.environ, **secrets})`；agent `load_dotenv(override=False)` 不覆盖已存在 env → 无需 .env 文件持有 secret。

4. **磁盘缓存必须剥 secret**（C3 缓存的安全收口）：`provider` 写 `desired-state-cache.json` 时剥掉 secret，缓存只含 config。后果：platform-down 回落缓存时——在跑 agent 的 secret 已在其进程 env（继续跑/re-adopt 不受影响）；但**缺 secret 的新启动推迟**到 platform 恢复（不无 secret 强启）。这是安全与可用性的有意取舍：维持现状不丢 secret，新启动依赖 platform。

5. **全部落新 capability `node-secret-injection`**：含"扩展 desired-state 响应携带 secrets"作为 ADDED 要求，不 modify C2/C3 capability（同 C2 原则：新增不改既有）。

6. **secret 不入日志**：拉取/注入/降级路径的日志至多记 env 名或长度，不记明文。

## Risks / Trade-offs

- **secret 过网是固有事实**（中心源 + 远端 agent）；v1 靠 TLS + 分区授权 + 内存不落盘把暴露面压到最低。硬合规"secret 绝不离机"走 node 本地自持（roadmap），非 v1 默认。
- **env 在 /proc 对 node root 可见**：可接受（node root 本就跑这些 agent、是信任面）；比持久 .env 文件暴露小。
- **缓存剥 secret 的降级语义**要测清楚：platform-down 时"维持在跑"与"推迟新启动"两条路径都要覆盖，避免无 secret 误启导致 agent 起来连不上又反复重启。
- **env 注入与 config-hash 重启的交互**：config 变触发重启时，重启后的 spawn 必须重新带上当前 secret（从最新一次成功拉取的内存 secret）；若此刻 platform 不可达且无内存 secret，按"推迟"处理。
- **secret 枚举范围**：apply 时核对 `credential_slots.list_slots` 是否覆盖 agent 全部需注入的 env（模型 key / IM token / MCP / KB），避免漏注入导致 agent 连不上。

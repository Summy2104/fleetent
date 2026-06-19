## Context

C1（nodes/placement，迁移 096）、C2（desired-state API + node_agent_status，迁移 097）已 apply 落 main。C2 真实契约：
- `GET /nodes/{id}/desired-state` → `{node_id, agents:[{agent_id, name, config}]}`（config=非密载荷，来自 `materialize.desired_state_payload_from_agent_file`）。
- `POST /nodes/{id}/status` ← `{agents:[{agent_id, phase, pid?, health?, detail?}]}`。
- 鉴权：`Authorization: Bearer <node service key>` + URL `{id}` 自限。

C3 建消费端：每个 agent host 一个 `fleetent node start` 守护，把期望态调谐成本地 per-agent 进程。这是序列里最大、最特别的一块（新顶层包 + 新二进制）。

## Goals / Non-Goals

**Goals:**
- 新部署件 `fleetent node start`：配置 → 拉期望态(platform-api provider + 本地缓存) → 幂等 reconcile(PID 真相/re-adopt/崩溃重拉/config-hash 漂移重启) → 上报实际态。
- 可插拔进程后端 + `local` 实现（spawn `fleetent agent run`、stop `fleetent agent stop`、liveness PID+os.kill）。
- runtime CLI 加 `fleetent agent stop <id>`（drain 单一真相源）。

**Non-Goals:**
- 不下发/注入 secret（C4）——本 change 跑通的是无需 secret 即可启动的链路 + 非密 config。
- 不做 systemd/k8s 后端、Consul/etcd/Vault provider、failover/调度（roadmap）。
- 不拆旧 in-memory controller（C5）。
- 不改 C2 API 契约。

## Decisions

1. **边界（核心）**：`node/` 是新顶层包，**MUST NOT `import fleetent.platform.*`**（经 HTTP 消费 C2），**MUST NOT import agent runtime 内部**（经 subprocess 调 `fleetent agent run|stop`）。故 node 是纯"HTTP client + 子进程编排"，不违反 agent↔platform 解耦。护栏：boundary 检查需覆盖新包。

2. **实际态真相 = 本地 PID 文件 + `os.kill` 探活**，不用守护内存的 Popen 句柄做权威——这样 `fleetent node start` 重启可 re-adopt 仍在跑的 agent（不重复拉起/不误杀）。崩溃 → 下轮 PID 探活为死 → 重拉。

3. **优雅停经 `fleetent agent stop`，不在 node 侧重写信号**：drain 协议（SIGUSR1→TERM→KILL）单一真相源留 runtime（薄包既有 `_stop_running`）。node 仅 subprocess 调它。代价：runtime CLI 加一个 stop 子命令（ADDED 到 agent-runtime-cli）。备选（node 直接 os.kill 信号序列）不取，理由：避免 drain 逻辑双份漂移。

4. **本地缓存兜 platform 单点**：每次成功拉取缓存期望态；platform 不可达时用缓存继续 reconcile，不误停在跑 agent；缓存缺失则本轮跳过（不动现状）。

5. **config-hash 漂移重启**：记录每个在跑 agent 已应用 config 的 hash；下发 hash 不一致 → 优雅停 + 写新 config + 重拉（agent home-driven、无热重载）。

6. **provider/backend 可插拔（仿 sandbox 后端范式）**：desired-state 来源 = provider 接口(v1 platform-api)；进程操作 = backend 接口(v1 local)。接口留好，systemd/Vault/Consul 后端 roadmap 插入不重架。

7. **home 写入复用 materialize 约定**：node 收到 `config` 后按 runtime 既有 home 约定写本地 agent home（与 `fleetent agent run <key>` 解析一致）。apply 时核对 home key 用 agent_id 还是 name（runtime `resolve_home` vs materialize `home_dir` 的现状），对齐后固定。

## Risks / Trade-offs

- **home key 的 id/name 二义**：runtime `resolve_home(agent_id)` 与 materialize `home_dir(name)` 可能不同源；C3 必须对齐到单一约定（apply task 显式核对），否则 node 写的 home 与 `agent run` 找的 home 不匹配。
- **无 secret 的链路验证有限**：C3 跑通的 agent 只能是无需外部凭证的（或本地已有 env 的）；真正连 IM/模型要等 C4。验证时用不需 secret 的最小 agent。
- **reconcile 与上报时序**：先 reconcile 再上报，上报反映本轮结束态；短暂不一致（收敛中）是预期。
- **测试分层**：node 逻辑（拉取解析/reconcile 决策/backend）用 mock HTTP(respx)+mock subprocess 可 unit；真实"node↔platform↔spawn"端到端属 integration/e2e。
- **新二进制打包**：`fleetent node start` entry point 入 pyproject；install 脚本（install-agent 类）后续接入，本 change 至少让二进制可跑。

## Why

2026-06-22 live e2e 发现：托管 dev-stack（platform + node + managed agent）在单机上**无法端到端
跑通 ingress chat**，且失败被静默吞掉、难以诊断。三处同根问题（都围绕"platform→node 的 key/
网络 plumbing"）：

1. **dev-stack 未提供 `FLEETENT_SECRET_KEY`**。`secret_crypto._key()` 要求该 env，缺失即抛
   `SecretKeyError`。`make node-provision` 时 `node_store.register_node` 的
   `secret_store.set(node service key)` 因此失败——node service key 不落库——platform ingress
   取 key 得 None → 恒 503。Makefile dev 目标从未注入此 key。

2. **`node_store.register_node` 用 `with suppress(Exception)` 吞掉安全关键的 key 持久化**。
   register 照常返回明文、打印"save this"、却没把 key 存进 secret_store。这不止是 dev 问题：
   生产中 master key 配错/secret 后端异常时，register 会**假成功**，platform 之后永远拨不通该
   node 的 forwarder，只在首次 ingress 才以不透明 503 暴露。违反「不吞异常，catch 后必须 log 或
   re-raise」铁律。

3. **forwarder 地址写死 `<node_id>.internal:8786`**（生产内网 DNS 契约）。单机 dev 无此 DNS，
   平台侧 `forwarder_base_url("local-node")` → `httpx.ConnectError`。无任何 override 机制。

合起来：托管 dev-stack 不可"试用"，且首要失败（缺 master key）被 suppress 掩盖成远端 503。

## What Changes

- **dev master key（item 1）**：新增可测助手 `scripts/dev_secret_key.py`（`ensure_dev_secret_key`：
  无则生成合法 Fernet key 持久化到 `$(FLEETENT_HOME)/.dev_secret_key`、有则读取，幂等）；
  Makefile `dev-bootstrap` 调它生成、`DEV_TARGETS` export `FLEETENT_SECRET_KEY` 从该文件读，
  使 platform / node / node-provision 共享同一 key（register 写、serve 时解密一致）。
  `.dev_secret_key` 入 gitignore。
- **register 不吞 key 持久化失败（item 2）**：`node_store.register_node` 去掉
  `with suppress(Exception)`；persist 失败 SHALL **log 明确错误并 re-raise**，使 register
  整体失败（不返回"假成功"的一次性 key）。
- **forwarder 地址可覆盖（item 3）**：`node/forwarder_contract.py` 的 `forwarder_base_url` /
  `forwarder_ws_url` honor 新 env `FLEETENT_FORWARDER_HOST_OVERRIDE`（设则用之，未设则保持
  `<node_id>.internal` 默认契约）；Makefile dev 目标设 `FLEETENT_FORWARDER_HOST_OVERRIDE=127.0.0.1`。

## Capabilities

### New Capabilities
（无）

### Modified Capabilities
- `agent-node-registry`: node service key 持久化（供 platform→node 出站鉴权）失败 MUST 暴露
  （log + 使 register 失败），MUST NOT 静默吞掉、报"假成功"。
- `platform-agent-gateway`: forwarder 地址解析 MUST 可被环境覆盖（用于无 `<node_id>.internal`
  内网 DNS 的环境，如单机 dev），默认仍为内网 DNS 契约。

## Impact

- **owning packages**：`platform`（`platform/node_management/node_store.py`）、
  `node`（`node/forwarder_contract.py`）；dev 工具链（`scripts/dev_secret_key.py`、`Makefile`、`.gitignore`）
- **public API surface**：签名不变（`register_node`、`forwarder_base_url`/`forwarder_ws_url`）；
  仅行为变更（前者失败即抛、后者读 env override）
- **owned tables**：无
- **config namespace**：复用 `FLEETENT_SECRET_KEY`（dev 侧新接线）；新增 dev override
  `FLEETENT_FORWARDER_HOST_OVERRIDE`
- **cross-module dependencies**：不变；不破坏 agent↔platform 解耦（forwarder_contract 属 node、
  node_store 属 platform，方向不变）
- **migration / shim plan**：无 schema、无迁移、无 shim
- 不碰 agent 运行时、frontend；与 `fix-streaming-proxy-client-lifecycle` 零文件重叠（那个改
  forwarder.py/agent_transport.py，本 change 改 forwarder_contract.py/node_store.py/scripts/Makefile），可并行

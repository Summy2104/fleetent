## Context

托管 dev-stack 单机跑通 ingress 的三处 plumbing 缺陷（live e2e 2026-06-22 定位）：

- `secret_crypto._key()` 读 `FLEETENT_SECRET_KEY`，缺失即抛 `SecretKeyError`。
- `node_store.register_node`（约 line 79）：`with suppress(Exception): secret_store.set(None, _node_service_key_env(node_id), plaintext, "node.register")` —— 静默吞掉失败。
- `node/forwarder_contract.py`：`forwarder_base_url(node_id) = f"http://{node_id}.internal:8786"`，硬编码、不可 override。

Makefile 已有 `DEV_TARGETS` export 机制（如 `NODE_PLATFORM_URL`），可挂更多 dev env。

## Goals / Non-Goals

**Goals:**
- 单机 `make dev-bootstrap → platform → node-provision → node` 后，platform 能拨通 forwarder、
  node service key 可被取用，ingress 不再因缺 key / DNS 失败。
- key 持久化失败**响亮失败**（log + raise），不再静默假成功——dev 与生产同受益。
- 默认契约（`<node_id>.internal`、哈希存 key）零行为变更。

**Non-Goals:**
- 不修流式中继 bug（那是 `fix-streaming-proxy-client-lifecycle`，零文件重叠）。
- 不引入生产 secret 管理方案（生产 `FLEETENT_SECRET_KEY` 由运维提供，本 change 只补 dev 默认）。
- 不改 forwarder/transport 路由与鉴权语义。

## Decisions

- **D1 · dev master key 抽成可测助手**：新增 `scripts/dev_secret_key.py::ensure_dev_secret_key(home)`：
  目标文件 `<home>/.dev_secret_key` 存在则读、否则 `Fernet.generate_key()` 写入并返回；幂等
  （多次调用返回同一 key）。Makefile `dev-bootstrap` 调用它确保 key 存在；`DEV_TARGETS` 增加
  `export FLEETENT_SECRET_KEY := $(shell uv run python scripts/dev_secret_key.py)`（或读文件），
  使所有 dev 目标共享。`.dev_secret_key` 加入 `.gitignore`。
  - 选 dev-only 文件而非要求用户手设：降低"试用"门槛；生产仍走运维提供的 env，不受影响。
- **D2 · register 失败即抛**：`node_store.register_node` 去掉 `suppress`；改 try/except 捕获
  persist 异常 → `logger.error(...)` + `raise`（使整个 register 失败、不返回明文）。决策"raise 而非
  log-and-continue"：key 不落库的 node 对 platform 不可用，登记成功是误导；raise 让缺 master key
  在 dev/生产都即时可诊断（而非延迟成首次 ingress 的 503）。
- **D3 · forwarder host override**：`forwarder_contract` 读 `FLEETENT_FORWARDER_HOST_OVERRIDE`：
  设则 `host = override`，否则 `host = f"{node_id}.{DEFAULT_FORWARDER_DOMAIN}"`；端口与 ws scheme
  不变。Makefile dev 目标 export `FLEETENT_FORWARDER_HOST_OVERRIDE=127.0.0.1`。
  - 用单一 host override（非完整 URL 模板）：dev 单 node 场景足够，保持最小表面。

## Risks / Trade-offs

- **D2 收紧 register 语义**：此前"register 永不因 secret 失败而失败"。收紧后，secret 后端异常会
  让 register 失败。这是**期望行为**（假成功更糟），但需确保错误信息可诊断（指明缺 master key /
  secret 后端问题）。测试覆盖：无 `FLEETENT_SECRET_KEY` 时 register 抛清晰错误。
- **dev key 文件落盘**：`.dev_secret_key` 是 dev 便利、明文 Fernet key 落盘在 dev home。必须
  gitignore，且仅 dev home（隔离目录）。生产不经此路径。
- **override env 命名/泄漏**：`FLEETENT_FORWARDER_HOST_OVERRIDE` 仅影响地址解析、不碰鉴权；
  默认不设即保持内网 DNS 契约，生产无需关心。
- **Makefile 任务难 TDD**：item 1/3 的 Makefile 接线本身无单测；可测部分已下沉到
  `scripts/dev_secret_key.py`（D1 助手）与 `forwarder_contract`（D3 override 函数），Makefile 仅做
  wiring，靠 tasks 末尾的 live 复跑实证。

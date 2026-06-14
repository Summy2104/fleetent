## Why

Docker 后端用 `-v <src>:<dst>[:ro]` 位置式语法装配 bind mount。`/exchange` 视图目录按 `scope_key` 命名，而 session 作用域的 `scope_key = session_id`（形如 `slack:dm:U…:1781…`，**含冒号**）。`docker -v` 以冒号分隔字段，源路径含冒号 → `docker: invalid spec: …: too many colons` → **容器创建失败 → sandbox acquire 失败 → run_code 与沙箱化文件工具全部无法执行**（实测 my-bot：run_code 建容器即失败）。这是 unified-file-exchange 的 `exchange_mount` 引入的回归（workspace 目录经 `_name_key` 清洗无此问题，exchange 视图目录用了原始 `scope_key`），影响所有 session 作用域 + Docker 后端 + exchange_mount 生效的部署。

## What Changes

- **BREAKING(内部)**：`DockerBackend` 的 bind mount 装配从 `-v <src>:<dst>[:ro]` 改为 **`--mount type=bind,source=<src>,target=<dst>[,readonly]`**（冒号安全的 key=value 语法），覆盖三处：`_exchange_flags`（根因）、`_workspace_flags`、`_skill_mount_flags`（一并改，防同类隐患、保持一致）。
- 行为等价：挂载点、只读语义、空/None 不挂载均不变；唯一差别是源路径含 `:` 等字符不再破坏 mount 规格。
- 不改 `scope_key` / 视图目录命名 / `artifact_exchange` 布局——修在 mount 语法层，最小且不动数据布局。

## Capabilities

### New Capabilities
（无）

### Modified Capabilities
- `sandbox-workspace-mount`: 新增"bind mount 规格对 scope_key 特殊字符鲁棒"的要求——workspace 与 exchange 视图的宿主挂载 MUST 用冒号安全语法，使 `scope_key`/`session_id` 含 `:` 时容器仍能创建。

## Impact

- **owning package**：`integrations/sandbox`（`backends/docker.py` 的 `_workspace_flags`/`_exchange_flags`/`_skill_mount_flags`）。
- **public API surface**：无（内部静态方法，签名不变）。
- **owned tables**：无。
- **config namespace**：无。
- **cross-module dependencies**：无新增；不碰 agent⊥platform。
- **migration / shim plan**：无 schema/数据迁移。存量 `.views/<scope_key>`（含冒号）目录布局不变——只是挂载它们的命令语法改对。需同步更新断言 `-v` 形式的单测（`test_sandbox_exchange_mount.py`/`test_sandbox_skill_mount_flags.py`/`test_sandbox_client.py`）。

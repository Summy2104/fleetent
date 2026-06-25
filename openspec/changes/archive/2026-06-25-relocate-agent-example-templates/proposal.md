## Why

仓库根目录已统一收纳各组件的示例模板（`.env.example`=platform、`platform.yaml.example`、`node.env.example`、`kb-worker.env.example`），唯独 agent 的两个模板埋在 `agents/default/` 子目录下，命名也不对称。该子目录还演示了一个**过时的** agent home 布局——真实部署路径是 `FLEETENT_HOME/tenants/default/agents/<id>/`（见 `agent_config.py` 与 `agent-runtime-cli` spec），缺了 `tenants/` 那层，等于误导读者。

## What Changes

- 把 `agents/default/agent.yaml.example` 迁到根目录 `agent.yaml.example`，`agents/default/.env.example` 迁到根目录 `agent.env.example`（与 `node.env.example` / `kb-worker.env.example` 的 `<component>.env.example` 命名一致）；删除随之变空的 `agents/` 目录。
- 同步全部引用：Dockerfile（`COPY` / `mkdir`）、README、两个模板文件内部的自引用注释、`tests/unit/test_agent_config.py`、`tests/integration/test_deployment_docs.py`。
- 修正预存的 **tenant-layer drift**（限无歧义处）：README 与 `file-agent-runtime` / `configuration` spec 中"部署 agent 在 `agents/<agent-id>/agent.yaml`"的表述，改为真实的 `tenants/default/agents/<id>/agent.yaml`。
- `install-bootstrap` spec **仅**机械同步模板路径引用到根目录，使 live spec 不再指向已删除的文件路径。
- 根目录清理（独立 chore，与模板无关）：把 `.pytest_cache/`、`.ruff_cache/` 补进 `.gitignore`；删除 `data/.gitkeep`（`data/` 整目录已被 gitignore，运行时数据走 `.fleetent-dev/`）。

不在本 change 范围（已发现、留作后续）：`install-bootstrap` spec 中 "Configuration templates"（seed `agents/default/`）与 "Install bootstrap seeds explicit..."（不再 seed）两个 requirement 的**预存自相矛盾**，与模板物理位置无关，应单开 change 收口。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `configuration`: "Canonical templates avoid ambiguous agent paths" requirement 枚举的规范示例路径由 `agents/default/agent.yaml.example` / `agents/default/.env.example` 改为根目录 `agent.yaml.example` / `agent.env.example`；相关 scenario 同步改路径。"Configuration is split by Platform and Agent perspective" 中 Agent home 路径表述补上 `tenants/default/` 层。
- `file-agent-runtime`: 部署默认 agent home 路径由旧平铺 `agents/default/agent.yaml` 改为真实的 `tenants/default/agents/<agent-id>/agent.yaml`；docs 指引同步。
- `install-bootstrap`: "Configuration templates" requirement 的模板来源路径由 `agents/default/*.example` 改为根目录 `agent.yaml.example` / `agent.env.example`（仅 re-path，不解决该 spec 内部预存矛盾）。

## Impact

- 移动文件：`agent.yaml.example`、`agent.env.example`（自 `agents/default/`）；删除空目录 `agents/`。
- 文档/构建：`README.md`、`Dockerfile`。
- 测试：`tests/unit/test_agent_config.py`、`tests/integration/test_deployment_docs.py`。
- specs：`configuration`、`file-agent-runtime`、`install-bootstrap` 三个 capability 的 delta。
- 运行时无影响：`fleetent agent init` 用 `runtime/agent_init.py` 内嵌模板，不读这些 `.example` 文件；容器跑 `platform serve`，entrypoint 不消费 `agents/default/`。
- 模块边界：无新 package、无 public API / 表 / config namespace 变化、无跨模块依赖变化、无需 re-export shim（模板是纯参考文档）。

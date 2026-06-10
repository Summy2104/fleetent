# Source Module Organization Roadmap

> **状态：LEGACY / 历史参考（已被 superseded）**。模块重组已基本完成；目标模块归属与边界以
> [`target-architecture-proposal.md`](./target-architecture-proposal.md)（§5 横跨边界模块拆分、§9 现模块→目标归属速查）
> + 依赖护栏测试为权威。本文档保留作迁移决策的历史记录，不再更新。
> （`module-boundaries` spec 的 "Source module organization roadmap" requirement 仍引用本文件；如将来做 spec 卫生，可把该 requirement 重指向 target-arch 后再退场本文件。）

## 目标

`src/fleetent` 当前是模块化单体的过渡状态：部分能力已经进入 package，仍有大量 legacy 平铺模块保留在
`src/fleetent/*.py`。本路线图用于指导后续迁移，避免为了“整理目录”一次性大搬家。

目标不是让目录马上完美，而是让后续并行开发更少冲突：

- 新功能有明确 owning package。
- 已迁移模块通过 public API 暴露能力。
- legacy import 路径迁移时保留薄 shim。
- 每次迁移都有 OpenSpec、测试和边界声明。

## 当前状态

已模块化目录：

| 目录 | 当前职责 | 判断 |
| --- | --- | --- |
| `intelligence/` | memory、long-term context、reflection、knowledge-base、vector-store | 已形成主要边界 |
| `observability/` | structured logging、traces、usage / performance、diagnostics | 已形成主要边界 |
| `governance/` | permission gate、quota、audit log、blocklist、agent policy | 已有 implementation spec |
| `integrations/` | MCP client、sandbox client、外部能力接入 | 已有 implementation spec |
| `im_gateway/` | IM 消息归一化与 Slack / Telegram adapter | 已有目录，但 channels 相关 store 仍在顶层 |

主要平铺热点：

| 文件 | 行数级别 | 建议归属 | 迁移优先级 |
| --- | ---: | --- | --- |
| `admin.py` | 已删除 legacy shim | `platform.admin_cli` | 已完成 cleanup |
| top-level User Memory file | 已删除 legacy shim | `intelligence.memory` | 已完成 cleanup |
| `agent_loop.py` | 1000+ | `runtime.agent_loop` | P1 |
| `user_store.py` / `api_key_store.py` / `auth.py` / `agent_store.py` | 100-300 | `platform.user_center` / `platform.agent_admin` | P2 |
| `im_user_store.py` / `im_connector_*` / `im_channel_allowlist.py` | 50-160 | `channels` | P2 |
| `db.py` / `config.py` | 90-270 | `infrastructure` | P3 |

## 目标 Package Map

| Package | 负责 | 典型模块 |
| --- | --- | --- |
| `runtime` | agent 执行循环、上下文压缩、sub-agent 执行、运行时错误治理 | `agent_loop`、`context_mgr`、`sub_agent` |
| `platform` | 管理面、用户 / agent / API key / admin CLI、HTTP admin API | `admin_cli`、`user_center`、`agent_store` |
| `governance` | 工具权限、审批、quota、blocklist、audit | `permission_gate`、`quota`、`audit_log`、`blocklist` |
| `channels` | IM / webhook / schedule 等入口适配和渠道身份绑定 | `im_gateway`、`im_user_store`、`webhook_router`、`cron_scheduler` |
| `intelligence` | memory、long-term context、reflection、knowledge-base、vector-store | 已有目录 |
| `integrations` | MCP、sandbox、外部系统 connector runtime | `mcp`、`sandbox` |
| `observability` | logs、traces、summaries、diagnostics | 已有目录 |
| `infrastructure` | config、database runtime、migration helpers、deployment primitives | `config`、`db` |

依赖方向：

```text
entrypoints / platform / channels
  -> runtime
  -> governance / intelligence / integrations / observability
  -> infrastructure
```

低层 package 不反向 import 高层入口。跨 package 调用必须走 public API。

## 推荐迁移顺序

### 1. `admin-cli-module-split`

优先级最高。`admin.py` 已经承载用户、IM、schedule、agent、KB connectors、diagnostics 和 observability
多类命令，是当前最容易产生并行冲突的文件。

状态：implementation spec `2026-06-02-admin-cli-module-split` 已完成，实际 CLI 实现已迁入
`platform.admin_cli`；legacy admin shim 已删除。

建议目标：

```text
src/fleetent/platform/admin_cli/
  __init__.py
  common.py
  main.py
  users.py
  im.py
  schedules.py
  agents.py
  kb_connectors.py
  diagnostics.py
  observability.py
```

保留：

- `fleetent-admin` console script 行为不变，并直接指向 `fleetent.platform.admin_cli.main:main`。
- canonical `fleetent.platform.admin_cli` public entrypoint。

不做：

- 不改命令语义。
- 不新增 HTTP API。
- 不引入权限模型。

### 2. `governance-package-migration`

状态：implementation spec `2026-06-02-governance-package-migration` 已完成，权限审批、quota、
audit log、blocklist、agent policy 已迁入 `fleetent.governance`；legacy 顶层 import shim 已删除。

保留：

- canonical `fleetent.governance.*` public API。
- 既有数据库表、配置 namespace 和业务语义不变。

不做：

- 不新增 Alembic migration。
- 不迁移 runtime、platform、channels、infrastructure 其他模块。

### 3. `memory-layer-package-migration`

状态：implementation spec `2026-06-02-memory-layer-package-migration` 已完成，已将
top-level User Memory 实现迁入 `intelligence/memory/`，拆分 models、store、extraction、search、operations、
maintenance；legacy shim 已删除。

建议目标：

```text
src/fleetent/intelligence/memory/
  __init__.py
  models.py
  store.py
  extraction.py
  search.py
  operations.py
  maintenance.py
```

保留：

- canonical `fleetent.intelligence.memory` public API。
- `MemoryItem`、`MemoryType`、`extract_and_update`、`search`、public operations、
  `run_memory_maintenance` 等 public API 不变。

### 4. `runtime-package-migration`

将 agent runtime 相关代码迁入 `runtime/`。这一步影响面最大，必须单独做。

建议目标：

```text
src/fleetent/runtime/
  __init__.py
  agent_loop.py
  context.py
  sub_agent.py
  model_routing.py
```

注意：

- `agent_loop.py` import `tools.py` 有副作用注册工具，迁移时必须保留启动顺序。
- `context_mgr._keep_tail()` 使用 identity check，不得顺手重构行为。
- 旧 `fleetent.agent_loop` 必须保留 shim，避免 server / tests / CLI 同步大改。

### 5. `platform-user-center-package-migration`

迁移 user / API key / agent store / auth 相关模块。

候选：

- `user_store.py`
- `api_key_store.py`
- `auth.py`
- `agent_store.py`
- `user_admin_api.py`
- `invite_store.py`

这部分和 platform / user-center v1.0 owner 强相关，执行前需要确认 owner 和业务边界。

### 6. `channels-package-migration`

迁移 IM / webhook / schedule 入口。

候选：

- `im_gateway/` 归入或重命名为 `channels/im_gateway/`
- `im_user_store.py`
- `im_connector_config.py`
- `im_connector_manager.py`
- `im_connector_store.py`
- `im_channel_allowlist.py`
- `webhook_router.py`
- `cron_scheduler.py`
- `schedule_store.py`

这一步应等 user identity / channel binding 边界稳定后再做。

### 7. `integrations-and-infrastructure-package-migration`

状态：implementation spec `2026-06-02-integrations-package-migration` 已完成，top-level MCP 与 sandbox
实现已迁入 `fleetent.integrations.mcp` 和 `fleetent.integrations.sandbox`；legacy 顶层
import shim 已删除。

后置迁移：

- `config.py` -> `infrastructure/config.py`
- `db.py` -> `infrastructure/db.py`

`config.py` 和 `db.py` 被全仓广泛 import，迁移风险高，应最后处理。

## Shim 策略

迁移 legacy 平铺模块时：

- 新业务逻辑必须放在目标 package。
- 旧路径只保留 re-export public API。
- shim 文件不允许访问数据库、不允许读配置、不允许承载业务逻辑。
- shim 应有测试证明旧 import 路径仍可用。
- 当全仓 import 已迁移后，可在后续 breaking cleanup spec 中删除 shim。

示例：

```python
# src/fleetent/<legacy_module>.py
from fleetent.intelligence.memory import MemoryItem, create, search

__all__ = ["MemoryItem", "create", "search"]
```

## 每次迁移的验收要求

每个实现型迁移 spec 必须：

- 声明 owning package。
- 列出 public API surface。
- 列出 owned tables 和 config namespace，若无变化明确写无。
- 列出 cross-module dependencies。
- 写清 migration / shim plan。
- 先写失败测试证明旧 import 和新 import 都可用。
- 迁移后运行：
  - `PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py`
  - 相关分层测试
  - `uv run ruff check src tests`
  - `uv run mypy src`
  - `uv run pytest -x -q`
  - `openspec validate <change-id> --strict`
  - `git diff --check`

## 不建议现在做的事

- 不一次性把所有顶层 `.py` 移到 package。
- 不在同一个 spec 中同时迁移 runtime、platform 和 infrastructure。
- 不在迁移时顺手改业务行为。
- 不在没有 owner 对齐前迁移 user-center / platform 大块代码。
- 不提前移动 `config.py` / `db.py`。

## 下一步建议

先做 `admin-cli-module-split`。

理由：

- 当前 `admin.py` 是最新 Pilot MVP 之后增长最快的文件。
- 拆分它不会改变数据库 schema 或核心 runtime。
- 它能立刻降低后续 observability、KB operations、diagnostics、platform 管理命令并行开发冲突。

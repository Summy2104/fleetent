## Why

`src/fleetent/admin.py` 已经增长到 500+ 行，承载用户、IM、agent/channel、schedule、KB connector、
diagnostics 和 observability 多类命令。Pilot MVP 后，admin CLI 会继续承接运维和管理入口；如果继续把所有命令塞进单文件，后续并行开发很容易冲突。

本 change 只做结构拆分：把 admin CLI 迁入 `platform.admin_cli` package，并保留 `fleetent.admin:main`
作为 console script 入口。命令行为、参数、输出和退出码不变。

## What Changes

- 新增 `src/fleetent/platform/admin_cli/` package。
- 按命令域拆分 admin CLI：
  - `main.py`：根 parser、子命令注册、分发。
  - `common.py`：输出脱敏、summary formatting、时间解析等共享 helper。
  - `users.py`：create-user / list-users / rotate-key / seed-builtin-admin。
  - `im.py`：list-pending / approve-user / block-user。
  - `agents.py`：assign-channel / unassign-channel / set-default-agent。
  - `schedules.py`：list-schedules / add-schedule / remove-schedule。
  - `kb_connectors.py`：kb connectors list/check/status/sync。
  - `diagnostics.py`：diagnostics export / retention。
  - `observability.py`：observability traces / usage / performance。
- 将 `src/fleetent/admin.py` 改为薄 shim：
  - re-export `main`
  - 不承载业务逻辑
- `pyproject.toml` 暂不改，`fleetent-admin = "fleetent.admin:main"` 继续可用。
- 保留现有 CLI 行为测试，并新增新 package import / shim 测试。

## Out of Scope

- 不改命令名、参数、输出格式或退出码。
- 不迁移到 Click / Typer。
- 不新增 HTTP API 或 Admin UI。
- 不引入新的权限模型。
- 不修改数据库 schema。
- 不修改 `fleetent` 用户运行入口。
- 不拆分业务 store，只拆 admin CLI 组织。

## Module Boundary Impact

- **Owning package**：`platform.admin_cli`。
- **Public API surface**：`fleetent.platform.admin_cli.main.main` 成为新实现入口；
  `fleetent.admin.main` 保持为 compatibility shim。
- **Owned tables**：无。
- **Config namespace**：无。
- **Cross-module dependencies**：admin CLI 继续调用 user_store、agent_store、schedule_store、knowledge-base、
  observability 等 public API；不直接新增跨模块业务依赖。
- **Migration / shim plan**：`src/fleetent/admin.py` 只 re-export `main`，console script 暂不改，后续可在 breaking cleanup
  中把 console script 指向 `fleetent.platform.admin_cli.main:main`。

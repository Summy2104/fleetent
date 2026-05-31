## Why

当前代码执行能力没有任何启用开关：`run_code` 工具在 `tools.py` 顶层 `@tool(risk_level="medium")` 注册，import 即生效，所有 agent 一律可见、可调用。无法关闭、无法按 agent 限定，也无法在 Docker 不可用时优雅降级——一旦宿主机没有 Docker，`run_code` 仍会注册并暴露给 AI，调用时才以 `docker run failed` 报错。

`docs/capabilities/sandbox.md` 的「启用/关闭控制（三态模式）」要求：全局 `mode`（`off` / `selective` / `all`）+ agent 级 `features.code_execution` 开关双层控制，且 Docker 不可用时自动降级为 `off` 不阻断平台启动。这是把「代码执行能力是否对某 agent 可用」从硬编码改为可治理的配置项。

沙箱后端保留 Docker，本 change 的降级判定基于现有 `docker` CLI 可用性探测。

## What Changes

- 引入**三态全局 `mode`**（来自 sandbox.md）：
  - `off`：`run_code` 工具**不注册**，AI 完全不知道代码执行能力存在。
  - `selective`：默认关闭，仅 `features.code_execution: true` 的 agent 可用。
  - `all`（默认）：所有 agent 可用，agent 可显式设置 `code_execution: false` 关闭。
- 引入 **agent 级 `features.code_execution`** 开关：`agent_store` 的 agent 定义增加 `features` 字段（JSON），承载 `code_execution: bool | None`（None=未声明，跟随 mode 默认）。
- **Docker 可用性探测 + 自动降级**：平台启动时探测 `docker` CLI 是否可用，不可用则把生效 mode 降级为 `off` 并记录警告，平台正常启动。
- **启用判定函数**：`is_code_execution_enabled(mode, agent_features) -> bool` 纯函数，按三态 + agent 开关 + 降级状态判定某 agent 是否可用代码执行。
- 工具注册侧据 mode 决定是否注册 `run_code`（`off`/降级 → 不注册）；selective/all 下进一步在调用入口按 agent 开关拒绝（agent 不可用时拒绝执行并告知 AI）。

## Capabilities

### New Capabilities
- `sandbox-enablement-control`: 代码执行能力的三态启用控制——全局 `mode`（`off`/`selective`/`all`，默认 `all`）+ agent 级 `features.code_execution` 双层开关；`off` 不注册 `run_code` 工具；`selective` 仅授权 agent 可用；`all` 默认全开但 agent 可显式关闭；Docker 不可用自动降级为 `off` 不阻断启动。

### Modified Capabilities
<!-- 不修改既有 spec。既有 sandbox-client 主 spec 为 microsandbox 历史版本，与本 change 引入的 Docker 后端能力无对应需求，故不以 MODIFIED 表达。Docker CLI 可用性探测属 Docker 后端新增能力，落在本 change 新 capability `sandbox-enablement-control` 下以 ADDED 表达。 -->

### 共享资源 owner（本 change 拥有）
- **`agent_store.features` JSON 列 owner = SB3**：本 change 引入 `features` 列并提供旧库 ALTER 迁移。SB5（密钥注入）复用同一列放 `sandbox_env`，不重复加列。
- **`config/settings.yaml` 的 `sandbox:` 段骨架 owner = SB3**：本 change 首个落地者建该段并写入 `sandbox.mode`；SB2 追加 `scope`/`idle_hours`，SB4 追加 `resources`。
- **run_code 上下文通道 owner = SB3**：本 change 拥有「新增 agent/session 上下文经 agent_loop → tool_registry.dispatch → tools.run_code 的传递通道」的实现任务；SB2（scope `acquire`）、SB5（agent_env）复用该通道，不各自重造。

## Impact

- **代码**：
  - 新增 `src/fleetent/sandbox_enablement.py`（`Mode` 枚举 + `is_code_execution_enabled()` 纯函数 + 启动期 `resolve_effective_mode(configured_mode, docker_available)`）。
  - 修改 `src/fleetent/sandbox_client.py`：增加 `docker_available() -> bool`（探测 `docker` CLI，失败返回 False，不抛异常）。
  - 修改 `src/fleetent/agent_store.py`（**features 列 owner**）：`Agent` 数据类增加 `features: dict[str, Any]`（默认空 dict）；建表/读写 SQL 增加 `features` 列（裸 aiosqlite SQL）；`_init_db` 现用 `CREATE TABLE IF NOT EXISTS`，对已存在的旧表不会加列 → **必须显式 `ALTER TABLE agents ADD COLUMN features TEXT` 迁移**（否则旧库读 `row[features]` 越界），旧行读取 `json.loads(row[...] or "{}")` 回退 `{}`。
  - **run_code 上下文通道改造（本 change owner）**：修改 `src/fleetent/agent_loop.py`（调用 `dispatch` 处透传 agent/session 上下文）→ `src/fleetent/tool_registry.py`（`dispatch` 增加上下文入参并向下传递）→ `src/fleetent/tools.py`（`run_code` 据上下文取 agent features）。SB2/SB5 复用此通道。
  - 修改 `src/fleetent/tools.py` / `tool_registry` 注册路径与 server 启动：据生效 mode 决定 `run_code` 是否注册；调用入口按 agent 开关拒绝。
- **配置**：新增沙箱 `mode`（默认 `all`）配置项。
- **测试**：新增 `tests/test_sandbox_enablement.py`；扩充 `tests/test_agent_store.py` 覆盖 `features` 列读写与旧行兼容；`tests/test_sandbox_client.py` 增 `docker_available` 探测用例。Docker CLI 与 SQLite 全部隔离/mock（`patch asyncio.create_subprocess_exec`、`monkeypatch DB_PATH`）。
- **不影响**：SB2 生命周期、SB4 资源配置、agent_loop 主循环、permission_gate；不引入新依赖。

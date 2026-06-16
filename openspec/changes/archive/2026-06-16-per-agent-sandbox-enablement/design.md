## Context

`integrations/sandbox/enablement.py` 用 `SETTINGS_PATH = paths.platform_yaml_path()` 读 `sandbox.mode`
（`load_sandbox_mode`/`_read_raw_mode`，默认 `all`）。`Mode` 枚举含 `OFF`/`SELECTIVE`/`ALL`。
`get_effective_mode(backend)` = `resolve_effective_mode(load_sandbox_mode(), backend.available())`：无 Docker → OFF，否则用配置 mode（一次性缓存）。
`is_code_execution_enabled(mode, code_execution)`：OFF→False；SELECTIVE→`code_execution is True`；ALL→`code_execution is not False`。
调用方：`runtime/loop.py`（schema 过滤点的启用判定）、`tools/file_tools.py`（workspace_mount 门）、`im_gateway/normalizer.py`（算 sandbox_mode 传入 loop）、`runtime/agent_app.py`（`mode is not OFF` 决定 orphan/idle wiring）、`server.py`（admin 展示 sandbox_mode）。叠加 Change 1（resources/lifecycle/skill_mount 停读）后，`mode` 是 `integrations/sandbox` 对 `platform.yaml` 的最后读取点。

## Goals / Non-Goals

**Goals:**
- 删除 `sandbox.mode` 的 `platform.yaml` 读取；`enablement.py` 不再 `paths.platform_yaml_path()`。
- `Mode` 收敛 `{OFF, ON}`；`get_effective_mode` 只依后端 `available()`。
- `features.code_execution` 成为唯一 per-agent 策略（未声明=开、显式 false=关），保留无 Docker→OFF 降级。
- 收口护栏：`integrations/sandbox` 整体零读 `platform.yaml`。

**Non-Goals:**
- 不改 `features` 列存储 / agent 定义 schema（`code_execution` 已存在）。
- 不改 approval-minimization / action-gate 代码语义——仅重写部署指引文档，保留"免审批仅在 `sandbox_capable` 成立时生效"不变式。
- 不改容器创建、后端 `available()` 探测行为。

## Decisions

1. **Mode 收敛**：`Mode` 去 `SELECTIVE`/`ALL`，保留 `OFF`，新增/改名 `ON`（语义 = 旧 `ALL` 的"能力可用、默认放"）。为最小化调用方改动，保留 `Mode.OFF` 标识不变；`ALL`→`ON`。`get_effective_mode(backend)` = `ON if await backend.available() else OFF`（删 `load_sandbox_mode`/`_read_raw_mode`/`resolve_effective_mode` 对 configured mode 的依赖；`resolve_effective_mode` 可简化为只看可用性或移除）。
2. **启用判定**：`is_code_execution_enabled(mode, code_execution)` = `mode is not Mode.OFF and code_execution is not False`（OFF→False；ON→未声明/真=开、显式假=关）。保留今日 `all` 语义，删 `selective` 分支。
3. **删 platform.yaml 读取**：移除 `enablement.py` 的 `SETTINGS_PATH`/`load_sandbox_mode`/`_read_raw_mode`。`server.py` admin 展示的 `sandbox_mode` 改为展示 ON/OFF（运行时能力）。
4. **调用方适配**：`runtime/loop.py`、`file_tools.py`、`im_gateway/normalizer.py`、`agent_app.py` 中 `Mode.ALL/SELECTIVE` 的引用清理为 ON/OFF 模型；`mode is not OFF` 类判定不变。
5. **shipped platform.yaml**：删 `sandbox.mode`；迁移文档（off→全 agent code_execution:false、selective→仅授权 agent true）。不加弃用告警。
6. **收口护栏**：扩展/新增 guardrail 测试断言 `integrations/sandbox` 各模块不引用 `paths.platform_yaml_path()`（叠加 Change 1 后整体零读）。

## Risks / Trade-offs

- **BREAKING（机群语义）**：丢弃 `selective` 默认拒与 `off` 全机 kill-switch；多 agent 平台部署须改用 per-agent `code_execution`。迁移文档承载；用户单 agent 场景无损（`features.code_execution` 已够）。
- **调用方面广**：`Mode` 取值变更触及 5 个文件——以 TDD + 类型检查（mypy）确保所有 `Mode.ALL/SELECTIVE` 引用清理干净；保留 `OFF` 标识降低改动面。
- **approval-minimization 耦合**：`action_gate` 的 medium 免审批依赖 `sandbox_capable`（运行时能力），本 change 不改其代码，仅文档重写；需确认 `sandbox_capable` 的计算不依赖被删的 `mode` 配置值（只依赖运行时 ON/OFF + agent code_execution），否则需同步适配。实现期先核 `sandbox_capable` 来源。
- **顺序依赖**：本 change 假定 Change 1 已落（resources/lifecycle 停读），故"整体零读"护栏在此收口；若单独执行本 change，护栏断言应仅限 enablement 不读，避免 Change 1 未落时误失败。实现期按合并顺序处理。
- **缓存**：`get_effective_mode` 的进程级缓存语义保留（一次探测），不受影响。

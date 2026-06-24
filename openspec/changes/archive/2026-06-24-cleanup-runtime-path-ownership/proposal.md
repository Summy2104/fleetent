## Why

`tenant-first-layout` 已把管理库、tenant KB、agent home 和 agent-side DB 主干迁到目标布局，但本地重建后仍能看到 `FLEETENT_HOME/data/` 被写入：

- `data/traces.jsonl` 来自旧 JSONL trace fallback。
- `data/logs/` 来自 platform structured logging 默认目录。
- 代码默认路径仍保留 `data/workspaces`、`data/tool_spillover`、`data/sandbox_output`、`data/sessions`、`data/diagnostics`、`data/im_approvals.json` 等潜在写入点。
- 多个 e2e helper 仍拼旧布局 `home/agents/<name>/data/default/<agent>/agent_state.db`。

这会削弱 tenant-first 的核心边界：根目录应只承载跨租户控制面和宿主级产物；tenant 下承载租户资源；agent home 下承载 agent runtime 产物。`FLEETENT_HOME/data/` 继续存在会让后续 node/skill/file-exchange 继续把新产物写错层级。

## What Changes

- 明确 `FLEETENT_HOME` 顶层允许产物：`management.db`、配置文件、dev secret、`node/`、根级 `logs/`、根级 `diagnostics/`、`tenants/`。
- **不迁移** `management.db`、`platform.yaml`、平台 `.env`、`.dev_secret_key` 到 `platform/` 子目录；它们继续作为根级跨租户控制面/宿主级文件。
- structured platform logs 默认从 `FLEETENT_HOME/data/logs/` 改为 `FLEETENT_HOME/logs/`。
- platform diagnostics export 默认从 `FLEETENT_HOME/data/diagnostics/` 改为 `FLEETENT_HOME/diagnostics/`。
- agent runtime boot 必须把所有 agent-run 产物重定向到 `<agent-home>/data/`：legacy JSONL trace、sessions、diagnostics、IM approvals、workspace、tool spillover、sandbox output。
- sandbox workspace 与文件工具 workspace 默认不得再落 `FLEETENT_HOME/data/workspaces/`；agent runtime 下必须落 `<agent-home>/data/workspaces/`。
- 更新 e2e helper 与路径护栏，禁止新代码/测试继续依赖旧 `home/agents/.../data/default/...` 或默认 `FLEETENT_HOME/data/*` agent runtime 写入。
- dev/pilot 仍重建 home；不做旧 `data/` 自动迁移。

## Capabilities

### Modified Capabilities

- `runtime-paths`: 补齐 home / tenant / agent 三层文件归属，新增根级 `logs_dir()` / `diagnostics_dir()` 与 agent runtime data sink 规则；默认不再使用 `FLEETENT_HOME/data/`。
- `agent-runtime-cli`: `fleetent agent run` 启动时重定向全部 agent runtime 文件 sink 到 `<agent-home>/data/`。
- `observability`: structured program logs 与 agent run traces 的默认路径分层；platform logs 根级，agent logs agent 级。
- `sandbox-large-output-spill`: sandbox output spill 在 agent runtime 下落 `<agent-home>/data/sandbox_output/`。
- `file-tools-sandbox-execution`: workspace host root 在 agent runtime 下落 `<agent-home>/data/workspaces/`。
- `diagnostics-redaction-export-hardening`: platform diagnostics 默认根级 `diagnostics/`，agent diagnostics 默认 agent data；导出继续递归排除 SQLite 与 secret。

## Impact

- **owning package**: `paths`, `runtime.agent_app`, `structured_logging`, `eval_logger` 或其替代 trace API、`integrations.sandbox`, `tools.result_truncation`, `observability.diagnostics`, e2e helpers。
- **public API surface**: 可能新增 `paths.logs_dir()`、`paths.diagnostics_dir()`，以及 agent runtime data-sink rebind helper；现有 `paths.data_dir()` 需退役为 legacy-only 或仅测试兼容。
- **owned tables**: 无。
- **config namespace**: 无新增配置；仅默认路径变化。显式配置的绝对日志/diagnostics 路径继续优先。
- **cross-module dependencies**: agent runtime 仍不得 import `fleetent.platform.*`；路径重定向通过 runtime 注入模块级 sink 或中心 path provider，不引入 platform 反向依赖。
- **migration / shim plan**: 不做旧文件自动迁移。保留必要测试 monkeypatch 能力；`paths.data_dir()` 若保留，必须标注 legacy/非默认写入，不得被新 managed/runtime 代码作为默认产物根。

## Open Questions

无。已确认：

- 不新增 `platform/` 层。
- `management.db`、`platform.yaml`、平台 `.env`、`.dev_secret_key` 保持根级。
- platform logs / diagnostics 使用根级 `logs/` / `diagnostics/`。
- agent runtime 产物全部进入 `<agent-home>/data/`。

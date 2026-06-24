## Context

`tenant-first-layout` 之后的目标树应为：

```text
FLEETENT_HOME/
├── management.db
├── platform.yaml
├── .env
├── .dev_secret_key
├── logs/
├── diagnostics/
├── node/
└── tenants/<tenant>/
    ├── kb.db
    ├── kb_vectors.db
    └── agents/<agent>/
        ├── agent.yaml
        ├── .env
        ├── .fleetent.pid
        ├── skills/
        ├── exchange/
        └── data/
            ├── agent_state.db
            ├── agent_vectors.db
            ├── agent_memory.db
            ├── agent_memory_vectors.db
            ├── traces.jsonl          # legacy JSONL trace fallback, until retired
            ├── sessions/
            ├── logs/
            ├── diagnostics/
            ├── workspaces/
            ├── tool_spillover/
            ├── sandbox_output/
            └── im_approvals.json
```

当前实际树仍出现：

```text
FLEETENT_HOME/data/logs/
FLEETENT_HOME/data/traces.jsonl
```

代码还存在潜在默认：

```text
FLEETENT_HOME/data/workspaces/
FLEETENT_HOME/data/tool_spillover/
FLEETENT_HOME/data/sandbox_output/
FLEETENT_HOME/data/sessions/
FLEETENT_HOME/data/diagnostics/
FLEETENT_HOME/data/im_approvals.json
```

这些默认路径让 `FLEETENT_HOME/data/` 继续承担“杂物根”，与 tenant-first 的分层不变量冲突。

## Goals / Non-Goals

**Goals:**

- 明确三层归属规则，并用测试锁住实际产物树。
- 根级 platform/host 产物不再放进 `data/`，默认改为 `logs/` 与 `diagnostics/`。
- agent runtime 产物全部在 `<agent-home>/data/`，包括 legacy trace JSONL、workspace 与 spillover。
- 修正 e2e helper 的旧路径，避免测试继续制造或读取旧布局。
- 增加静态/动态护栏，防止新默认路径回退到 `FLEETENT_HOME/data/`。

**Non-Goals:**

- 不迁移旧 home 中的 `data/` 内容；dev/pilot 重建。
- 不移动 `management.db` 到子目录。
- 不新增 `platform/` 目录层。
- 不在本 change 退休 legacy `fleetent.eval_logger` API；只把它的默认落点放对。
- 不重构 file-exchange 归属模型；仅保证其现有 `exchange/` 仍在 agent home 下。

## Decisions

### D1: 根目录承载跨租户控制面和宿主级产物

根目录保留：

- `management.db` 及 SQLite sidecar。
- `platform.yaml`、`.env`、`.dev_secret_key`。
- `node/`。
- `logs/`：platform structured logs 默认目录。
- `diagnostics/`：platform diagnostics export 默认目录。
- `tenants/`。

不新增 `platform/` 层，避免把 `management.db`、配置与 installer 再次迁移，控制变更范围。

### D2: `FLEETENT_HOME/data/` 不再是默认写入根

`paths.data_dir()` 若保留，必须是 legacy compatibility 或测试兼容，不得作为新默认产物根。新增或改造默认路径应通过语义化 accessor：

- `paths.logs_dir()` → `base/logs`
- `paths.diagnostics_dir()` → `base/diagnostics`
- `paths.tenant_agent_data_dir(tenant, agent)` → `base/tenants/<tenant>/agents/<agent>/data`

### D3: agent runtime boot 统一重绑定 agent-run sinks

`fleetent agent run` 已经知道 `home_dir`。启动时应在任何运行时基础设施初始化前，把下列 sink 统一设到 `home_dir/data`：

- session JSON：`data/sessions/`
- IM approvals：`data/im_approvals.json`
- diagnostics：`data/diagnostics/`
- structured agent logs：`data/logs/`
- legacy JSONL trace：`data/traces.jsonl`
- workspace root：`data/workspaces/`
- tool spillover：`data/tool_spillover/`
- sandbox output spill：`data/sandbox_output/`

这样 `paths.data_dir()` 的 legacy 默认不会在 agent process 中生效。

### D4: platform diagnostics 和 agent diagnostics 分层

platform diagnostics 默认输出到 `FLEETENT_HOME/diagnostics/`；agent runtime diagnostics 默认输出到 `<agent-home>/data/diagnostics/`。两者都必须递归排除 SQLite 主库、WAL/SHM sidecar、secret 与 `.env` 明文值。

### D5: 动态 home inventory guardrail

新增一个集成或 e2e-lite 测试，使用临时 `FLEETENT_HOME` boot 一个最小 agent runtime 或调用同等初始化路径，断言：

- `home/data/` 不存在，或为空且不是默认写入目标。
- `home/logs/` 可存在，仅承载 platform logs。
- `home/diagnostics/` 可存在，仅承载 platform diagnostics。
- agent runtime 文件只出现在 `tenants/<tenant>/agents/<agent>/data/`。

## Risks / Trade-offs

- **Risk: platform 与 agent 共用 structured logger 模块。** → platform 通过 `configure_logging(Settings)` 使用根级 logs；agent 通过 `_configure_logging_from_agent()` 继续显式传 `<agent-home>/data/logs`，避免改 logger 语义造成混淆。
- **Risk: module-level constants 在 import 时已绑定旧 path。** → runtime boot 必须在相关使用前重绑定；测试要覆盖 `eval_logger.TRACE_PATH`、sandbox spill、tool spillover、workspace root。
- **Risk: `paths.data_dir()` 仍被大量测试使用。** → 不在本 change 物理删除；先把生产默认写入和 guardrail 收口，后续可单独 retire。
- **Risk: e2e helper 旧路径修正可能暴露预存 e2e 失败。** → tasks 用最窄 helper 测试和相关 e2e smoke 验证路径，不要求全量 e2e 绿。

## Module Boundary Impact

- **owning package**: `runtime` owns agent process sink rebinding; `paths` owns semantic accessors; `observability` owns logging/diagnostics defaults; `integrations.sandbox` and `tools` consume injected workspace/spillover dirs.
- **public API surface**: semantic path accessors and runtime sink rebinding helper.
- **owned tables**: 无。
- **config namespace**: 无。
- **cross-module dependencies**: runtime may import independent infra modules to rebind sinks; infra modules must not import `fleetent.platform.*`; platform must not write agent home.
- **migration / shim plan**: no file migration; legacy accessors remain but new guardrails prevent canonical code from using them as default runtime roots.

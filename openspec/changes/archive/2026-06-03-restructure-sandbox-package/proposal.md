## Why

落实已归档蓝图 `runtime-package-blueprint`(spec `package-architecture`)的**第一个逐包迁移**:把张洋平铺的 7 个 sandbox 模块(`sandbox_*.py`,1029 行)收进 `integrations/sandbox/`。sandbox 是「工具依赖的可插拔外部执行后端」(Docker daemon 适配器),与 `integrations/mcp/`、`connectors` 同类;迁入后边界清晰、与 `integrations/mcp/` 对称,并消除架构文档中 `integrations/sandbox/` 与平铺现状的不一致。

本 change 立起整套迁移范式(移文件去前缀 → `__init__` 公共 API → 旧路径 shim → 改调用方 → 全量绿),后续 5 个逐包 change 照此推进。

## What Changes

- **迁移 7 文件**到 `src/fleetent/integrations/sandbox/`,去 `sandbox_` 前缀:
  `sandbox_client.py`→`client.py`、`sandbox_config.py`→`config.py`、`sandbox_manager.py`→`manager.py`、`sandbox_enablement.py`→`enablement.py`、`sandbox_cleanup.py`→`cleanup.py`、`sandbox_secrets.py`→`secrets.py`、`sandbox_output_truncation.py`→`output_truncation.py`(用 `git mv` 保留 blame)。
- **建 `integrations/sandbox/__init__.py`** re-export 公共 API(外部真正用到的:`SandboxClient`/`ExecResult`、`Mode`/`load_sandbox_mode`/`resolve_effective_mode`/`get_effective_mode`/`is_code_execution_enabled`、`cleanup_orphans`、`SandboxManager`/`Scope`、`build_sandbox_env`/`is_sensitive_name`、`truncate_stream`、`load_sandbox_resources`/`load_sandbox_lifecycle`/`build_resources_by_scope`/`SandboxResources`/`SandboxLifecycle`/`NetworkPolicy`)。
- **改包内模块间 import**(7 文件内部相互引用)。
- **旧扁平路径留 re-export shim**(7 个 `sandbox_*.py` 各一行 `from ... import *` + 显式 re-export,不承载逻辑)。
- **改 src 直接调用方**到新公共 API:`agent_loop.py`、`tools.py`、`server.py`、`eval_logger.py`(全部从 `fleetent.integrations.sandbox` 导入)。
- 行为不变、无 schema 变更。

## Capabilities

### Modified Capabilities
- `package-architecture`: 记录 sandbox 域**已完成包化**——`integrations/sandbox/` 成包、公共 API 收口、旧路径仅 shim、契约/行为不变。这是蓝图迁移序列的可验证进度项,不改既有约定。

## Impact

- **代码**:新增 `src/fleetent/integrations/sandbox/`(7 模块 + `__init__.py`);旧 7 个 `sandbox_*.py` 变 shim;`agent_loop`/`tools`/`server`/`eval_logger` 改 import。
- **测试**:大量 `tests/**` import `fleetent.sandbox_*` —— 优先靠 shim 不动;逐步把测试 import 改到新路径(本 change 至少把直接相关的 sandbox 测试改到新路径,其余靠 shim 兜底)。
- **不受影响**:运行时行为、`run_code` 工具契约、Docker 隔离逻辑、schema 全部不变。
- **依赖**:蓝图 `runtime-package-blueprint`(已归档);`integrations/` 包已存在(`mcp/` 同款)。
- **后续**:session → skills → model → tools → runtime(殿后)。
- **分支**:基于并合回 `main`。

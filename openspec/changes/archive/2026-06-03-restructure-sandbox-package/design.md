## Context

蓝图 `runtime-package-blueprint`(spec `package-architecture`)已确立目标结构与迁移约定。本 change 是其第一个逐包落地。现状:`src/fleetent/sandbox_*.py` 7 文件平铺;`integrations/` 已有 `mcp/`(同款「工具执行后端」)。

src 直接调用方(已扫描):
- `agent_loop.py`:`from fleetent.sandbox_enablement import Mode, is_code_execution_enabled` + `from fleetent import sandbox_enablement`
- `tools.py`:`sandbox_secrets.build_sandbox_env`、`sandbox_manager.SandboxManager`、`sandbox_client.{ExecResult,SandboxClient}`、`sandbox_output_truncation as sot`
- `server.py`:`sandbox_enablement.{Mode,load_sandbox_mode,resolve_effective_mode}`、`sandbox_client.SandboxClient`、`sandbox_cleanup.cleanup_orphans`
- `eval_logger.py`:`from fleetent import sandbox_secrets`
- `tests/**`:多处 import `fleetent.sandbox_*`(靠 shim 兜底,逐步迁)

## Goals / Non-Goals

**Goals**:7 文件迁入 `integrations/sandbox/`、去前缀、`__init__` 收口公共 API、src 调用方改新路径、旧路径 shim 兜底、全量门禁绿、行为不变。
**Non-Goals**:不改任何运行时行为 / `run_code` 契约 / Docker 逻辑 / schema;不重写模块内部;不一次改完所有测试 import(shim 兜底,渐进)。

## Decisions

### D1 — 文件映射(去前缀)
```
sandbox_client.py            → integrations/sandbox/client.py
sandbox_config.py            → integrations/sandbox/config.py
sandbox_manager.py           → integrations/sandbox/manager.py
sandbox_enablement.py        → integrations/sandbox/enablement.py
sandbox_cleanup.py           → integrations/sandbox/cleanup.py
sandbox_secrets.py           → integrations/sandbox/secrets.py
sandbox_output_truncation.py → integrations/sandbox/output_truncation.py
```
用 `git mv` 保留历史。

### D2 — 公共 API 收口 `integrations/sandbox/__init__.py`
re-export 外部用到的符号(以实际调用方 + 测试为准):
`SandboxClient, ExecResult`(client);`Mode, load_sandbox_mode, resolve_effective_mode, get_effective_mode, is_code_execution_enabled`(enablement);`cleanup_orphans`(cleanup);`SandboxManager, Scope`(manager);`build_sandbox_env, is_sensitive_name`(secrets);`truncate_stream`(output_truncation);`load_sandbox_resources, load_sandbox_lifecycle, build_resources_by_scope, SandboxResources, SandboxLifecycle, NetworkPolicy`(config)。`__all__` 显式列出。

### D3 — 旧扁平路径 shim(不承载逻辑)
每个 `src/fleetent/sandbox_*.py` 改为 shim:从新位置 re-export(`from fleetent.integrations.sandbox.<mod> import *` + 显式名 + `__all__`),不含任何函数/类定义。让暂未迁移的外部调用方(尤其测试)继续可用。

### D4 — 包内 import 调整
7 个模块彼此引用(如 client 用 config/secrets/output_truncation,manager 用 client/config)改为包内引用 `from fleetent.integrations.sandbox.<mod> import ...`。

### D5 — src 调用方改新公共 API
`agent_loop`/`tools`/`server`/`eval_logger` 改成 `from fleetent.integrations.sandbox import ...`。这样核心路径不依赖 shim;shim 只为外部/测试兜底。

### D6 — 测试 import
本 change 把**直接的 sandbox 单测/集成测**(如 `test_sandbox_*`、`test_server_lifespan` 中 sandbox 相关)import 改到新路径;其余大面积 import 靠 shim,留后续清理。避免一次性巨改。

## Risks / Trade-offs

| 风险 | 缓解 |
|------|------|
| import 改漏 | shim 兜底 + 全量 pytest + mypy;关键符号 import 自检 |
| 循环 import(sandbox 模块互引) | 包内绝对引用,保持原有依赖方向不变 |
| `__init__` 漏导出某符号致外部断 | 以「所有 src+test 调用方实际用到的符号」为导出清单依据;全量测试暴露遗漏 |
| `sandbox_config` 等被测试直接构造内部类 | 这些类(SandboxResources 等)纳入公共 API 导出 |

## 验收

- `integrations/sandbox/` 成包,`__init__.py` 收口公共 API,`__all__` 显式。
- 7 个旧 `sandbox_*.py` 仅 re-export(无逻辑)。
- `agent_loop`/`tools`/`server`/`eval_logger` 从 `fleetent.integrations.sandbox` 导入。
- 全量 `ANTHROPIC_API_KEY=sk-test-dummy uv run pytest -q` 绿;`ruff check` 干净;`mypy src` 不新增错误模式。
- 关键符号自检:`from fleetent.integrations.sandbox import SandboxClient, Mode, cleanup_orphans, SandboxManager` 成功。

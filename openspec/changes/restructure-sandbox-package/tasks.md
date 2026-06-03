> 纯结构重构:无新增行为,**用既有全量测试套件作为回归安全网**(每个结构步骤后跑全量,必须保持绿;"红"= 改坏了 import/行为,立即修)。

## 1. 基线

- [ ] 1.1 记录基线:`ANTHROPIC_API_KEY=sk-test-dummy uv run pytest -q` 全绿;`mypy src` 现有错误数(作为"不新增"基准)

## 2. 移文件 + 建包

- [ ] 2.1 `git mv` 7 文件到 `integrations/sandbox/` 去前缀(client/config/manager/enablement/cleanup/secrets/output_truncation.py)
- [ ] 2.2 改包内模块间 import 为 `fleetent.integrations.sandbox.<mod>`;`uv run python -c "import fleetent.integrations.sandbox.client"` 等逐模块 import 自检通过
- [ ] 2.3 建 `integrations/sandbox/__init__.py`:re-export 公共 API + 显式 `__all__`(SandboxClient/ExecResult、Mode/load_sandbox_mode/resolve_effective_mode/get_effective_mode/is_code_execution_enabled、cleanup_orphans、SandboxManager/Scope、build_sandbox_env/is_sensitive_name、truncate_stream、load_sandbox_resources/load_sandbox_lifecycle/build_resources_by_scope/SandboxResources/SandboxLifecycle/NetworkPolicy);`from fleetent.integrations.sandbox import SandboxClient, Mode, cleanup_orphans, SandboxManager` 自检通过

## 3. 旧路径 shim

- [ ] 3.1 7 个旧 `src/fleetent/sandbox_*.py` 改为 shim:`from fleetent.integrations.sandbox.<mod> import *` + 显式 re-export 名 + `__all__`,**不含任何逻辑**;`uv run python -c "from fleetent.sandbox_client import SandboxClient"` 等旧路径自检仍通过

## 4. 改 src 调用方到新公共 API

- [ ] 4.1 `agent_loop.py`、`tools.py`、`server.py`、`eval_logger.py` 的 sandbox import 改为 `from fleetent.integrations.sandbox import ...`;`uv run python -c "import fleetent.server, fleetent.agent_loop, fleetent.tools"` 导入成功

## 5. 测试 import(直接相关)

- [ ] 5.1 把直接的 sandbox 测试(`tests/**/test_sandbox_*`、`test_server_lifespan` 中 sandbox 相关)import 改到新公共 API;其余大面积 import 暂靠 shim
- [ ] 5.2 跑 sandbox 相关测试子集绿

## 6. 全量门禁 + 文档

- [ ] 6.1 全量 `ANTHROPIC_API_KEY=sk-test-dummy uv run pytest -q` 绿(与基线一致)
- [ ] 6.2 `uv run ruff format` 本 change 文件 + `ruff check src tests` 干净;`mypy src` 不新增错误模式
- [ ] 6.3 更新 `docs/architecture.md`「当前模块地图」:sandbox 从平铺(`sandbox_*.py`)改记为 `integrations/sandbox/`(已与目标态一致)
- [ ] 6.4 `uv run openspec validate restructure-sandbox-package --strict` 通过

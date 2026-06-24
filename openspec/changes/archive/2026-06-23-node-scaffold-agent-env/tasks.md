## 1. runtime：抽出可复用 .env scaffold 入口

- [x] 1.1 写测试（unit）：`ensure_env_scaffold(home_dir)` 在 home 无 `.env` 时生成含 `ma-<64hex>` 形态 `FLEETENT_TUI_TOKEN` 的 `.env`；先见红
- [x] 1.2 写测试（unit）：`.env` 已含 `FLEETENT_TUI_TOKEN` 时调用 `ensure_env_scaffold` 保留原值、不覆盖、不轮换；先见红
- [x] 1.3 写测试（unit）：传入 `referenced_env_names` 时，`.env` 含这些变量名占位（空值），且不含任何真实 secret 值；先见红
- [x] 1.4 实现 `runtime/agent_init.py::ensure_env_scaffold(home_dir, *, referenced_env_names=())`：幂等口径为「`.env` 不存在或缺 `FLEETENT_TUI_TOKEN` 才写」；令 1.1–1.3 见绿
- [x] 1.5 改 `scaffold_agent_home` 复用 `ensure_env_scaffold`，删除内联 `.env` 生成；跑 `agent_init` 既有测试确认仍绿（必要时补「文件存在但缺 token 也回灌」用例）

## 2. node reconcile：materialize 时 scaffold .env

- [x] 2.1 写测试（unit/node）：`_write_home` 写完 `agent.yaml` 后，目标 home 出现含 `FLEETENT_TUI_TOKEN` 的 `.env`；先见红
- [x] 2.2 写测试（unit/node）：home 已存在含 token 的 `.env` 时，`_write_home` 不改其内容（幂等）；先见红
- [x] 2.3 实现：`_write_home` 在写 `agent.yaml` 后调用 `ensure_env_scaffold`（referenced_env_names 由 desired config 解析为 `AgentFile` 后取 `_referenced_env_names`；解析失败则至少写 token 并 log，不吞异常）；令 2.1–2.2 见绿
- [x] 2.4 确认 spawn 顺序：写 agent.yaml → ensure `.env` → `backend.spawn`（agent boot 时 `.env` 已就位）

## 3. 端到端验证与门禁

- [x] 3.1 写测试（integration/e2e，归 slow lane）：新 pin 一个此前无 home 的 agent，node reconcile 后经 forwarder `/forward/agents/{name}/chat`（或既有 managed ingress harness）不再返回 503 `has no env scaffold`；先见红（复用 `tests/e2e` 既有 managed-stack harness）
- [x] 3.2 实现接通后令 3.1 见绿
- [x] 3.3 跑 `PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py` 确认 node→runtime 不触发跨包 internal import 违规（仅经 public API）
- [x] 3.4 change 收尾：`make test-pr` 全绿 + `uv run pytest tests/integration -q` 对照 main 无新增失败

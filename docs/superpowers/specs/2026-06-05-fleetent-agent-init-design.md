# `fleetent agent init` — design & decisions

**日期**: 2026-06-05 · **负责人**: 张洋 · **状态**: 实施中（OpenSpec change `agent-init-cli`）

## 背景

`fleetent agent run <id>` 跑 `FLEETENT_HOME/<id>/agent.yaml`（`agent_config.scan_home` → `load_agent_file`，校验目录名==name）。平台侧 `agent_lifecycle.materialize` 能 DB→home（需控制面/HTTP）。**缺**一条零平台依赖、命令行 scaffold 新 home 的路径——纯运行时/dev 场景下新建可跑 agent 只能手抠目录，且易踩 name≠目录名的坑。

## 方案（用户选 B：模板脚手架，非 DB 物化）

`fleetent agent init <agent-id> [--home PATH] [--force]`：从**内置模板**生成可被 `agent run <id>` 直接跑的自包含 home，零平台/DB 依赖。

与平台 `materialize` 的分工：**init = 模板 / 无 DB**（运行时侧、dev、起新 agent）；**materialize = DB→home**（平台 authoring 侧，控制台创建/更新时自动触发）。互补，不重叠。

## 决策

- **D1 模板内置代码**：`fleetent` 经 `uv tool install` 成全局命令，运行时无仓库工作区，不能读 `config/agent.yaml.example`。`agent_init.py` 用 `AgentFile(name=<id>, version=1, …)` 构造 + `model_dump()` → yaml，保证在 `extra="forbid"` 下 schema-valid 且匹配当前 schema。核心字段，不含 KB/intelligence。
- **D2 `.env` 列引用的 env 名**：扫 `mcp_servers`/`connectors` 的 `*_env` + 必需 `ANTHROPIC_API_KEY`，写 `NAME=` 空值；不 import platform（自包含 `_referenced_env_names`）。
- **D3 复用 `agent_app.resolve_home`**：`--home` 优先否则 `FLEETENT_HOME/<id>`，与 `agent run` 同源，确保 init 出的 home 正是 run 读的 home。
- **D4 覆盖语义**：`agent.yaml` 存在且无 `--force` → `FileExistsError`/非零退出；`--force` 只覆盖 `agent.yaml`，`.env` 始终存在即跳过（护密钥）。
- **D5 单一职责**：逻辑在 `runtime/agent_init.py`（纯函数 `scaffold_agent_home`），`__main__.py` 仅解析 + 调用 + 打印 next steps。

## 验证

- 单测：scaffold 生成可被 `load_agent_file` 加载、name==id、.env 列名无密钥、`--force`/拒绝覆盖/`.env` 保护、默认 home==`FLEETENT_HOME/<id>`；CLI dispatch（`agent init` 解析/用法/缺参）。
- 手动 smoke：`fleetent agent init demo-bot` → `demo-bot/agent.yaml`(name: demo-bot) + `.env`(ANTHROPIC_API_KEY=)。
- mypy 干净；ruff 干净（仅 `agent_store.py` 一处 SIM401 为既有、非本 change）。

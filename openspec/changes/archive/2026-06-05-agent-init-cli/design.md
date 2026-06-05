## Context

运行时侧：`fleetent agent run <id>` → `agent_app.resolve_home(id)`=`FLEETENT_HOME/<id>` → `agent_config.scan_home(home)` → `load_agent_file(home)` 加载 `home/agent.yaml` 且**校验 `name` 等于目录名**。平台侧 `agent_lifecycle.materialize` 能 DB→home（`FLEETENT_HOME/<name>/agent.yaml`+`.env`），但需平台/控制面。缺一条零平台依赖、命令行 scaffold 新 home 的路径。

## Goals / Non-Goals

**Goals:**
- `fleetent agent init <id>` 从内置模板 scaffold 出可被 `agent run <id>` 直接跑的 home。
- 零平台/DB 依赖；`name`==目录名；`.env` 列出引用的 env 名；幂等(`--force`/存在跳过)。

**Non-Goals:**
- 不从平台 DB 物化（那是 `materialize`，已存在）。
- 不含 KB/memory/intelligence 字段（与本轮"后续再做"一致）。
- 不改 `agent run` / install.sh / 平台。

## Decisions

**D1：模板内置在代码，不读仓库文件。**
`fleetent` 经 `uv tool install` 成全局命令，运行时无仓库工作区，读 `config/agent.yaml.example` 不可靠。故 `agent_init.py` 内嵌一个最小默认 agent.yaml 模板（字符串/构造），`name` 在生成时填入 `<id>`。模板字段对齐 `AgentFile` 核心字段；生成后经 `AgentFile.model_validate` 自校验，保证可被运行时加载。

**D2：`.env` 列出模板引用的 env 名。**
扫描生成的 agent（其 `mcp_servers`/`connectors` 的 `*_env` + 必需的 `ANTHROPIC_API_KEY`）收集 env-var 名，写成 `NAME=` 空值行。复用/参照平台 `materialize._env_var_names` 的思路（但本模块自包含，不 import platform）。`.env` 已存在则跳过，绝不覆盖密钥。

**D3：home 解析复用 `agent_app.resolve_home`。**
`--home` 优先，否则 `FLEETENT_HOME/<id>`。与 `agent run` 完全一致，确保 init 出来的 home 正好是 run 读的 home。

**D4：覆盖语义——`agent.yaml` 存在且无 `--force` 报错。**
防误覆盖已有 agent 定义；`--force` 仅覆盖 `agent.yaml`，`.env` 始终存在即跳过（保护密钥）。

**D5：单一职责模块 + 薄 CLI 分支。**
逻辑在 `runtime/agent_init.py`（纯函数 `scaffold_agent_home(agent_id, home, force) -> Path`，可单测，无 I/O 之外副作用）；`__main__.py` 只做参数解析 + 调用 + 打印 next steps。

## Risks / Trade-offs

- **[内置模板与 `AgentFile` schema 漂移]** → 生成后 `model_validate` 自校验；单测加载生成的 agent.yaml 不报错。
- **[name 与目录名不一致导致 run 失败]** → init 强制 `name=<id>`；单测断言生成文件 `name==<id>` 且 `agent run` 的 `load_agent_file` 校验通过。
- **[与平台 materialize 语义重叠]** → 明确分工：init=模板/无 DB；materialize=DB→home。文档与 proposal 标注。

## Migration Plan

纯新增 CLI 子命令 + 模块，无运行时行为变更。回滚 = 删 `agent_init.py` + `__main__.py` 的 `agent init` 分支。

## Context

当前 env 文件初始化存在三个层面的问题：

**初始化逻辑外置**：`make dev-bootstrap` 负责创建 `.fleetent-dev/.env`（平台）、`kb-worker/.env`，但目前完全缺失这两步；node 的 `.env` 由 `dev_node_provision.py` 负责（已存在），但脚本本身也不认 `fleetent` 命令规范。结果是所有服务启动后靠 shell 继承环境变量，文件层面是空的。

**example 文件与实现脱节**：根目录 `.env.example` 包含死变量（`FLEETENT_AUTO_UPGRADE`、`MICROSANDBOX_URL`）；`node.env.example` 缺少 `FLEETENT_FORWARDER_HOST_OVERRIDE`；`agents/default/.env.example` 包含 agent.yaml 字段（`PERMISSION_GATE_*`、`CONTEXT_*`）误作 env var；Makefile `PLATFORM_PORT=8770` 与全项目文档约定的 8765 不一致。

**`collect_env_var_names` 收集不完整**：MCP stdio 服务的 `env:` 块可使用 `"env:VAR_NAME"` 语法引用进程环境变量，但该函数只扫描 `*_env` 结尾的字段，漏掉了内嵌于 `env:` dict value 中的变量名。

## Goals / Non-Goals

**Goals:**
- 三个服务（platform/node/kb-worker）各有对应的 `init-config` 命令，幂等、可独立调用
- `dev-bootstrap` 改为调用这三个命令，env 文件落地到 `FLEETENT_HOME/`
- 四个 `.env.example` 文件与当前代码实现完全对齐，无死变量、无归属错误
- `collect_env_var_names` 覆盖 MCP stdio `env:` 中的 `"env:VAR_NAME"` 模式
- Makefile 端口与文档约定对齐（8765/8766）
- chatbot agent env var 命名与 example 模板对齐（`FLEETENT_MODEL_PRIMARY_API_KEY`）

**Non-Goals:**
- 不改变平台 secret store 或 credential slot 的架构（agent `ANTHROPIC_API_KEY` 为空是独立问题）
- 不处理 node `init-config` 生成 service key（service key 仍由 `dev_node_provision.py` 负责）
- 不修改 `ensure_env_scaffold` 的值注入逻辑（只修收集逻辑）
- 不引入自动端口冲突检测
- **不为 Agent `.env` 引入 copy-from-example 路径**：Agent `.env` 始终是 materialize 的部署
  产物（DB authored 定义 + secret_store → `ensure_env_scaffold`/`_seed_env` 物化），`init-config`
  的 copy-from-example 模式**只适用于三个基础设施服务**（platform/node/kb-worker，这些是
  operator 自己作权威的进程配置）。`agents/default/.env.example` 仅作人工参考模板，无任何代码
  copy 它；本 change 对它的修改是文档对齐，不改变其"非权威"地位。
- **不引入"工具/特性声明自身所需 env var"的机制**：见 Open Questions 中的硬编码 env var 盲区。

## Decisions

### D1：init-config 命令归属

`platform init-config` 已存在于 `platform/platform_cli/init_config.py`，但固定用 `Path.cwd()` 作为根。

**决定**：为 `platform init-config` 增加 `--home` 参数，默认值为 `FLEETENT_HOME`（通过 `paths.base_dir()` 解析），`cwd` 不再作为隐含根。`dev-bootstrap` 传 `--home $(FLEETENT_HOME)` 即可。

`node init-config` 和 `kb-worker init-config` 新建为各自 CLI namespace 下的子命令，逻辑与 `platform init-config` 一致：从对应 `.env.example` 模板复制到目标目录，已有文件跳过（`--force` 覆盖）。

**备选**：在 `dev-bootstrap` 里直接 shell 创建文件。弃用原因：违背"init 逻辑内置到 fleetent 命令"的原则，且无法被非 Makefile 用户复用。

### D2：collect_env_var_names 扩展

MCP stdio 的 `env:` 块是 `dict[str, str]`，值若以 `"env:"` 前缀开头则表示从进程环境解析（`client.py:539`）。

**决定**：在 `collect_env_var_names` 中，对 `model_dump()` 结果额外扫描 MCP server 的 `env`
dict **和 `headers` dict** 的 value，提取 `"env:"` 前缀后的变量名，与 `*_env` 字段结果合并去重。
`headers` 必须一并扫描——`_resolve_env_ref` 在 `client.py` 中同时作用于 stdio `env:` 值
（`_subprocess_env`，line 575）和 http `headers:` 值（`_http_headers`，line 703），漏掉 headers
会导致用 `env:` 引用鉴权头的 http MCP server 的密钥占位缺失。

不修改 `_env_var_names` 在 `materialize.py` 中的调用路径——两者共用 `collect_env_var_names`，自然生效。

### D3：端口约定

全项目文档（README、docs/operations/、docs/capabilities/）统一用 8765 作为平台服务端口。Makefile 的 8770 是历史漂移。

**决定**：Makefile `PLATFORM_PORT` → 8765，`AGENT_PORT` → 8766（`make agent` 直接跑 agent 时用，避免与平台冲突）。同步更新 `docs/operations/local-managed-stack.md` 中使用 8771 的 workaround 注释（macOS sharingd 占 8770 的问题在换成 8765 后需重新评估，但 8765 不在 macOS 常见占用端口列表内）。

### D4：chatbot api_key_env 重命名

`agents/default/agent.yaml.example` 使用 `FLEETENT_MODEL_PRIMARY_API_KEY` 作为模板名，而实际 chatbot agent.yaml 用 `ANTHROPIC_API_KEY`。

**决定**：将 chatbot agent.yaml（dev 文件 + `agents/default/agent.yaml.example`）中的 `api_key_env: ANTHROPIC_API_KEY` 全部改为 `api_key_env: FLEETENT_MODEL_PRIMARY_API_KEY`。平台管理库内 chatbot agent 的 `config_overrides` 如有引用也需同步更新（通过 rematerialize 触发）。

涉及 `.fleetent-dev/` 下的运行时文件须在 task 中明确重建步骤，不由 agent 直接修改 dev 数据（dev 数据不进代码库）。

## Risks / Trade-offs

- **`node.env.example` 模板缺 service key**：`node init-config` scaffold 出来的 `.env` 里 `FLEETENT_NODE_SERVICE_KEY=`（空），首次启动前仍需先跑 `node-provision`。这是预期行为，需在命令输出里提示。

- **端口改动影响现有 dev 实例**：已经跑起来的 `.fleetent-dev/node/.env` 里的 `FLEETENT_NODE_PLATFORM_URL` 指向旧端口（8771/8770），需要 `--force` 重新 provision。这是 dev-only 影响，文档说明即可。

- **`collect_env_var_names` 扩展的 MCP env:/headers: 覆盖范围**：只有 `env` 和 `headers` 两个 dict 中 value 严格以 `"env:"` 开头的才被收集，与 `client.py` 的解析逻辑完全一致。空字符串或纯值不受影响。

## Open Questions

### 硬编码 env var 盲区（结构性，超出本 change）

部分 env var 由工具/特性**硬编码名字直接读取**，从不在 `agent.yaml` 中以 `*_env` 字段或
`env:` 引用形式声明，因此 `collect_env_var_names`（flatten + `*_env` + MCP `env:`/`headers:`）
**结构上无法捕获**：

- `SEARXNG_URL`：`web_search` 工具的 `availability` lambda 与函数体直接 `os.getenv("SEARXNG_URL")`
  （`tools/web_tools.py:126,137`）。这是合法的自托管生产变量（符合内网原则）。
- `FLEETENT_REFLECTION_REAL_SKILL_DRAFT`（`reflection/reflection.py:1820`）及 `FLEETENT_EVAL_*`
  系列：纯 dev / 评估开关，不属于任何部署模板。

**本 change 的处置**：
- `SEARXNG_URL` → 在 `agents/default/.env.example` 加注释，提示"启用 `web_search` 工具时手动
  补 `SEARXNG_URL=`"。不塞进物化器（无声明机制，硬编码会很 hacky）。
- eval / reflection flag → 不进任何 `.env.example`（dev-only）。

**遗留架构问题（不在本 change 解决）**：缺少"工具/特性声明自身所需 env var"的统一机制。
若未来工具的环境依赖增多，应考虑让 `@tool` 注册声明所需 env var 名，由物化器据此补全占位。

## Migration Plan

1. 修改代码（init-config、collect_env_var_names）
2. 更新四个 `.env.example` 文件和 `agent.yaml.example`
3. 更新 Makefile 端口
4. 更新 `docs/operations/local-managed-stack.md` 端口相关说明
5. `dev-bootstrap` 改调 `fleetent` 命令
6. 开发者本地：`make dev-clean && make dev-bootstrap`（或手动 `--force` 重跑各 init-config）重建 dev home

无 DB schema 变更，无 migration。

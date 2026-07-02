## Why

env 文件初始化逻辑散落在 Makefile 中，`dev-bootstrap` 缺少创建平台/node/kb-worker 三个 env 文件的步骤，导致所有服务在初始化后靠 shell 继承环境变量运行而不是靠落地文件；同时所有 `.env.example` 模板与当前实现严重脱节（死变量残留、变量归属错误、端口不一致），新环境无法自助完成初始化。此外 `collect_env_var_names` 漏掉 MCP stdio `env: "env:VAR_NAME"` 模式，导致配置了 stdio 密钥的 agent `.env` 不完整。

## What Changes

- **新增** `fleetent platform init-config --home <path>` 支持 `--home` 参数（当前固定用 `cwd`），使 `dev-bootstrap` 可正确初始化 `.fleetent-dev/.env`
- **新增** `fleetent node init-config` 命令：在 `$FLEETENT_HOME/node/` 下创建 `.env` scaffold（仅含空占位，不含 service key）
- **新增** ``fleetent` `kb-worker` init-config` 命令：在 `$FLEETENT_HOME/kb-worker/` 下创建 `.env` scaffold
- **修改** `make dev-bootstrap`：调用上述三个命令替代现有缺失步骤
- **修复** `collect_env_var_names`：扫描 MCP stdio `env:` dict 中 `"env:VAR_NAME"` 格式的值，提取实际变量名
- **修正** `.env.example`（平台）：删除死变量 `FLEETENT_AUTO_UPGRADE`、`MICROSANDBOX_URL`；区分平台服务端与 TUI 客户端注释区块
- **修正** `agents/default/.env.example`：补充 `FLEETENT_TUI_TOKEN` 说明；删除 `PERMISSION_GATE_*`、`CONTEXT_*`（这些是 agent.yaml 字段，不是 env var）；补充 MCP `env:VAR` 使用说明
- **重命名** chatbot agent（`.fleetent-dev/tenants/default/agents/chatbot/agent.yaml` 及平台 DB 内 `api_key_env`）：`ANTHROPIC_API_KEY` → `FLEETENT_MODEL_PRIMARY_API_KEY`，与 `agents/default/.env.example` 模板命名对齐
- **修正** `kb-worker.env.example`：生产路径改为可读的 dev 友好注释，补充 dev 默认值示例
- **修正** `node.env.example`：补充 `FLEETENT_FORWARDER_HOST_OVERRIDE`（`forwarder_contract.py` 读取）
- **修正** Makefile 端口：`PLATFORM_PORT` 8770 → 8765（对齐 README 和 docs 全局约定，8770 是后来的漂移）；`AGENT_PORT` 8765 → 8766 避免冲突

## Capabilities

### New Capabilities

- `env-init-commands`：三个服务（platform/node/kb-worker）的 env scaffold 初始化命令，可独立调用也可在 `dev-bootstrap` 中调用；命令幂等，已有文件时跳过（除非 `--force`）

### Modified Capabilities

- `platform-cli`：`init-config` 新增 `--home` 参数；`node` 和 `kb-worker` 子命令下各增一个 `init-config` 子命令
- `platform-agent-lifecycle`：`collect_env_var_names` 行为变更——额外收集 MCP stdio `env:` dict 中 `env:` 前缀值所引用的变量名；`.env.example` 作为权威模板随之更新

## Impact

- `src/fleetent/platform/platform_cli/init_config.py`：增加 `--home` 参数
- `src/fleetent/node/`：新增 `init_config.py` 模块；`__main__.py` 或 node CLI 注册入口
- `src/fleetent/knowledge_base/`：新增 worker init-config 命令注册
- `src/fleetent/agent_config.py`：`collect_env_var_names` 扩展
- `Makefile`：`dev-bootstrap` target 改调 fleetent 命令
- `.env.example`、`agents/default/.env.example`、`kb-worker.env.example`、`node.env.example`：内容修正
- `agents/default/agent.yaml.example`：`api_key_env` 统一用 `FLEETENT_MODEL_*` 模板命名
- dev chatbot agent.yaml 及管理库：`ANTHROPIC_API_KEY` → `FLEETENT_MODEL_PRIMARY_API_KEY`（需 rematerialize）
- 无 API breaking change，无数据库 schema 变更，无运行时行为变更（仅 dev-bootstrap 流程和 env scaffold 逻辑）

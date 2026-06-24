## 1. 修复 collect_env_var_names（MCP env: 引用）

- [ ] 1.1 测试：`collect_env_var_names` 对含 `env: {"DB_URL": "env:MY_DATABASE_URL"}` 的 MCP server 返回 `MY_DATABASE_URL`（红）
- [ ] 1.2 实现：在 `agent_config.py` 的 `collect_env_var_names` 中额外扫描 MCP server `env` dict，提取 `"env:"` 前缀值的变量名，合并去重
- [ ] 1.3 测试通过（绿）；运行 `uv run pytest tests/unit -q` 确认无新增失败

## 2. platform init-config 支持 --home

- [ ] 2.1 测试：`apply_init_config(root=Path("/tmp/x"))` 在指定路径创建 `.env`（红）
- [ ] 2.2 实现：`init_config.py` 的 `plan_init_config` / `apply_init_config` 接受 `root` 参数（已有），`handle()` 改为从 `--home` 参数或 `paths.base_dir()` 获取 root，删除 `Path.cwd()` 回退
- [ ] 2.3 测试通过（绿）

## 3. fleetent node init-config 命令

- [ ] 3.1 测试：`fleetent node init-config` 在 `FLEETENT_HOME/node/.env` 不存在时创建文件（红）
- [ ] 3.2 实现：`src/fleetent/node/init_config.py` 新建，逻辑参考 `platform/platform_cli/init_config.py`；源模板为仓库根 `node.env.example`；在 `node` CLI 入口（`__main__.py` 或 `main.py`）注册 `init-config` 子命令
- [ ] 3.3 测试：已存在时跳过，`--force` 时覆盖（绿）

## 4. fleetent kb-worker init-config 命令

- [ ] 4.1 测试：`fleetent kb-worker init-config` 在 `FLEETENT_HOME/kb-worker/.env` 不存在时创建文件（红）
- [ ] 4.2 实现：`src/fleetent/knowledge_base/worker_init_config.py` 新建；源模板为仓库根 `kb-worker.env.example`；在 kb-worker CLI 入口注册 `init-config` 子命令
- [ ] 4.3 测试：幂等行为（绿）

## 5. 更新四个 .env.example 文件

- [ ] 5.1 `.env.example`（平台）：删除 `FLEETENT_AUTO_UPGRADE`、`MICROSANDBOX_URL`；加注释区分"平台服务端"与"TUI 客户端"两区块；确认 `FLEETENT_FORWARDER_HOST_OVERRIDE` 不在此文件（node 级变量）
- [ ] 5.2 `agents/default/.env.example`（agent）：补充 `FLEETENT_TUI_TOKEN=`（注明自动生成）；删除 `PERMISSION_GATE_*`、`CONTEXT_*`；补充 MCP `env:VAR` 使用说明注释
- [ ] 5.3 `kb-worker.env.example`：将生产路径（`/var/lib/fleetent/`）改为 dev 友好注释，提供 dev 默认值示例（`sqlite:///$(FLEETENT_HOME)/management.db`）；补充 `FLEETENT_HOME` 须由进程环境提供的说明
- [ ] 5.4 `node.env.example`：补充 `FLEETENT_FORWARDER_HOST_OVERRIDE=`；`FLEETENT_NODE_PLATFORM_URL` 端口保持 8765（文档约定）

## 6. agent.yaml.example 与 chatbot 重命名

- [ ] 6.1 `agents/default/agent.yaml.example`：确认所有 `api_key_env` 使用 `FLEETENT_MODEL_*` 模板命名（非 `ANTHROPIC_API_KEY`）
- [ ] 6.2 `.fleetent-dev/tenants/default/agents/chatbot/agent.yaml`：`api_key_env: ANTHROPIC_API_KEY` → `api_key_env: FLEETENT_MODEL_PRIMARY_API_KEY`（两处 model target 均改）
- [ ] 6.3 确认平台管理库中 chatbot agent 的 `model_overrides`/`config_overrides` 无残留 `ANTHROPIC_API_KEY` 引用（如有，通过 platform admin API 更新）

## 7. Makefile 端口对齐与 dev-bootstrap 改造

- [ ] 7.1 Makefile：`PLATFORM_PORT` 8770 → 8765；`AGENT_PORT` 8765 → 8766
- [ ] 7.2 Makefile `dev-bootstrap`：在 `seed-builtin-admin` 后增加三行调用：`fleetent platform init-config --home $(FLEETENT_HOME)`、`fleetent node init-config`（使用 `FLEETENT_HOME`）、`fleetent kb-worker init-config`（使用 `FLEETENT_HOME`）
- [ ] 7.3 更新 `docs/operations/local-managed-stack.md`：将 8770/8771 的端口说明统一更新为 8765；`NODE_PLATFORM_URL` 默认值更新

## 8. 集成验证

- [ ] 8.1 运行 `make test-pr`，无新增失败
- [ ] 8.2 运行 `uv run pytest tests/integration -q`，确认无新增失败
- [ ] 8.3 手动验证：`make dev-clean && make dev-bootstrap`，确认 `.fleetent-dev/.env`、`.fleetent-dev/node/.env`（模板内容）、`.fleetent-dev/kb-worker/.env` 均存在且结构正确
- [ ] 8.4 验证 `fleetent node init-config --force` 不清空已有 service key（service key 不在模板里，`--force` 用模板覆盖，符合预期；在输出提示中说明）

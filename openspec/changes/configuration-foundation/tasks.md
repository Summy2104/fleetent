## 0. 前置确认

- [ ] 0.1 确认本 change 不做热加载、Admin UI、配置中心或 DB-backed dynamic config
- [ ] 0.2 确认 `.env` 只保留 secrets / environment overrides，且优先级高于 YAML
- [ ] 0.3 确认 cron jobs 和 webhook sources 不进入 `settings.yaml`
- [ ] 0.4 确认不保留 `config/mcp.yaml`、`config/cron.yaml`、`config/webhooks.yaml` 兼容读取

## 1. Settings YAML loader

- [ ] 1.1 Write failing tests: `Settings()` 从 `config/settings.yaml` 读取非敏感配置
- [ ] 1.2 Write failing tests: 环境变量覆盖 YAML 值
- [ ] 1.3 Write failing tests: `config/settings.yaml` 缺失时使用 typed defaults
- [ ] 1.4 实现 settings YAML loader
- [ ] 1.5 运行 `uv run pytest tests/unit -x -q`

## 2. MCP settings migration

- [ ] 2.1 Write failing tests: server startup 从 `settings.mcp.servers` 注册 MCP
- [ ] 2.2 Write failing tests: 存在旧 `config/mcp.yaml` 时 fail fast，不 fallback
- [ ] 2.3 实现 `mcp.servers` settings model 和 startup 集成
- [ ] 2.4 运行 `uv run pytest tests/integration -x -q`

## 3. Cron scheduler configuration cleanup

- [ ] 3.1 Write failing tests: scheduler 不再读取 `config/cron.yaml`
- [ ] 3.2 Write failing tests: 存在旧 `config/cron.yaml` 时 fail fast
- [ ] 3.3 Write failing tests: scheduler 从 settings 读取 enabled/default timezone 等全局参数
- [ ] 3.4 实现 cron YAML loader 删除和 settings 集成
- [ ] 3.5 运行 `uv run pytest tests/integration -x -q`

## 4. Webhook configuration cleanup

- [ ] 4.1 Write failing tests: server 不再读取 `config/webhooks.yaml`
- [ ] 4.2 Write failing tests: 存在旧 `config/webhooks.yaml` 时 fail fast
- [ ] 4.3 Write failing tests: webhook 全局 enabled / max_body_bytes 从 settings 读取
- [ ] 4.4 实现 webhook legacy YAML 删除和 settings 集成
- [ ] 4.5 运行 `uv run pytest tests/integration -x -q`

## 5. Examples and docs

- [ ] 5.1 更新 `config/settings.yaml.example`
- [ ] 5.2 删除旧 `config/mcp.yaml.example`、`config/cron.example.yaml`、`config/webhooks.example.yaml`
- [ ] 5.3 更新 `docs/architecture.md`、`docs/capabilities/deployment.md`、`docs/capabilities/mcp.md`、`docs/capabilities/scheduling.md`
- [ ] 5.4 运行 `uv run pytest -x -q`
- [ ] 5.5 运行 `uv run ruff format src tests`
- [ ] 5.6 运行 `uv run ruff check src tests`
- [ ] 5.7 运行 `uv run mypy src`
- [ ] 5.8 运行 `openspec validate configuration-foundation`

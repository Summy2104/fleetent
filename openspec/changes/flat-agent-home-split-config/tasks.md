## 1. paths.agent_file() 扁平化

- [x] 1.1 Write failing test：`tests/unit/test_paths.py` —— `agent_file() == base_dir()/"agent.yaml"`（设 `FLEETENT_HOME`，指向 `$FLEETENT_HOME/agent.yaml`，非 config/）
- [x] 1.2 Implement：`paths.agent_file()` 改为 `base_dir()/"agent.yaml"`

## 2. 模板重排（config/agent/ + config/platform/）

- [x] 2.1 Write failing test：`tests/integration/test_deployment_docs.py` —— 断言存在 `config/agent/agent.yaml.example`、`config/agent/.env.example`、`config/platform/.env.example`；不存在 `config/agent.yaml.example`、根 `.env.example`；更新「env.example 覆盖 agent.yaml.example 的 *_env」一致性测试指向 `config/agent/`
- [x] 2.2 Implement：`git mv config/agent.yaml.example config/agent/agent.yaml.example`（并改头注释为扁平 home 根）；新建 `config/agent/.env.example`（agent env，D3）+ `config/platform/.env.example`（platform env，D3）；`git rm .env.example`

## 3. install.sh 扁平 seed

- [x] 3.1 Write failing tests：`tests/integration/test_install_script.py` —— fresh 后 `$FLEETENT_HOME/agent.yaml` + `.env` 存在、**无 `$FLEETENT_HOME/config/`**；agent.yaml 来自 `config/agent/agent.yaml.example`；存在即跳过；`--skip-config` 不 seed
- [x] 3.2 Implement：`copy_config_templates` seed `$FLEETENT_HOME/{agent.yaml,.env}`（源 `config/agent/agent.yaml.example`、`config/agent/.env.example`），不建 config/

## 4. init_config + Dockerfile + .gitignore

- [x] 4.1 Write failing/更新 tests：`test_admin_init_config.py`（.env 模板源 `config/platform/.env.example`）；`test_deployment_docs.py` 的 Dockerfile COPY 断言更新
- [x] 4.2 Implement：`init_config.py` 的 `.env.example` 源 → `config/platform/.env.example`；`Dockerfile` COPY → 新模板路径；`.gitignore` 忽略 `config/agent/agent.yaml`、`config/**/.env`、`config/platform/*.yaml`，保留 `*.example`

## 5. 下游测试与一次性 home agent 路径

- [x] 5.1 更新 `tests/unit/test_agent_config.py`（加载 `config/agent/agent.yaml.example`）、`tests/integration/test_run_sync_home_agent.py`（home agent 扁平 `FLEETENT_HOME/agent.yaml`）等引用旧路径的测试
- [x] 5.2 Implement/调整使其转绿（运行时已由 task 1 改 `agent_file()`）

## 6. 收尾

- [x] 6.1 全量 `ANTHROPIC_API_KEY=sk-test-dummy uv run pytest -x -q` 通过；`uv run ruff format && uv run ruff check src tests`；`uv run mypy src` 不新增；`bash -n scripts/install.sh`；手动 smoke：隔离 HOME 跑 install.sh → 校验扁平 `agent.yaml` 被 `fleetent` 读到
- [ ] 6.2 README/CLAUDE agent 部署段：部署 home 扁平（`agent.yaml` 在根）、模板新位置、旧 `config/agent.yaml` 迁移说明

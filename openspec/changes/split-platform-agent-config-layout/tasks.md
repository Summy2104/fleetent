## 1. 配置布局 contract

- [ ] 1.1 Write failing tests: 仓库 canonical 模板只包括 Platform / Agent 两类；不存在旧 `config/agent.yaml.example`，tracked `config/agent.yaml` 不作为 canonical 模板；`config/agents/*` 不被部署文档当成 canonical 模板。
- [ ] 1.2 Implement: 重组/迁移模板路径，删除或移动 confusing tracked 本地配置与 examples。
- [ ] 1.3 Verify green: 跑配置模板/部署文档相关测试。

## 2. Platform / Agent env 边界

- [ ] 2.1 Write failing tests: Platform ENV 模板含平台进程变量（如 `FLEETENT_SECRET_KEY`），Agent ENV 模板不含平台进程变量；Agent `.env` 由 materialize / init 生成 required env。
- [ ] 2.2 Implement: 更新模板、install/init/materialize 注释与源路径。
- [ ] 2.3 Verify green: 跑 env 模板解析与 materialize env 测试。

## 3. Knowledge 默认内嵌平台

- [ ] 3.1 Write failing tests: 默认部署不要求 `config/knowledge.yaml.example` 作为独立模板；Platform config 可表达 embedded knowledge；独立 knowledge service 模板只作为 future/optional 示例。
- [ ] 3.2 Implement: 调整 knowledge 配置模板与文档，避免默认部署强制独立 `knowledge.yaml`。
- [ ] 3.3 Verify green: 跑 knowledge service config 与 docs 测试。

## 4. Agent home materialize 目标

- [ ] 4.1 Write failing tests: Platform materialize 写入 `agents/<agent-id>/{agent.yaml,.env,data/}`；Agent runtime 从该 home 自包含启动；Platform home 根不再被当成 Agent home。
- [ ] 4.2 Implement: 更新 materialize/install/runtime path contract 与相关文档。
- [ ] 4.3 Verify green: 跑 agent lifecycle、install bootstrap、agent runtime CLI 测试。

## 5. 文档与 OpenSpec 收敛

- [ ] 5.1 Write failing tests/checks: README、deployment docs、active specs 不再引用旧 `config/agent.yaml.example` / `config/agent.yaml` 作为部署主路径。
- [ ] 5.2 Implement: 更新 README、docs、`openspec/specs/configuration`、`install-bootstrap`、`platform-agent-lifecycle`、`knowledge-service-config`。
- [ ] 5.3 Verify green: `openspec validate --specs --strict`。

## 6. Quality gates

- [ ] 6.1 Run `uv run pytest -x -q`
- [ ] 6.2 Run `uv run ruff format src tests`
- [ ] 6.3 Run `uv run ruff check src tests`
- [ ] 6.4 Run `uv run mypy src`
- [ ] 6.5 Run `uv run python scripts/check_test_layers.py`
- [ ] 6.6 Run `PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py`

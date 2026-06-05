## 1. Agent config schema

- [ ] 1.1 Write failing tests: `tests/unit/test_agent_config.py` 或新文件覆盖 `models.targets` / `models.routes` 解析，包含 provider/protocol 必填、duplicate target、route missing target、`api_key_env` inline secret 拒绝、删除 `model_overrides` 后旧字段不再被接受
- [ ] 1.2 Implement: 在 `AgentFile` 引入 `models` dataclass/schema，删除 `model_overrides` 字段和旧示例，使测试转绿
- [ ] 1.3 Verify green: 运行 `uv run pytest tests/unit/test_agent_config.py -x -q`

## 2. Model resolver

- [ ] 2.1 Write failing tests: 新增 `tests/unit/test_model_resolver.py`，覆盖 target+route 合并、route params 覆盖 target params、fallback 顺序、missing env、认证/配置错误不 fallback、可切换错误 fallback、`ModelPolicySnapshot` 不携带明文 key 且可按 `agent_id + route_key` 解析
- [ ] 2.2 Implement: 在 `fleetent.model` 提供 Agent-scoped resolver、`ModelPolicySnapshot` 与 resolved config 类型，支持 `openai_chat` / `openai_image_generation` / `http_embedding` / `http_rerank` 的协议分派边界，使测试转绿
- [ ] 2.3 Verify green: 运行 `uv run pytest tests/unit/test_model_resolver.py -x -q`

## 3. Runtime wiring

- [ ] 3.1 Write failing tests: 覆盖 `runtime/snapshot.py` 携带 `models`，`runtime/loop.py` 的 default/memory_extraction/vision 路由从 Agent snapshot resolver 获取，不再依赖 `config/routes.yaml`
- [ ] 3.2 Implement: 更新 `AgentSnapshot`、loop 调用点和 OpenAI-compatible client 创建路径，使测试转绿
- [ ] 3.3 Verify green: 运行相关 runtime/model 单元测试 `uv run pytest tests/unit -x -q`

## 4. Image / embedding / rerank integration

- [ ] 4.1 Write failing tests: 覆盖 `generate_image` 从 `models.routes.image_generation` 解析 provider，embedding/rerank 从 `models.routes.embedding` / `models.routes.rerank` 解析 provider；服务化消费方通过 `ModelPolicySnapshot` 按 `agent_id + route_key` 解析，而不是从 AgentFile legacy flat fields 或全局 provider route 独立读取生产路由
- [ ] 4.2 Implement: 将 `tools/image_gen_client.py`、intelligence embedding/rerank runtime 接入 Agent-scoped resolver / `ModelPolicySnapshot`，保留测试注入边界，使测试转绿
- [ ] 4.3 Verify green: 运行相关 unit/integration 测试

## 5. Platform materialize and templates

- [ ] 5.1 Write failing tests: 覆盖 platform DB/authored Agent materialize 生成完整 `models`，`.env` scaffold 写入 `api_key_env` 且保留已有值，模板不再输出 `ANTHROPIC_API_KEY` / `model_overrides`
- [ ] 5.2 Implement: 更新 `platform/agent_lifecycle/materialize.py`、admin deploy/export、`fleetent agent init` scaffold、`config/agent/agent.yaml.example` 与 local `config/agent.yaml`，使测试转绿
- [ ] 5.3 Verify green: 运行相关 platform/runtime integration 测试

## 6. Remove old runtime config path

- [ ] 6.1 Write failing tests: 覆盖 `config/routes.yaml` 不再作为 runtime 主路径，旧 `DEFAULT_ROUTES` 不再提供生产 fallback；旧 `model_overrides` 配置启动失败
- [ ] 6.2 Implement: 删除或降级旧 router/routes.yaml 主路径与相关示例/文档引用，使测试转绿
- [ ] 6.3 Verify green: 运行 `uv run pytest -x -q`

## 7. Quality gates

- [ ] 7.1 运行 `uv run ruff format src tests`
- [ ] 7.2 运行 `uv run ruff check src tests`
- [ ] 7.3 运行 `uv run mypy src`
- [ ] 7.4 运行 `uv run python scripts/check_test_layers.py`
- [ ] 7.5 运行 `PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py`

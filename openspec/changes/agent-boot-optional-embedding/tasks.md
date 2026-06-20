## 1. configure 缺路由回落(TDD)

- [ ] 1.1 写测试(红):`tests/unit/` 下,构造一个**命名** `AgentFile`,其 `models` 不含 `embedding` 路由 → 调 `vector_store.runtime._configure(agent)`(或 `configure_from_active_agent` + monkeypatch active agent)→ 断言**不抛错**且 `_embedding` 为 `DeterministicEmbeddingProvider`。最窄命令 `uv run pytest tests/unit/<file>::<test> -x -q` 见红。
- [ ] 1.2 实现(绿):`_configure` 中,命名 agent 分支先判 `"embedding" not in ModelPolicySnapshot.from_agent(agent).routes`(或等价的路由成员检查)→ 是则 `DeterministicEmbeddingProvider()` + WARN 日志;否则 `create_embedding_provider_from_policy(...)`。同命令见绿。
- [ ] 1.3 写测试(红→绿):断言回落时记了一条 WARN(用日志捕获)。

## 2. 显式路由 + 误配路由(回归保护)

- [ ] 2.1 写测试(红→绿):命名 agent **显式配** `http_embedding` + endpoint 的 `embedding` 路由 → `_embedding` 为 `HttpEmbeddingProvider`、不回落、不告警。
- [ ] 2.2 写测试(红→绿):命名 agent `embedding` 路由存在但**协议非 http_embedding / 缺 endpoint** → 仍抛 `ModelConfigError`(不被回落吞掉)。

## 3. 边界与文档

- [ ] 3.1 跑 `PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py` 确认 `vector_store` 无新增跨包 import、未 import `platform`。
- [ ] 3.2 文档:`vector-store` 行为说明同步「缺 embedding 路由 deterministic 回落」;managed agent 模型配置相关文档补一句「embedding 路由可选,缺则 deterministic 回落,生产应显式配置」。
- [ ] 3.3 收尾门禁:`make test-pr` + `make test-unit-ci`(覆盖率门禁)+ `uv run pytest tests/integration -q`(对照 main 基线无新增失败)。

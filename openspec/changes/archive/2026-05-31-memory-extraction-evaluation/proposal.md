## Why

`memory-update-merge-actions` 已让 memory extraction 支持 `create` / `update` / `delete` /
`ignore`，但这只保证 action contract 可执行，并不能说明模型提取质量是否稳定。memory 一旦误记、
漏记或把一次性请求写成长期偏好，会直接污染 long-term-ctx 注入结果。

本 change 建立 memory extraction 的评估基线：默认使用 deterministic/mock LLM evaluation
验证 fixture 与 action contract；同时预留真实 LLM 手动评估入口，用于后续调整 prompt 或切换模型时
评估真实提取质量。真实 LLM evaluation 不进入默认 PR gate。

## What Changes

- 新增 `tests/evaluation/` 下的 memory extraction evaluation。
- 定义可读的 evaluation fixture 格式，至少包含：
  - `name`
  - `initial_memories`
  - `conversation`
  - `mock_actions`
  - `expected_memories`
  - `forbidden_memories`
- 覆盖第一批 memory extraction 场景：
  - identity create
  - identity update
  - context update + TTL refresh
  - preferences create
  - one-off preference request ignore
  - explicit forget / delete
  - noisy or invalid conversation ignore
- 默认 evaluation 使用 mock LLM，保证稳定、快速、可在 `make test-evaluation` 下运行。
- 新增真实 LLM 手动入口，通过显式环境变量启用，例如：
  - `FLEETENT_EVAL_REAL_LLM=1 uv run pytest tests/evaluation/test_memory_extraction_eval.py`
- 真实 LLM evaluation 默认 skip；即使显式启用，缺少 provider API key 时也 skip，不进入 Bitbucket PR/main gate。

## Dependencies

- 依赖 `memory-update-merge-actions` 完成后执行；否则 update / delete memory state expectations 无运行时基础。
- 依赖已完成的测试分层：evaluation tests 必须放在 `tests/evaluation/`。

## Module Boundary Impact

- **owning package**：无运行时代码 owning package；本 change 属于 memory-layer evaluation test ownership。
- **public API surface**：不新增或修改 public API。
- **owned tables**：无新增表；测试使用 `memory_items` 并通过 tmp SQLite 隔离。
- **config namespace**：无新增生产配置；真实 LLM evaluation 使用测试环境变量显式开启。
- **cross-module dependencies**：测试通过 `memory_layer.extract_and_update()`、`memory_layer.search()`、
  mock `model_router` 和 `vector_store` 验证行为。
- **migration / shim plan**：无迁移；不恢复旧 JSONL memory 兼容。

## Impact

- **代码**：不修改运行时代码，除非 evaluation 暴露 `memory-update-merge-actions` 的 contract bug。
- **测试**：新增 evaluation fixture 与 pytest runner，替换当前 evaluation placeholder。
- **CI**：不改变 PR/main Bitbucket gate；evaluation 仍为手动或显式命令。
- **数据**：不使用真实用户数据，不触碰 `data/`。
- **不包含**：
  - 不接真实 embedding provider。
  - 不评估 long-term-ctx 回答质量。
  - 不做 reflection 自动修复。
  - 不把真实 LLM evaluation 加入默认 CI。

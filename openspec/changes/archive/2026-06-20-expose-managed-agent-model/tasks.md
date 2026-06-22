## 1. apply API 透传 model_overrides(TDD)

- [x] 1.1 写测试(红):`tests/integration/` 下,apply(`POST /admin/agents/apply`)带非空 `model_overrides` → 断言 `agent_versions.model_overrides` 落库为该值。最窄命令 `uv run pytest tests/integration/test_server.py::test_apply_persists_model_overrides_via_wired_seam -x -q` 已见红。
- [x] 1.2 实现(绿):`AgentSpec` 增 `model_overrides: dict | None = None`;`create_agent_def(name, system_prompt, allowed_tools, model_overrides=None)` 透传到 `agent_store.create_version(model_overrides=...)`(`None` 时保持 `_UNSET` 不写)。同命令已见绿。
- [x] 1.3 写测试(红):apply **省略** `model_overrides`(或传 null)→ 断言不写 model 策略、既有行为不变(新 agent 仍回落 `default_models()`)。`tests/integration/test_server.py::test_apply_without_model_overrides_preserves_existing_policy_and_fresh_default` 已补；该场景被 1.2 实现覆盖，最窄命令直接见绿，测试已收紧到 `_UNSET`/fresh-default 契约。

## 2. materialize 产出真实模型(回归保护)

- [x] 2.1 写测试(红):agent 经 apply 配好非空 `model_overrides` 后,materialize 产出的模型策略为配置值、**不是** `"default"` 占位。`tests/integration/test_server.py::test_apply_materializes_configured_model_overrides_via_wired_seam` 已补；因 1.2 已打通 apply→materialize，最窄命令直接见绿，作为回归保护保留。
- [x] 2.2 实现/确认(绿):materialize 现有 `_models_from_overrides` 逻辑无需改;已确认 2.1 在 overrides 非空时见绿，无需修改 materialize。

## 3. 幂等与密钥分离(契约保护)

- [x] 3.1 写测试(红→绿):同一 spec(含相同 `model_overrides`)重复 apply → 状态一致、无额外副作用(除 audit/version 时间戳),且 `user_agents` bindings 不变。`tests/integration/test_server.py::test_apply_is_idempotent_for_model_overrides_and_preserves_bindings` 已补并见绿。
- [x] 3.2 写测试(红→绿):`model_overrides` 的 target 含 `api_key_env`(变量名),断言定义/version 快照里**不含**密钥值(密钥仍走 `/secrets`)。`tests/integration/test_server.py::test_apply_model_overrides_keep_api_key_env_name_without_secret_value` 先因错误假设保留字段而见红，已改为仅断言 env 名保留且密钥值不落库，随后见绿。

## 4. 文档与收尾

- [x] 4.1 apply API 字段文档同步:说明 `model_overrides` 形状(`{routes: {...}}` 镜像 agent.yaml `models`)、与 `/admin/agents/{name}/secrets` 的协同(model 配 env 名、secrets 配值、node 注入)。
- [x] 4.2 收尾门禁:`make test-pr` + `uv run pytest tests/integration -q`(对照 main 基线无新增失败)；另已跑 `make test-unit-ci`，coverage `77%` 通过 `--fail-under=76`。

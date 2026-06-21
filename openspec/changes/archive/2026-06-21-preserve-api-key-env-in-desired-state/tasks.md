> TDD 硬门禁:先写测试见红 → 改实现见绿。最窄命令 `uv run pytest <file>::<test> -x -q`。测试任务先于实现。

## 1. 锁定行为(测试先行,见红)

- [x] 1.1 写测试:含 `api_key_env` 的 agent 经 `desired_state_payload_from_agent_file` 后,model target **仍保留** `api_key_env` 字段。当前应见红(被剥)。
- [x] 1.2 写测试:配置中承载密钥值的 `env` 字典(`key == "env"`)与 `credential_ref` **仍被剥除**,载荷不含明文密钥值。锁住主权契约,防修复过头。
- [x] 1.3 写集成测试:`materialize_from_store` 产出的 `agent.yaml` 含 `api_key_env`;当对应 provider 配了 inline key 时,`.env` 含该值(验证"指针 + 值"闭合)。当前应见红(agent.yaml 缺指针 / 该路径断)。

## 2. 修复(实现,见绿)

- [x] 2.1 改 `agent_lifecycle/materialize.py` 的 `_strip_secret_plumbing`:删除 `key.endswith("_env")` 分支,保留 `key == "env"` 与 `key.endswith("credential_ref")`。运行 1.1/1.2/1.3 全见绿。

## 3. Change 收尾验证

- [x] 3.1 `make test-pr` 全绿(对照 main 基线无新增失败)。
- [x] 3.2 `uv run pytest tests/integration -q -k "materialize or desired_state or node"`(对照 main 基线)无新增失败。
- [x] 3.3 `PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py` 通过;确认未碰 agent 运行时、未碰 server.py、无 agent→platform 反向依赖。

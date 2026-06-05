## 1. 删除前确认无运行时回读

- [x] 1.1 grep 全库确认阶段 2 后无 runtime 模块仍读待删 `Settings` 字段(治理/部署/智能层/IM tokens/
      `default_agent_name`/`agent_budget_global_*`);产出确认清单(对照阶段 2 task 7.3)
      → 确认:仅 D4.1 列出的 fallback 分支(`Settings()`/`s.` 无-agent 回退)+ `server.py` health
      adapters + `agent_store._get_default_agent_name` + `set-default-agent` CLI 仍读待删字段;所有
      `agent.`/`governance.` 读取均来自 agent.yaml dataclass(正确保留)。fallback 分支由 task 2.2 前置重指。

## 2. 删除 Settings agent-runtime 字段

- [x] 2.1 Write failing tests: 断言 `Settings` 不再含治理字段(`agent_max_turns`/`context_*`/
      `agent_budget_*` 含 global/`session_*`/`permission_gate_*`/`tool_default_timeout_seconds`/
      `provider_failure_threshold` 等)与部署字段(`microsandbox_url`/`image_gen_*`/`vision_*`/
      `disabled_skills`)及智能层字段(`vector_store`/`embedding`/`rerank`/`long_term_ctx`/
      `knowledge_base`/`mcp`/`scheduling`/`webhooks`)。运行见红(字段尚存)
      → `test_settings_excludes_dissolved_agent_runtime_fields`
- [x] 2.2 从 `Settings` 删除上述字段;**保留**子模型类于 `config.py` 供 `AgentFile` 复用。运行见绿
      → 含前置 fallback 重指;~16 测试文件从 `Settings(...)` 迁到 `AgentFile`;intelligence/diagnostics
      源读取改 `active_agent_or_default()`/`_kb_config`/`_ltc_config`。config_validation 仍读旧字段
      (mypy 4 err + 4 测试失败)→ 留待 task 5 retarget。

## 3. 删除 IM tokens、default_agent_name、anthropic_api_key

- [x] 3.1 Write failing tests: 断言 `Settings` 无 `slack_bot_token`/`slack_app_token`/
      `telegram_bot_token`/`default_agent_name`/`anthropic_api_key`;`YAML_SECRET_FIELDS` 清空;
      平台 stores 可 `Settings()` 无需传 key。运行见红
- [x] 3.2 删除这些字段;`YAML_SECRET_FIELDS` 置空(`SecretRejecting` 源作空集安全网保留);
      平台 stores 的 `Settings(anthropic_api_key="")` 改为 `Settings()`。运行见绿
      → `_get_default_agent_name` 读 `agent_config.current().default`;server `/health` adapters 改
      per-agent connectors(slack)+ owner connector(telegram);owner IM tokens 经 `connector_config`
      从 env 读取(脱离 Settings)。config_validation 仍 task 5。

## 4. set-default-agent CLI 作用于 agent.yaml

- [x] 4.1 Write failing tests: `set-default-agent --agent-name X` 写目标 agent.yaml `bindings.default: true`
      并清除原 default;`--clear` 移除该 flag;不写 `settings.yaml`。运行见红
- [x] 4.2 改 admin CLI `set-default-agent` 实现作用于 agent.yaml(遍历 agents_dir,set/clear
      bindings.default;未知 agent 报错);删 `_SETTINGS_YAML`。运行见绿

## 5. config_validation retarget 到 agent.yaml

- [ ] 5.1 Write failing tests(integration): `validate-config` 校验 agent.yaml 治理/部署/智能层字段与
      inline-secret;env 注入的 token 不报 inline secret;平台 DB 可达仍可校验。运行见红
- [ ] 5.2 retarget `platform/config_validation.py`:加载 agent.yaml 校验,inline-secret 扫描复用阶段 1
      同源逻辑;平台 prerequisite 仍读精简 `Settings`。运行见绿

## 6. settings.yaml.example 收缩 + 文档

- [ ] 6.1 收缩 `config/settings.yaml.example` 为平台精简集(`database_url`/`log_format`/`observability`);
      在迁移说明中列出 agent-runtime 字段 → `agent.yaml` 的迁移路径

## 7. 收尾

- [ ] 7.1 `uv run ruff format src tests && uv run ruff check src tests` + `uv run mypy src` 通过
- [ ] 7.2 全量 `uv run pytest -x -q` 与 `uv run python scripts/check_test_layers.py` 通过

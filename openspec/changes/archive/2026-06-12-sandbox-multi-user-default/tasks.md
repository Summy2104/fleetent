## 1. 翻转 multi_user 默认为 fail-safe

- [x] 1.1 更新既有 unit 测试(red):把 `sandbox-scope-split-followups` 中断言 `SandboxSettings.multi_user` 默认 `False` 的用例改为断言默认 `True`;断言显式 `multi_user: false` 仍可解析(opt-out)
- [x] 1.2 实现(green):`agent_config.SandboxSettings.multi_user` 默认 `True`;更新该字段 docstring(fail-safe 默认 + 单用户 opt-out 语义)
- [x] 1.3 更新既有 integration 测试(red→green):`sandbox-scope-split-followups` 中"未声明 multi_user → agent 保留"的用例改为"未声明(默认 true)→ agent 纠正为 session + 告警";新增/改"显式 multi_user: false → agent 保留"
- [x] 1.4 新增 unit(red→green):`init_sandbox_manager` 在 agent.yaml 未声明 multi_user 时以 `multi_user=True` 构造 manager(默认 fail-safe 端到端)

## 2. 文档与收尾

- [x] 2.1 `agents/default/agent.yaml.example` 注释:`sandbox.multi_user` 默认 `true`(fail-safe,每用户隔离),单用户跨会话复用须显式 `false`
- [x] 2.2 `PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py` EXIT 0(agent_config 无 import platform)+ check_test_layers + ruff(仅改动文件)+ `mypy src` 无新增
- [x] 2.3 `make test-pr` 无新增失败 + sandbox 相关 integration 无回归(重点:workspace-scope / multi_user / containment 用例按新默认全绿)
- [x] 2.4 `openspec validate sandbox-multi-user-default --strict` 通过

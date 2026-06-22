## 1. registry: _manifest 维护 + refresh_if_changed

- [x] 1.1 写测试(unit, tmp_path)：`scan()`/`reload()` 后模块级 `_manifest` 被填充为 user 根下 `{SKILL.md 相对路径: (mtime_ns, size)}`，与索引同源 —— 见红
- [x] 1.2 实现：registry 新增 `_manifest`，在 `scan()` 与 `reload()` 成功后填充(覆盖 user 根 SKILL.md) —— 见绿
- [x] 1.3 写测试(unit, tmp_path)：`refresh_if_changed` —— 无变化返回 False 且不重扫；新增/编辑(改 mtime/size)/删除 SKILL.md 返回 True 且 `_index` 反映变化；`skills_dir=None` 且从未 scan → False；不读文件内容(只 stat，可用「篡改正文但不改 mtime/size 不触发」反证或 mock os.stat 验证) —— 见红
- [x] 1.4 实现：`refresh_if_changed(skills_dir=None) -> bool`(walk+stat 拼 manifest，比对 `_manifest`，变了调 `reload()` 并更新基线)，加模块级锁保护临界区 —— 见绿

## 2. config: skill_hot_reload 开关

- [x] 2.1 写测试(unit)：`AgentFile` 默认 `skill_hot_reload=True`，可被 agent.yaml 设 false —— 见红
- [x] 2.2 实现：`agent_config.AgentFile` 增 `skill_hot_reload: bool = True` —— 见绿

## 3. 接线：每条入站消息 catalog 注入前检测一次(受开关门控)

- [x] 3.1 写测试(unit)：IM 路径 `normalizer` 在 `available_skills_prompt` 前，agent `skill_hot_reload=True` 时调用 `refresh_if_changed`、`False` 时不调用 —— 见红
- [x] 3.2 实现：`im_gateway/normalizer` 在注入 catalog 前，按 `agent.skill_hot_reload` 调 `refresh_if_changed`(skills_dir 取 `_last_skills_dir`) —— 见绿
- [x] 3.3 写测试(unit)：HTTP 流式 `run_stream` 在 catalog 注入前，按 `skill_hot_reload` 调/不调 `refresh_if_changed` —— 见红
- [x] 3.4 实现：`runtime/loop.run_stream` 增 `skill_hot_reload: bool = True` 形参并在 catalog 注入前据此调 `refresh_if_changed`；`agent_app` chat 入口从 `agent.skill_hot_reload` 透传 —— 见绿
- [x] 3.5 写测试(unit)：CLI 一次性路径(`run_sync`)行为不变(仍每次 `scan_skills`，不重复引入检测) —— 见红（若已绿说明无回归，补一条覆盖断言）→ 见绿

## 4. 集成、隔离校验与收尾

- [x] 4.1 写/跑集成测试(integration, tmp_path)：模拟运行中 agent —— scan 一次 → 外部改/增/删 SKILL.md → `refresh_if_changed` 触发 reload → 索引/`available_skills_prompt` 反映新集合；关闭开关时不变 —— 见红→见绿
- [x] 4.2 跑模块边界护栏 `scripts/check_module_boundaries.py` + `test_module_dependency_guardrails.py`：确认 `skills/`、`runtime/`、`im_gateway/` 无新增 `import fleetent.platform.*`
- [x] 4.3 收尾门禁：`make test-pr` 全绿 + `uv run pytest tests/integration -q`(对照 main 基线无新增失败) + `uv run ruff check`(改动文件干净)

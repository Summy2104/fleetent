## 1. 配置：AgentFile.skill_user_access

- [x] 1.1 写测试(unit)：`AgentFile` 默认 `skill_user_access == {}`；可从 agent.yaml 设 `{skill: [user_ids]}` —— 见红
- [x] 1.2 实现：`agent_config.AgentFile` 增 `skill_user_access: dict[str, list[str]] = {}` —— 见绿

## 2. registry：可见性判定(含 DM-only)

- [x] 2.1 写测试(unit)：`skill_visible_to_user(name, user_id, chat_type, access_map)`——公开 skill 任何人/任何 chat_type True；受限 skill 仅 dm+在白名单 True；频道(非 dm)恒 False；dm 但不在白名单 False —— 见红
- [x] 2.2 实现 `registry.skill_visible_to_user` —— 见绿

## 3. catalog 按用户过滤

- [x] 3.1 写测试(unit)：`available_skills_prompt(..., user_id=, chat_type=, skill_user_access=)`——受限 skill 对非授权/频道不渲染、对授权 dm 渲染、公开 skill 不受影响、空 map/无入参时字节级同旧 —— 见红
- [x] 3.2 实现：`available_skills_prompt` 增可选 user_id/chat_type/skill_user_access，渲染前过 `skill_visible_to_user` —— 见绿

## 4. read_skill / read_skill_file 按用户拦截(中性提示)

- [x] 4.1 写测试(unit)：`read_skill` 对受限 skill——非授权用户/频道返回**与"无此 skill"逐字一致**的中性错误且不返回内容；授权 dm 正常返回；`read_skill_file` 同此判定。access_map+chat_type 经 tool_context —— 见红
- [x] 4.2 实现：`read_skill`/`read_skill_file` 加前置可见性判定(取 `tool_context.principal.user_id` + `session_context.chat_type` + access_map)，不可见返回中性"无此 skill" —— 见绿

## 5. 沙箱 per-session 过滤视图

- [x] 5.1 写测试(unit, tmp_path)：`registry.build_session_skill_view(scope_key, allowed_names, skills_dir=)`——在 `<root>/.views/<scope_key>/` 为 allowed_names 硬链接 skill 目录、只含允许项、幂等可重建；返回视图路径 —— 见红
- [x] 5.2 实现 `registry.build_session_skill_view`(复用 .views 硬链接模式 + 清理 helper) —— 见绿
- [x] 5.3 写测试(unit)：sandbox manager `_resolve_skill_mount` 在拿到"允许 skill 名集合/视图路径"时 host_src 指向该会话视图；空 access(允许全部)时等价整根；挂载点/ro/SKILLS_DIR 不变 —— 见红
- [x] 5.4 实现：`manager._resolve_skill_mount` 接受 runtime 传入的 allowed-names/视图,host_src 改为视图路径(沙箱不解析授权) —— 见绿

## 6. 接线(透传 user_id/chat_type/access_map + 允许集到沙箱)

- [x] 6.1 写测试(unit)：`im_gateway/normalizer` 在 catalog 注入处把 `msg.user_id`+`session_context.chat_type`+`agent.skill_user_access` 传入 `available_skills_prompt`；并把 access_map 注入 tool_context —— 见红
- [x] 6.2 实现：normalizer + `runtime/loop.run_stream` 透传 user_id/chat_type/skill_user_access 到 catalog 与 tool_context；CLI 一次性路径按需(单用户)处理 —— 见绿
- [x] 6.3 写测试(unit)：runtime 计算"该会话允许 skill 名集合"(对每个 skill 过 `skill_visible_to_user`)并交给沙箱挂载;skill reload/allowlist 变更触发视图重建 —— 见红
- [x] 6.4 实现：runtime 在取沙箱前算 allowed-names→驱动 `build_session_skill_view` + manager 挂载;接热加载/变更重建钩子 —— 见绿

## 7. 集成、隔离校验与收尾

- [x] 7.1 写/跑集成测试(integration, tmp_path)：端到端——受限 skill 对授权 dm 用户:catalog 含、read_skill 可读、视图含;对非授权用户:catalog 无、read_skill 中性拒、视图不含;频道:对所有人均无/拒/不含;公开 skill 各场景不受影响;空配置等价旧行为 —— 见红→见绿
- [x] 7.2 跑模块边界护栏 `scripts/check_module_boundaries.py` + `test_module_dependency_guardrails.py`：确认无新增 platform import；确认 sandbox 不为授权 import agent_config(授权计算在 skills/runtime)
- [x] 7.3 收尾门禁：`make test-pr` 全绿 + `uv run pytest tests/integration -q`(对照 main 基线无新增失败) + `ruff check` 改动文件干净 + 新字段 `skill_user_access` 同步到 `agents/default/agent.yaml.example`

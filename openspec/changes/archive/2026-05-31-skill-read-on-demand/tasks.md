> 本 change 原为 `agent-skill-binding`,review 中推翻重做为 openclaw read-on-demand。以下为重做后**实际完成**的任务。

## 1. 可用 Skill 清单产出

- [x] 1.1 Write failing tests for `skill_registry.available_skills_prompt()`:渲染已启用 Skill 为含 name/description/location 的 `<available_skills>` 清单;`disabled_skills` 命中与 `enabled_by_default: false` 的 Skill 排除;空索引返回空串。看到红
- [x] 1.2 Implement:`available_skills_prompt(disabled_skills=None)` 渲染清单 + `## Skills` mandatory 扫描指令,复用 `_resolve_disabled_skills`/`_disabled_reason` 判定;无可用 Skill 返回空串。看到绿

## 2. read_skill 工具

- [x] 2.1 Write failing tests:`read_skill(name)` 返回该 Skill 完整 SKILL.md;未注册名返回明确错误文本(不抛)。看到红
- [x] 2.2 Implement:`tools.read_skill(name)` `@tool`,`name in skill_registry._index` 则 `load(name)`、否则返回 `error: no skill named ...`。看到绿

## 3. 注入链改清单 + 移除关键词注入

- [x] 3.1 Write failing tests:`_assemble_prompt` 把 base_system + 清单作 messages[0] 稳定前缀、memory 作其后独立 system 消息;两次仅 memory 不同→前缀字节相同;无清单无 memory→单条 base system。看到红
- [x] 3.2 Implement:`_assemble_prompt(base_system, skills_catalog, memory_ctx, user_msg)`;`run_sync`/`run_stream` 经它注入 `available_skills_prompt()`;删 `_matched_skill_content`、`match_skill`/`load_skill` 注入链、`run`/`run_sync`/`run_stream` 的 `allowed_skills`/`blocked_skills` 参数。看到绿
- [x] 3.3 `im_gateway/normalizer` 改注入清单,system 消息按 base+catalog(稳定)→memory(变量)排序(顺带修复其原有前缀缓存杀手)。

## 4. 移除 per-agent DB 绑定(回退跨域改动)

- [x] 4.1 删 `agent_policy.check_skill_access`。
- [x] 4.2 回退 `agent_store`:删 `Agent` 的 `allowed_skills`/`blocked_skills`、`_dump_opt`/`_load_opt`、`create_agent` 参数、`_SELECT_COLS`/`_row_to_agent` 相关、`_ensure_skill_columns`、CREATE 列。
- [x] 4.3 删 alembic 迁移 `002_add_agent_skill_columns.py`;修 `test_agent_store` / `test_migrations`。

## 5. 收尾

- [x] 5.1 删旧模型测试 `test_skill_policy.py`、`test_agent_loop_skill_binding.py`;改 `test_agent_loop` 的 prompt-cache 用例为清单模型。
- [x] 5.2 全量 `ANTHROPIC_API_KEY=... uv run pytest` 通过(721 passed);ruff 零新增(仅既有 baseline);mypy 71=71 零新增。
- [x] 5.3 守卫:清单进稳定前缀(memory 变化前缀不变);read_skill 找不到返回错误文本;禁用 Skill 不入清单。

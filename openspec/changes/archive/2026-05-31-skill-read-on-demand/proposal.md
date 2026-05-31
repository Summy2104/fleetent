## Why

> 注:本 change 原名 `agent-skill-binding`(per-agent Skill 白名单,基于 DB 列)。wave-1 review 期间(2026-05-31)经 zy 决策**推翻重做**为 openclaw 式 read-on-demand 模型并更名。本文件描述的是**实际实现**。

`agent_loop` 原先的 Skill 注入是「关键词匹配 + 命中灌全文」:`scan()` 后 `match_skill(user_input)` 取第一个命中的 Skill,`load_skill()` 把**整篇 SKILL.md** 拼到 system prompt。两个硬伤:

- **未命中即 AI 完全不知有哪些 Skill**:关键词漏召时 AI 看不到 Skill 列表、无从主动援引。
- **命中即灌全文**:整篇 SKILL.md 长期占 context,且每条消息变着注入,**打爆 prompt 前缀缓存**。

原 `agent-skill-binding` 想给 Skill 加 per-agent DB 白名单(类比 `allowed_tools`)。但 review 中认定:**Skill 不是授权边界,tool 才是**——Skill 只是指令文档,模型读了也越不过 `allowed_tools` + 审批那道真正的墙。给 Skill 做 DB 表 + 硬 allowlist 是把低风险指令当高风险能力治理,过度设计。

故改为 openclaw 式 **read-on-demand**:框架注入可用 Skill 的**清单**(让 AI 感知),模型按需用工具读全文。

## What Changes

- 新增 `skill_registry.available_skills_prompt()`:产出已启用 Skill 的 `<available_skills>` 清单(每项 name/description/location)+ `## Skills` mandatory 扫描指令;被禁用(`disabled_skills` 或 `enabled_by_default: false`)的 Skill 排除;无可用 Skill 时返回空串。
- 新增 `read_skill(name)` 内置工具(risk_level=low):按名返回完整 SKILL.md;未注册返回明确错误文本。
- `agent_loop._assemble_prompt` 把清单注入 system prompt 的**稳定前缀区**(base_system + catalog 作 messages[0],随 Skill 集变化、对消息稳定→可缓存);可变 memory 作其后独立 system 消息。`run_sync` / `run_stream` 改走它。
- **移除**关键词自动匹配 + 全文自动注入:删 `match_skill`/`load_skill` 注入链、`_matched_skill_content`、`agent_policy.check_skill_access`。
- `im_gateway/normalizer` 同样注入清单,system 消息按 base+catalog(稳定)→memory(变量)排序(顺带修复其原有 prompt-cache 缓存杀手)。
- **不做** per-agent DB 白名单:回退 `agent_store` 的 `allowed_skills`/`blocked_skills` 列、迁移 002、`Agent` 字段。per-agent 收窄由 admin 在 agent 的 `system_prompt` prose 圈定;首版清单=全部已启用 Skill。

## Capabilities

### New Capabilities
- `skill-read-on-demand`: Skill 以 read-on-demand 方式提供——框架始终把已启用 Skill 的「名称+描述+位置」清单注入 system prompt 稳定前缀让 AI 感知;AI 按需调 `read_skill` 工具加载命中 Skill 的完整 SKILL.md;无关键词自动匹配、无全文自动注入。Skill 非授权边界(真正边界是 `allowed_tools`),故无 per-agent 硬白名单。

### Modified Capabilities
<!-- Skill 注入此前无既有 spec 承载;注入机制由「关键词匹配+全文注入」改为「清单+按需读」收口在本新 capability 内描述。 -->

## Impact

- **代码**:`skill_registry.py`(+`available_skills_prompt`)、`tools.py`(+`read_skill`)、`agent_loop.py`(`_assemble_prompt` 注入清单、删关键词链与 skill 参数)、`agent_policy.py`(删 `check_skill_access`)、`im_gateway/normalizer.py`(注入清单 + 缓存友好排序)、`agent_store.py`(回退 skill 列/字段/`_ensure_skill_columns`)、删迁移 `002_add_agent_skill_columns.py`。
- **测试**:`available_skills_prompt`(清单含 name/desc/location、禁用排除、空索引空串)、`read_skill`(找到/未找到)、`_assemble_prompt`(清单进稳定前缀、memory 在后)、删 `test_skill_policy.py` / `test_agent_loop_skill_binding.py`(旧模型)。
- **不影响**:`allowed_tools` / `check_tool_access`(工具授权不变);SK2 frontmatter 解析、`load()` / `list_skills()` 契约;不引入新依赖。
- **Non-Goals**:per-agent 结构化清单收窄(留后续,取决于 agent 定义 DB-vs-配置);热加载 / 注入审计 / 多 Skill 共存 / 禁用机制(各自后续 change,需按 read-on-demand 重规划)。

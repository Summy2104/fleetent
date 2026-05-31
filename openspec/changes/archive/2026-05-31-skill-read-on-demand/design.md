## Context

> 原 `agent-skill-binding`(per-agent DB 白名单)在 wave-1 review 被推翻重做为本设计。下文为**实际实现**的设计记录。

原 Skill 注入:`run_sync`/`run_stream` 调 `match_skill(user_input)` 取首个命中 Skill,`load_skill()` 把全文拼进 system prompt;`run()` 收预构建 messages、自身不注入。问题:未命中则 AI 不知有哪些 Skill;命中则灌全文、且逐消息变着注入打爆前缀缓存。

参考 openclaw(`/opt/gopath/src/github.com/openclaw/openclaw`):agent 配置声明可用 Skill,框架注入 `<available_skills>` 清单(name/description/location),模型经 `read` 工具按需读全文。

约束(CLAUDE.md):禁止 AI 框架;禁止全局可变状态;新模块结构;mypy strict;行长 100;TDD;测试隔离(skills 目录 tmp_path、LLM mock)。

## Goals / Non-Goals

**Goals:**
- 框架始终注入已启用 Skill 清单(name/description/location)+ mandatory 扫描指令,让 AI 感知。
- 提供 `read_skill(name)` 工具,模型按需加载全文。
- 清单进 system prompt 稳定前缀,对自动前缀缓存友好。
- 移除关键词自动匹配 + 全文自动注入。

**Non-Goals:**
- 不做 per-agent 硬白名单 / DB 绑定(Skill 非授权边界,见 D1)。
- 不做 per-agent 结构化清单收窄(留后续,见 D5)。
- 不做热加载 / 注入审计 / 多 Skill 共存 / 禁用机制特性(各自后续 change,需按 read-on-demand 重规划)。
- 不引入新依赖。

## Decisions

### D1:Skill 不是授权边界,不做 DB 绑定
真正的授权边界是 `allowed_tools` 白名单 + 风险审批门——它们卡住「模型能做什么」。Skill 只是指令文档,模型读了某 SKILL.md 也越不过 `allowed_tools`。故给 Skill 做 DB 表 + 硬 allowlist 是把低风险指令当高风险能力治理,过度设计。
**决定**:回退原 `agent_store` 的 `allowed_skills`/`blocked_skills` 列、`Agent` 字段、`_ensure_skill_columns`、迁移 002;删 `agent_policy.check_skill_access`。
**Alternatives**:①保留 DB 白名单——被否(过度设计 + 跨 governance 域纠葛);②skill 在 SKILL.md 声明哪些 agent 可用——被否(控制反转,治理上看不全 agent 权限面)。

### D2:read-on-demand —— 清单 + read_skill 工具
`skill_registry.available_skills_prompt()` 产出 `<available_skills>` 清单(每项 name/description/location)+ `## Skills` mandatory 指令;`tools.read_skill(name)` 按名返回全文、未注册返回错误文本。模型自行从清单选择并按需读。
**为何**:省 token(清单 vs 全文)、模型自主选更准、可多 Skill、与 tool 中心架构一致(skill 变成「模型用工具读的东西」)。
**Alternatives**:保留关键词匹配自动灌全文——被否(漏召则 AI 不知有此 Skill;命中灌全文费 context + 打爆缓存)。

### D3:清单进稳定可缓存前缀
`_assemble_prompt` 把 base_system + 清单作 `messages[0]`(稳定前缀,仅随 Skill 集变化);可变 memory 作其后独立 system 消息。清单非空才拼。
**为何**:清单对逐条请求稳定,放前缀让自动前缀缓存命中;memory 逐请求变,后置不破坏前缀字节。normalizer(IM 路径)同样按 base+catalog(稳定)→memory(变量)排序——顺带修复其原有「memory 在 system 最前」的缓存杀手。

### D4:移除关键词匹配与全文自动注入
删 `match_skill`/`load_skill` 注入链、`_matched_skill_content`;`run`/`run_sync`/`run_stream` 不再做关键词注入,仅经 `_assemble_prompt` 注入清单。`run()` 仍收预构建 messages、不注入。`read_skill` 用 `skill_registry.load(name)`;`match()`/`load()` 函数本身保留。

### D5:per-agent 作用域 = system_prompt prose(结构化收窄留后续)
首版清单 = 全部已启用 Skill(减 `Settings.disabled_skills`)。per-agent 用哪些由 admin 在 agent 的 `system_prompt` 文字圈定(模型按需读,prose 圈定有效)。结构化的「逐 agent 收窄清单」留后续,取决于 governance 域(张亮)对「agent 定义 DB-vs-配置」的决策——agent 现为 SQLite 行。
**为何**:Skill 非授权边界(D1),prose 圈定足够;结构化字段的存储归属是 governance 域决策,不在本 change 单方面定。

## Risks / Trade-offs

- [依赖模型可靠地「扫清单→调 read_skill」] → 用 mandatory `## Skills` 指令引导;on-prem 小模型若不稳,关键词匹配可作后续「提示/兜底」再加回(不进本版)。
- [首版清单=全部已启用 Skill,多 agent 场景所有 agent 都看到全部 Skill] → Skill 非授权边界,可接受;结构化收窄留后续(D5)。
- [read_skill 不 gate 禁用] → 与已批准的「load() 不受禁用约束」一致;清单只列启用项,模型只会读到启用项。

## Open Questions

- per-agent 结构化清单收窄:取决于张亮「agent 定义 DB-vs-配置」决策,待定。
- 是否需要关键词匹配作为「提示」兜底以适配弱模型:留观察,后续按需。

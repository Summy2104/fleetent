# skill-reflection-proposals

## Why

reflection foundation 已能识别 `skill_opportunity` finding，但当前不会形成可管理、可审批、可追踪的 Skill 变更建议。
随着 agent 被真实试用，重复任务、失败模式、无效 Skill 和可沉淀流程都需要进入受控 proposal lifecycle，而不是让
LLM 直接写 `skills/` 文件。

本 change 让 reflection 生成 pending Skill proposals。proposal 可以建议创建、更新或废弃 Skill，但不会自动应用。

## What Changes

- 新增 `skill_proposals` 表，归 reflection owns。
- 新增 public API：生成、查询、approve / reject、apply skill proposals。
- proposal 类型：
  - `create_skill`
  - `update_skill`
  - `deprecate_skill`
- 每条 proposal 必须包含 reason、evidence、suggested draft 或 suggested diff。
- apply 需要人工确认，且通过 skill public API / management boundary 执行。
- 默认 deterministic/fake signals 测试；真实 LLM draft generation 显式 opt-in。

## Out Of Scope

- 不自动创建、修改或删除 `skills/` 文件。
- 不让 LLM 无约束生成任意文件。
- 不做 Skill UI；skill management 只消费 proposal。
- 不定义 askit promote / drift 回流语义。
- 不默认调用真实 LLM。

## Module Boundary Impact

- owning package：`fleetent.intelligence.reflection`。
- public API surface：`SkillProposal`、`generate_skill_proposals()`、`approve_skill_proposal()`、
  `reject_skill_proposal()`、`apply_skill_proposal()`。
- owned tables：`skill_proposals`。
- config namespace：无新增必需配置；真实 LLM draft smoke 使用显式 env guard。
- cross-module dependencies：只读依赖 observability 和 skill public APIs；apply 阶段调用 skill management / skill registry public boundary。
- migration / shim plan：新增 Alembic migration；不改现有 skill scan/injection 行为。

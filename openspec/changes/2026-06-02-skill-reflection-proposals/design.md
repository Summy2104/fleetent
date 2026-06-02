# Design

## Proposal Lifecycle

Skill reflection proposals 是 reflection-owned pending suggestions：

```text
pending -> approved -> applied
pending -> rejected
approved -> rejected
```

只有 approved proposal 可以 apply。apply 仍需显式 actor，并走 skill public API 或 skill management boundary。
第一版可以先实现 create/update/deprecate 的 proposal 持久化和 guard，真正文件写入能力若 skill management
边界尚未具备，可以返回 `ready_for_manual_apply` 或调用 mockable adapter。

## Proposal Types

- `create_skill`：重复任务、稳定步骤、现有 skill 未覆盖。
- `update_skill`：现有 skill 经常触发但失败、缺少安全约束、步骤过期。
- `deprecate_skill`：长期不触发、和其他 skill 重复、或持续导致负面结果。

每条 proposal 包含：

- `id`
- `type`
- `target_skill_name`
- `status`
- `reason`
- `evidence_refs`
- `suggested_draft`
- `suggested_diff`
- `risk_level`
- `created_at`
- `reviewed_by`
- `reviewed_at`
- `applied_at`

## Input Signals

只读信号：

- observability traces：repeated tasks、tool usage、failures、permission rejection、final outcome；
- skill registry：skill hit / injection records、existing skill metadata、last used；
- reflection reports：`skill_opportunity` findings。

不直接扫描用户隐私 transcript 写入 proposal；evidence 保存 ids、短摘要和脱敏 metadata。

## Draft Generation

默认 deterministic generator 只输出结构化 suggested draft/diff skeleton，确保测试稳定。

真实 LLM draft generation 必须显式开启，例如 `FLEETENT_SKILL_PROPOSAL_REAL_LLM=1`，并且输出必须经过
schema validation、path/name validation 和安全审计。真实 LLM 失败时不自动 fallback 到写文件。

## Apply Boundary

apply 行为：

- `create_skill`：创建新 skill draft 或交给 skill management create API。
- `update_skill`：应用 suggested diff 或交给 skill management update API。
- `deprecate_skill`：标记 archived / disabled，不物理删除。

如果 skill management API 不可用，apply 应 fail fast 或返回明确 unsupported，不得绕过边界直接写 arbitrary file。

## Evaluation

默认 evaluation 使用 fake traces 和 fake skill registry：

- 重复任务生成 create proposal；
- 失败 skill 生成 update proposal；
- 长期未使用 skill 生成 deprecate proposal；
- 普通单次任务不生成 proposal；
- persisted proposal 不包含完整 transcript。

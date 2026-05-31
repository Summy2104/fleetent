## ADDED Requirements

### Requirement: Skill 内容注入前的安全审计

skill_registry SHALL 在把任一 Skill 纳入可注入集合之前，对其 SKILL.md **正文以及会被 L1 注入的 description 字段**运行一组已知 prompt 注入模式检测规则。审计范围 MUST 覆盖所有会被注入链拼入 system prompt 的字段（L2 正文 + L1 注入的 description），使藏在 description 中的注入串同样能被检出。每条规则 MUST 关联一个严重度（`suspicious` 或 `severe`），且 MUST 来自单一的静态规则表。审计 MUST 为纯静态匹配，不调用任何 LLM 或外部服务。

#### Scenario: 干净 Skill 通过审计
- **WHEN** 某 SKILL.md 正文不命中任何注入模式规则
- **THEN** 该 Skill 正常纳入可注入集合，可被匹配与注入，不产生审计告警

#### Scenario: 审计返回命中清单
- **WHEN** 某 SKILL.md 正文命中一条或多条注入模式规则
- **THEN** 审计产出包含每条命中规则标识与其严重度的结果

### Requirement: 命中严重模式拒绝加载

当某 Skill 的正文或 description 命中任一 `severe` 严重度的注入模式时，skill_registry MUST 拒绝把该 Skill 纳入可注入集合。该 Skill 的条目 MUST 保留在 `_index` 中并被打上 `audit_blocked` 标志（等价 `injectable=False`，处置方案为标志位，而非从 `_index` 删除）；`match` / `match_all` / `l1_summary`（L1 清单）等所有进入注入链的读取面 MUST 跳过被标记项。被拒 Skill 的 **name/description（L1 注入面）与正文（L2 注入面）MUST NOT 被拼入任何请求的 system prompt**，并 MUST 记录一条包含该 Skill 路径与命中规则的审计日志。`load` MUST 忽略 `audit_blocked` 标志、按名仍返回该 Skill 原文：审计只约束自动匹配注入路径，不改变 `load` 按名显式加载的契约（`load` 是审计与禁用共同的安全出口，取到的内容不会经注入链进入 system prompt）。

> 跨 change 约定（见 design D5）：因 L1 注入面（name + description）由 SK1 引入而 SK1 排在本 change 之后，SK1 落地 L1 时 MUST 一并兑现「L1 清单排除 `audit_blocked` Skill」与「audit 覆盖 description 字段」，否则 severe Skill 的 description 仍会经 L1 绕过审计注入。

#### Scenario: severe 命中的 Skill 正文永不被注入
- **WHEN** 某 SKILL.md 正文命中一条 `severe` 注入模式规则，且用户输入本可关键词命中该 Skill
- **THEN** 该 Skill 的正文（L2）不被注入 system prompt，其 `_index` 条目被标记 `audit_blocked`，并记录一条说明其因严重注入模式被拒绝加载的审计日志

#### Scenario: severe Skill 不出现在 L1 清单
- **WHEN** 某 Skill 因正文或 description 命中 `severe` 模式被标记 `audit_blocked`，系统构建 L1 清单（`l1_summary`，含 name + description）
- **THEN** 该 Skill 的 name 与 description 不出现在 L1 清单中、不经 L1 注入面进入 system prompt（L1 排除与 L2 排除同时生效）

#### Scenario: description 命中 severe 同样被拒
- **WHEN** 某 Skill 正文干净但其 description 字段命中一条 `severe` 注入模式规则
- **THEN** 该 Skill 被标记 `audit_blocked`，其 name/description（L1）与正文（L2）均不被注入，并记录审计日志

#### Scenario: severe 被拒的 Skill 仍可显式 load 取原文
- **WHEN** 某 Skill 因命中 `severe` 模式被标记 `audit_blocked`，调用方按名调用 `load`
- **THEN** `load` 忽略该标志，仍返回该 Skill 的完整原文供人工排查，`load` 契约不受审计影响（与 SK6 禁用机制对 `load` 的口径一致）

### Requirement: 命中可疑模式记录并告警

当某 Skill 的正文仅命中 `suspicious` 严重度的注入模式（无 `severe` 命中）时，skill_registry SHALL 仍将其纳入可注入集合，但 MUST 记录一条包含该 Skill 路径与命中规则的审计日志，并在启动扫描时输出控制台告警。

#### Scenario: suspicious 命中仍可注入但记录告警
- **WHEN** 某 SKILL.md 正文仅命中 `suspicious` 模式，且用户输入命中其关键词
- **THEN** 该 Skill 仍被注入，并记录一条审计日志、在启动扫描时产生控制台告警

#### Scenario: 审计命中写入可观察的审计轨迹
- **WHEN** 任一 Skill 命中注入模式（无论 suspicious 或 severe）
- **THEN** 审计轨迹中包含该 Skill 路径、命中规则标识、严重度与处置（拒绝/放行），便于事后排查

# skill-injection-audit Specification

## Purpose
TBD - created by archiving change skill-injection-audit. Update Purpose after archive.
## Requirements
### Requirement: Skill 内容的静态注入审计

skill_registry SHALL 在把任一 Skill 纳入索引的可用面之前,对其 SKILL.md **正文以及 description 字段**运行一组已知 prompt 注入模式检测规则。审计范围 MUST 覆盖会经 read-on-demand 两个面到达模型的内容:清单面注入的 description(`available_skills_prompt`)与全文面返回的正文(`read_skill`)。每条规则 MUST 关联一个严重度(`suspicious` 或 `severe`),且 MUST 来自单一静态规则表。审计 MUST 为纯静态匹配,不调用任何 LLM 或外部服务。

#### Scenario: 干净 Skill 通过审计
- **WHEN** 某 SKILL.md 正文与 description 不命中任何注入模式规则
- **THEN** 该 Skill 正常进入清单且可被 `read_skill` 读取,不产生审计告警

#### Scenario: 审计返回命中清单
- **WHEN** 某 SKILL.md 正文或 description 命中一条或多条注入模式规则
- **THEN** 审计产出包含每条命中规则标识与其严重度的结果

### Requirement: 命中严重模式拒绝经注入面到达模型

当某 Skill 的正文或 description 命中任一 `severe` 注入模式时,skill_registry MUST 拒绝让该 Skill 经任何自动注入面到达模型。该 Skill 条目 MUST 保留在 `_index` 中并被打上 `audit_blocked` 标志(而非删除)。`available_skills_prompt`(清单)MUST 跳过被标记项;`read_skill` MUST 对被标记项返回明确的拒绝文本而非其正文。被拒 Skill 的 **name/description(清单面)与正文(read_skill 面)MUST NOT 到达任何请求的 system prompt 或工具结果**,并 MUST 记录一条含该 Skill 路径与命中规则的审计日志。`load()` MUST 忽略 `audit_blocked`、按名仍返回原文(`load` 是人工排查的安全出口,其内容不经清单/`read_skill` 自动到达模型)。

#### Scenario: severe Skill 不出现在清单
- **WHEN** 某 Skill 因正文或 description 命中 `severe` 被标记 `audit_blocked`,系统构建可用 Skill 清单
- **THEN** 该 Skill 的 name 与 description 不出现在清单中

#### Scenario: read_skill 拒绝返回 severe Skill 全文
- **WHEN** 对一个被标记 `audit_blocked` 的 Skill 名调用 `read_skill`
- **THEN** 返回说明该 Skill 因安全审计被拒的明确文本,不返回其 SKILL.md 正文,并记录审计日志

#### Scenario: description 命中 severe 同样被拒
- **WHEN** 某 Skill 正文干净但其 description 命中一条 `severe` 注入模式规则
- **THEN** 该 Skill 被标记 `audit_blocked`,其清单面与全文面均不可达,记录审计日志

#### Scenario: severe 被拒的 Skill 仍可显式 load 取原文
- **WHEN** 某 Skill 因命中 `severe` 被标记 `audit_blocked`,调用方按名调用 `load()`
- **THEN** `load()` 忽略该标志,仍返回完整原文供人工排查,契约不受审计影响

### Requirement: 管理台上传与编辑路径必须执行真实注入审计

管理 API 的上传（`POST /admin/skills`）与编辑（`PUT /admin/skills/{name}`）路径 SHALL 在持久化前对 skill 内容执行与 scan 路径相同的静态注入检测。`engine_audit(content)` seam SHALL 调用 `skill_audit.audit(content)` 返回真实审计结果，不得返回固定的 `{"verdict": "pass", "rules": []}`。

- `severe` 判决 SHALL 阻止 skill 进入 `active` 状态（置为 `quarantined`）
- `suspicious` 判决 SHALL 记录并允许上传，等待人工 force-publish 确认
- `pass` 判决 SHALL 正常发布

#### Scenario: 上传含注入模式的 Skill 被拒绝
- **WHEN** 通过管理 API 上传一个正文命中 `severe` 注入模式的 Skill
- **THEN** `engine_audit()` 返回 `{"verdict": "rejected", "rules": [...]}`
- **AND** 该 Skill 状态被置为 `quarantined`，不进入 active 可用集合

#### Scenario: 上传干净 Skill 正常发布
- **WHEN** 通过管理 API 上传一个正文不命中任何注入模式的 Skill
- **THEN** `engine_audit()` 返回 `{"verdict": "pass", "rules": []}`
- **AND** 该 Skill 状态为 `active`，重扫后可被 agent 使用

#### Scenario: engine_audit 调用真实审计函数
- **WHEN** 管理 API 调用 `engine_audit(content)`
- **THEN** 实际执行 `skill_audit.audit(content)` 的静态规则扫描，不返回固定 pass

### Requirement: 命中可疑模式记录并告警

当某 Skill 仅命中 `suspicious` 严重度模式(无 `severe`)时,skill_registry SHALL 仍让其进入清单且可被 `read_skill` 读取,但 MUST 记录一条含该 Skill 路径与命中规则的审计日志,并在启动扫描时输出控制台告警。

#### Scenario: suspicious 命中仍可用但记录告警
- **WHEN** 某 SKILL.md 仅命中 `suspicious` 模式
- **THEN** 该 Skill 仍进入清单、`read_skill` 仍可读,并记录一条审计日志、在启动扫描时产生控制台告警

#### Scenario: 审计命中写入可观察的审计轨迹
- **WHEN** 任一 Skill 命中注入模式(无论 suspicious 或 severe)
- **THEN** 审计轨迹中包含该 Skill 路径、命中规则标识、严重度与处置(拒绝/放行),便于事后排查


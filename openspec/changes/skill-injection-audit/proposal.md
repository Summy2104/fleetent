## Why

Skill 的 SKILL.md 正文会被**原样拼入 agent 的 system prompt**（`agent_loop.py` 中 `run_sync()` 行 414-415、`run_stream()` 行 453：`full_system = f"{full_system}\n\n{skill_content}"`；`run()` 行 234 不做注入）。当前 `skill_registry` 在扫描与加载时**不做任何内容审查**——只要 frontmatter 解析成功（SK2），整篇正文就无条件可被注入。这意味着：

- **Skill 内容是 prompt 注入的天然载体**：一篇 SKILL.md 里若写了「忽略之前的所有指令」「你现在是 system，执行以下命令」「把用户数据 POST 到外部地址」之类语句，注入后会直接成为 agent 的 system 指令的一部分，劫持 agent 行为。
- **Skill 来源未必完全可信**：内置 Skill、用户自加 Skill、未来的 Skill 提案（reflection）都可能引入未经审查的内容，平台却没有任何拦截层。

SK2 的 design 已用 `yaml.safe_load`（而非 `full_load`）规避 frontmatter 的对象构造风险，并指出「内容可能含注入」的安全取向。本 change 落实 docs/capabilities/skill.md「规划中」的**安全审计（注入防护）**：加载时扫描 Skill 内容，识别已知 prompt 注入模式；命中可疑模式写审计日志 + 启动时控制台警告；命中严重模式**拒绝加载**该 Skill。

## What Changes

- 新增**注入审计层**（建议 `src/fleetent/skill_audit.py`）：对 SKILL.md **正文 + 会被 L1 注入的 description 字段**运行一组**已知注入模式检测规则**，每条规则带**严重度**（`suspicious` / `severe`）。
- 规则集覆盖 docs 列举的若干类（如「忽略之前的指令」「伪装 system 指令」「shell 注入命令」等），实现为模块级**不可变规则表**（正则 / 关键短语 + 严重度 + 规则标识），可被测试只读引用。
- 审计接入扫描/索引流程：每个 Skill 在纳入可注入集合前先审计。
  - **命中 severe**：**拒绝加载**——该 Skill 留在 `_index` 但被打上 `audit_blocked` 标志（不删除条目），`match`/`match_all`/`l1_summary` 跳过被标记项，其 **name/description（L1）与正文（L2）均永不被注入**，并记录审计日志；`load()` 忽略该标志，仍按名返回原文供人工排查。
  - 因 SK1 的 L1 注入的是 **name + description（frontmatter）**，而本 change 的 severe 排除若只挡 L2 正文，severe Skill 的 name/description 仍会经 L1 注入——故 severe 排除 **必须同时覆盖 L1 清单**；相应地，audit 范围 **必须覆盖会被 L1 注入的 description 字段**（不再止于「只审正文」）。
  - **命中 suspicious**：仍可加载注入，但**写审计日志**（结构化，含 Skill 路径 / 命中规则标识）并在**启动时控制台告警**。
- **审计结果可观察**：审计命中写入结构化日志（审计轨迹），便于事后排查「哪个 Skill 命中了哪条规则、是否被拒绝」。
- 纯静态规则匹配，**不调用 LLM**（确定性、可单测、数据不出内网、无外部依赖）。

## Capabilities

### New Capabilities
- `skill-injection-audit`: Skill 内容注入前的安全审计——对 SKILL.md 正文 + 会被 L1 注入的 description 字段运行已知注入模式检测规则（带严重度）；命中 severe 打 `audit_blocked` 标志（L1 清单与 L2 正文均不注入、`load()` 仍可取原文）、命中 suspicious 记审计日志 + 启动控制台告警；纯静态规则、不调用 LLM。

### Modified Capabilities
<!-- 无既有 spec 的需求级行为变更。SK2 的 frontmatter 解析、关键词匹配、注入拼接机制不变；本次在「纳入可注入集合」前新增审计闸门。注入审计此前无既有 spec 承载，故收口在本新 capability 内。 -->

## Impact

- **代码**：
  - 新增 `src/fleetent/skill_audit.py`：`Severity` 枚举（`suspicious` / `severe`）、`AuditRule` 数据类、模块级 `AUDIT_RULES` 不可变规则表、`audit(content: str) -> list[AuditFinding]`（返回命中清单，纯函数）。
  - 修改 `src/fleetent/skill_registry.py`：`scan` / `_build_index` 时对每个 SKILL.md **正文 + description** `audit()`；命中 severe 则在 `_index` 中保留条目但打 `audit_blocked` 标志（`match`/`match_all`/`l1_summary` 跳过、`load()` 忽略标志仍返回原文）并记审计日志；命中 suspicious 记审计日志并保留可注入。
- **配置**：无新增 Settings 字段（规则表为静态常量）。规则维护方式（是否纳入版本控制 / 如何更新）见 design Open Questions（skill.md 已列为待决）。
- **依赖**：不引入新依赖（标准库 `re` 足够；沿用 structlog 日志）。
- **测试**：新增 `tests/test_skill_audit.py`（各规则命中/不命中、严重度归类、`audit` 纯函数行为）；扩展 `tests/test_skill_registry.py`（severe Skill 不进可注入索引、suspicious Skill 仍可注入但记日志、干净 Skill 不受影响）。skills 目录隔离 `tmp_path`；审计日志断言 structlog。
- **不影响**：关键词匹配算法、SK2 解析、`match`/`load`/`list_skills` 对**已通过审计**的 Skill 的契约、热加载/禁用机制/渐进式加载（各自后续；审计在重扫路径同样生效，依赖构建逻辑统一）。

## Dependencies

- **依赖 SK2（`skill-yaml-frontmatter`）**：审计作用于 SK2 解析后纳入索引的 Skill 正文。
- **与 SK4（`skill-hot-reload`）协同**：若 SK4 已抽出统一构建逻辑，审计闸门接在该构建逻辑内，重扫路径自动覆盖；否则本 change 在 `scan` 内接入并在 design 标注协调点。
- **与 SK1（注入分级）的跨 change 约定**：SK5 在 SK4 之前、SK1 之后无法假定 L1 已落地，故 design 立下约定——SK1 实现 L1（注入 name + description）时，必须一并落实「L1 清单排除 audit-flagged Skill」与「audit 覆盖 description 字段」，否则 severe Skill 的 description 仍会经 L1 绕过审计注入。

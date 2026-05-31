## Context

Skill 注入是「把 SKILL.md 正文原样拼进 system prompt」（`agent_loop.py` 中 `run_sync()` 行 414-415、`run_stream()` 行 453；`run()` 行 234 不做注入）。`skill_registry.scan()`（行 31-56）只校验 frontmatter 能否解析（SK2），对**正文内容**零审查。由于 system prompt 是 agent 行为的最高优先指令源，一篇含注入语句的 SKILL.md 注入后即可劫持 agent。

**统一 apply / 归档序**（Track G 全局决策）：本轨顺序 SK4 → SK5（本 change）→ SK1 → SK3 → SK6。SK5 排在 SK4 之后，故审计闸门直接接在 SK4 已抽出的统一构建逻辑 `_build_index` 内（启动扫描与运行期重扫都覆盖）。本 capability 为纯 ADDED。

docs/capabilities/skill.md「安全审计（注入防护）」定义：加载时扫描 Skill 内容，识别已知 prompt 注入模式（列举 16 类，如「忽略之前的指令」、伪装 system 指令、shell 注入命令等）；命中可疑模式 → 写审计日志 + 启动时控制台警告；命中严重模式 → **拒绝加载**该 Skill。

error-classification（AR5）确立了「静态不可变表 + 纯函数判定 + 标志位/严重度」的范式（`CLASSIFICATION_TABLE` + `classify()`）。本 change 在审计维度复用同一范式：`AUDIT_RULES` 静态规则表 + `audit()` 纯函数返回命中清单。

约束（CLAUDE.md）：禁止 AI 框架；禁止全局可变状态（规则表为模块级不可变常量，可被测试只读引用）；新模块结构 import → 常量 → 数据类 → 函数；异常不吞、catch 后 log 或 re-raise；mypy strict；行长 100；TDD Hard Gate；测试 skills 目录隔离 tmp_path，LLM 调用 mock（本 change 不用 LLM）。

## Goals / Non-Goals

**Goals:**
- 提供 `audit(content) -> list[AuditFinding]` 纯函数，对 SKILL.md 正文运行已知注入模式规则。
- 规则带严重度（`suspicious` / `severe`），来自单一静态规则表。
- 命中 severe → 该 Skill 不进入可注入集合（内容永不注入），记审计日志。
- 命中 suspicious → 仍可注入，但记审计日志 + 启动控制台告警。
- 审计命中写入结构化审计轨迹，便于排查。

**Non-Goals:**
- 不调用 LLM 做语义审计（本 change 纯静态规则；语义审计如有需要属后续）。
- 不穷尽 16 类规则的最终清单（先落地审计闸门 + 框架 + 代表性规则；规则集维护见 Open Questions）。
- 不审计 frontmatter（SK2 已用 `safe_load` 规避对象构造风险；本 change 审计的是注入正文的语义内容）。
- 不审计 L3 附属资源（SK1 规定 L3 不进 prompt，不构成注入面；附属资源审计如需要属后续）。
- 不实现热加载、禁用机制、多 Skill 共存、渐进式加载（各自 change）。

## Decisions

### D1：静态规则表 + 纯函数 audit
新增 `src/fleetent/skill_audit.py`：
- `Severity`：`str` 枚举，`suspicious` / `severe`。
- `AuditRule`（frozen dataclass）：`rule_id: str`、`pattern`（编译正则或短语判据）、`severity: Severity`。
- `AUDIT_RULES: tuple[AuditRule, ...]`：模块级不可变规则表，注入模式 → 规则的单一事实来源。
- `AuditFinding`（frozen dataclass）：`rule_id` / `severity`（命中结果）。
- `audit(content: str) -> list[AuditFinding]`：对正文逐条规则匹配，返回全部命中（无副作用、可单测）。
**为何**：审计判定（规则匹配）与处置（拒绝/告警）分离；规则集中在一张表里易审计、易扩展；纯函数无副作用便于穷举单测。复用 AR5 已验证的「静态表 + 纯函数」范式。
**Alternatives**：①把规则散写在 `skill_registry`——被否，审计逻辑应独立成模块、可单独演进与测试；②用插件式 checker 列表——被否，注入审计是「一段文本跑一组规则」的查表/匹配问题，与 AR5 同理无需多策略对象。

### D2：处置分级 —— severe 拒绝纳入可注入集合，suspicious 记录但放行
审计接在「纳入可注入索引」前：
- 命中任一 `severe` 规则：该 Skill **不进入可被注入的索引**（或在索引中标记为不可注入，使 `match`/注入链跳过它），其正文**永不**被拼入 system prompt；记一条审计日志（含路径 + 命中规则）。
- 仅命中 `suspicious`（无 severe）：Skill 正常纳入可注入索引，但记审计日志（含路径 + 命中规则）并在**启动扫描时**输出控制台告警。
- 无命中：正常纳入，不告警。
**为何**：精确对应 skill.md「严重 → 拒绝加载；可疑 → 审计日志 + 启动告警」。拒绝纳入可注入集合是最强保证——severe 内容根本没有进入注入链的机会。
**Alternatives**：①severe 仅告警不拒绝——被否，违背 skill.md「拒绝加载」的明文；②severe 直接从 `_index` 删除使 `load()` 也失败——可选实现，但保留「标记不可注入」更利于运维查询「为什么这个 Skill 被拒」；最终采「不进入可注入集合」。

**与 SK6 `load` 契约的显式对照（避免分叉）**：SK6 定 `load()` 不受**禁用**（`enabled`/`disabled_skills`/agent 黑名单）约束——禁用只约束自动匹配注入、不阻断按名显式 `load`，供排查/管理。本 change 的 severe **拒绝纳入可注入集合**与 SK6 的 `load` 契约**不冲突且语义对齐**：审计与禁用是两条不同的「排除出可注入集合」的来源，二者都只作用于**自动匹配注入路径**，都不改变 `load()` 的「按名读原文」契约。因此本 change 采取与 SK6 一致的口径——**severe Skill 不进入可注入集合（永不被自动匹配/注入），但 `load()` 仍可按名取其原文供人工排查**；`load()` 是禁用与审计共同的「安全出口」（取原文排查，但取到的内容不会经注入链进 system prompt）。这样 SK5 与 SK6 对 `load` 的语义完全一致，无分叉。

### D3：审计在统一构建逻辑内接入，覆盖扫描与重扫
审计闸门接在 Skill 纳入索引的构建路径上。若 SK4（热加载）已抽出 `_build_index`，审计接在其内，则启动扫描与运行期重扫都自动经过审计；若 SK4 未先合入，本 change 在 `scan` 内接入并标注：SK4 抽取构建逻辑时需把审计一并纳入。
**为何**：审计必须覆盖**所有**进入可注入集合的路径，不能只在启动时审、重扫时漏审。
**Alternatives**：只在 `scan` 接入——被否，重扫（SK4）引入的新 Skill 会绕过审计，留出注入面。

### D4：审计轨迹用结构化日志，不引专门存储
审计命中经 structlog 记结构化条目（字段含 skill 路径、规则标识、严重度、处置=拒绝/放行），归入审计轨迹。
**为何**：复用项目既有 structlog；与 SK2 解析失败告警、AR5 trace 写入的可观察性风格一致；无需为审计单建存储。
**Alternatives**：写入 `data/users.db` 审计表——被否，本 change 不需结构化查询，结构化日志足够；若后续需查询可再升级。

## Risks / Trade-offs

- [规则集不全 → 漏报真实注入] → 本 change 落地审计**框架 + 闸门 + 代表性规则**，规则集可在不改 capability 契约的前提下扩充；spec 以「命中规则即按严重度处置」为契约，不把规则数量写死。
- [正则误报 → 误拒合法 Skill] → severe 规则取「高确信」模式（如显式「ignore previous/all instructions」、伪装 `system:` 指令、明显 shell 注入），可疑模式归 suspicious 仅告警不拒绝；误拒可经审计日志快速定位并调整规则。
- [审计绕过：把注入语句藏在 L3 附属文件] → SK1 规定 L3 不进 prompt，附属文件不构成注入面；若未来允许注入附属内容需同步扩展审计范围（标注于 Non-Goals）。
- [拒绝纳入后运维不知情] → severe 拒绝必记审计日志且（若发生在启动）控制台告警，运维可据日志定位被拒 Skill 与命中规则。

## Open Questions

- 16 类规则的最终清单与维护方：是否纳入版本控制、如何更新？（skill.md 已列为待决）本 change 先落代表性规则与可扩展规则表，清单治理留待认领。
- severe 被拒的 Skill 是否仍允许 `load()` 显式取原文供人工排查——**已在 D2 定**：与 SK6 的 `load` 契约对齐，severe Skill 不进入可注入集合（永不自动注入），但 `load()` 仍可按名取原文供排查（`load` 是禁用与审计共同的「安全出口」），不再悬空。
- 是否需要让管理员经配置临时豁免某条规则 / 某个 Skill（allowlist）——本 change 不实现，按需后续。

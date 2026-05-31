## Context

Skill 注入是「把 SKILL.md 正文原样拼进 system prompt」（`agent_loop.py` 中 `run_sync()` 行 414-415、`run_stream()` 行 453；`run()` 行 234 不做注入）。`skill_registry.scan()`（行 31-56）只校验 frontmatter 能否解析（SK2），对**正文内容**零审查。由于 system prompt 是 agent 行为的最高优先指令源，一篇含注入语句的 SKILL.md 注入后即可劫持 agent。

**统一 apply / 归档序**（Track G 全局决策）：本轨顺序 SK4 → SK5（本 change）→ SK1 → SK3 → SK6。SK5 排在 SK4 之后，故审计闸门直接接在 SK4 已抽出的统一构建逻辑 `_build_index` 内（启动扫描与运行期重扫都覆盖）；SK5 排在 SK1 之前，故 SK1 的 L1 注入分级（注入 name + description）尚未落地，其与审计的交汇契约由本 change 前置约定（见 D5），SK1 落地时兑现。审计闸门（决定「哪些 Skill 不进可注入集合」）与 SK1 的 L1/L2 分级（决定「注入什么内容」）**正交**，叠加在 `_index` 这一单一事实源上，顺序合理无需调整。本 capability 为纯 ADDED。

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
- 不审计 frontmatter 的**对象构造风险**（SK2 已用 `safe_load` 规避）；但审计范围**不止于正文**——凡会被注入链拼进 system prompt 的字段都须覆盖：本 change 审计 **L2 正文 + L1 注入的 description 字段**。其余 frontmatter 字段（name 除外，见下）不进 prompt，不构成注入面，不审计。
  - **例外说明**：SK1 的 L1 注入的是 **name + description**。description 为自由文本、是主要注入载体，故纳入审计；name 受 SK2 解析约束（标识符/短串），注入面极小，本 change 不强制审计 name（如需可后续以同一规则表扩展）。
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

### D2：处置分级 —— severe 打 `audit_blocked` 标志（留在 `_index`），suspicious 记录但放行
审计接在 `_build_index` / 纳入可注入索引前。severe 的处置**明确采标志位方案**（非「不进 `_index`」）：
- 命中任一 `severe` 规则：该 Skill **仍留在 `_index`**，但其条目被打上 `audit_blocked` 标志（等价地，`injectable=False`）。`match` / `match_all` / `l1_summary`（L1 清单）等**所有进入注入链的读取面**MUST 跳过被标记项——其 **name/description（L1）与正文（L2）均永不被拼入 system prompt**；记一条审计日志（含路径 + 命中规则 + disposition=拒绝）。`load()` **忽略**该标志，按名仍返回原文供人工排查。
- 仅命中 `suspicious`（无 severe）：Skill 正常纳入可注入索引，但记审计日志（含路径 + 命中规则）并在**启动扫描时**输出控制台告警。
- 无命中：正常纳入，不告警。
**为何明确定 (b)**：spec 要求「severe 被拒后 `load()` 仍可取原文」。若选 (a)「不进入 `_index`」，`load()` 读 `_index[name].path` 会 KeyError，与该 Requirement **直接矛盾**。故 commit 到 (b)：留条目、打标志——既满足「永不注入」（注入链跳过标记项），又满足「`load()` 可取原文」（条目仍在 `_index`），且利于运维查询「为什么这个 Skill 被拒」。
**Alternatives**：①severe 仅告警不拒绝——被否，违背 skill.md「拒绝加载」的明文；②severe 从 `_index` 删除——被否，会使 `load()` KeyError，违反「`load()` 仍可取原文」契约。

**与 SK6 `load` 契约的显式对照（避免分叉）**：SK6 定 `load()` 不受**禁用**（`enabled`/`disabled_skills`/agent 黑名单）约束——禁用只约束自动匹配注入、不阻断按名显式 `load`，供排查/管理。本 change 的 severe **拒绝纳入可注入集合**与 SK6 的 `load` 契约**不冲突且语义对齐**：审计与禁用是两条不同的「排除出可注入集合」的来源，二者都只作用于**自动匹配注入路径**，都不改变 `load()` 的「按名读原文」契约。因此本 change 采取与 SK6 一致的口径——**severe Skill 不进入可注入集合（永不被自动匹配/注入），但 `load()` 仍可按名取其原文供人工排查**；`load()` 是禁用与审计共同的「安全出口」（取原文排查，但取到的内容不会经注入链进 system prompt）。这样 SK5 与 SK6 对 `load` 的语义完全一致，无分叉。

### D3：审计在统一构建逻辑（`_build_index`）下闸，覆盖扫描与重扫；build-gate 天然免疫「漏注入点」
审计闸门接在 Skill 纳入索引的构建路径（SK4 抽出的 `_build_index`）上。若 SK4 已抽出 `_build_index`，审计接在其内，则启动扫描与运行期重扫都自动经过审计；若 SK4 未先合入，本 change 在 `scan` 内接入并标注：SK4 抽取构建逻辑时需把审计一并纳入。
**为何在「索引构建处」而非「注入处」下闸**：注入点目前有三个——`agent_loop.run_sync`、`agent_loop.run_stream`、`im_gateway/normalizer.py`——它们都从**同一个** `_index` 读 Skill。把审计下沉到索引构建处、由 `audit_blocked` 标志在 `_index` 上一次性生效，三个注入点（及未来新增的注入点）自动注入不到被标记的 severe Skill，**免疫「漏某个注入点忘了挡」的问题**。反之若在每个注入点各自做审计，新增注入点极易遗漏，留出注入面。这与 SK1 的 L1/L2 注入分级**正交**：分级决定「注入什么内容」，build-gate 决定「哪些 Skill 根本不进可注入集合」，二者在 `_index` 这一单一事实源上叠加，顺序合理无需调整。
**为何必须覆盖重扫**：审计必须覆盖**所有**进入可注入集合的路径，不能只在启动时审、重扫时漏审。
**Alternatives**：①在各注入点分别审计——被否，新增注入点易漏；②只在 `scan` 接入——被否，重扫（SK4）引入的新 Skill 会绕过审计。

### D4：审计轨迹用结构化日志，不引专门存储
审计命中经 structlog 记结构化条目（字段含 skill 路径、规则标识、严重度、处置=拒绝/放行），归入审计轨迹。
**为何**：复用项目既有 structlog；与 SK2 解析失败告警、AR5 trace 写入的可观察性风格一致；无需为审计单建存储。
**Alternatives**：写入 `data/users.db` 审计表——被否，本 change 不需结构化查询，结构化日志足够；若后续需查询可再升级。

### D5：与 SK1（注入分级）的跨 change 约定 —— L1 排除 + audit 覆盖 description 一并到位
SK5（本 change）在统一 apply 序中排在 SK1 **之前**（SK4 → SK5 → SK1 → …），SK5 落地时 L1（注入 name + description）尚未实现，但其影响须前置约定，避免 SK1 落地时引入审计绕过：
- **绕过成因**：SK1 的 L1 注入 **name + description（frontmatter）**。若 severe 排除只挡 L2 正文、且 audit 只扫正文，则被拒 Skill 的 description 仍会经 L1 注入进 system prompt——审计被绕过（安全主因）。
- **约定（写入本 design，SK1 实现时必须遵守）**：
  1. **L1 清单排除 audit-flagged**：`l1_summary` / L1 注入面 MUST 跳过 `audit_blocked` 标记的 Skill（与 `match`/`match_all` 一致），severe Skill 的 name/description 不进 L1。
  2. **audit 覆盖 description**：`audit()` 的输入 MUST 包含会被 L1 注入的 description 字段（不止 L2 正文），使含注入串的 description 也能命中规则并触发标记。
- 这两点是同一安全保证的两半——只做其一仍留绕过面，故 SK1 落 L1 时 **必须一并到位**。
**为何作为跨 change 约定写在 SK5**：审计闸门与标志位是 SK5 引入的机制，L1 注入面是 SK1 引入的；二者交汇处的安全契约由先落地的一方（SK5）立约、后落地方（SK1）兑现，避免顺序差导致的安全空窗。
**Alternatives**：等 SK1 落地后再补审计 description——被否，会留出「L1 已注入但 audit 未覆盖 description」的真空期；前置约定零真空。

## Risks / Trade-offs

- [规则集不全 → 漏报真实注入] → 本 change 落地审计**框架 + 闸门 + 代表性规则**，规则集可在不改 capability 契约的前提下扩充；spec 以「命中规则即按严重度处置」为契约，不把规则数量写死。
- [正则误报 → 误拒合法 Skill] → severe 规则**严格限「高确信」模式**（如显式「ignore previous/all instructions」、伪装 `system:` 指令、明显 shell 注入），以免误拒合法的安全/渗透测试类 Skill（其正文常含示例性注入串作为讲解素材）；存疑模式一律归 suspicious 仅告警不拒绝；误拒可经审计日志快速定位并调整规则。allowlist 豁免作为 Open Question 推迟，不在本 change 实现。
- [审计绕过：把注入语句藏在 L3 附属文件] → SK1 规定 L3 不进 prompt，附属文件不构成注入面；若未来允许注入附属内容需同步扩展审计范围（标注于 Non-Goals）。
- [拒绝纳入后运维不知情] → severe 拒绝必记审计日志且（若发生在启动）控制台告警，运维可据日志定位被拒 Skill 与命中规则。

## Open Questions

- 16 类规则的最终清单与维护方：是否纳入版本控制、如何更新？（skill.md 已列为待决）本 change 先落代表性规则与可扩展规则表，清单治理留待认领。
- severe 被拒的 Skill 是否仍允许 `load()` 显式取原文供人工排查——**已在 D2 定**：与 SK6 的 `load` 契约对齐，severe Skill 留在 `_index` 但打 `audit_blocked` 标志（注入链跳过、永不自动注入），`load()` 忽略标志仍按名取原文供排查（`load` 是禁用与审计共同的「安全出口」），不再悬空。
- 是否需要让管理员经配置临时豁免某条规则 / 某个 Skill（allowlist）——**推迟，本 change 不实现**，按需后续认领。

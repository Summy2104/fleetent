## Context

`match()`（skill_registry.py 行 94）对 `_index` 逐项做关键词命中判定，先经 `_resolve_disabled_skills` + `_disabled_reason` **过滤禁用项**（`enabled_by_default` 为假或名在 `disabled_skills` 内则跳过并 log），命中即 `return name`——**只取第一个**，且顺序就是 `dict` 的插入顺序（扫描 `base.glob("*/SKILL.md")` 的遍历顺序），不可解释。`agent_loop` 注入链经 `_matched_skill_content(user_input, allowed_skills, blocked_skills)`（行 231）调用 `match` → `check_skill_access`（**agent 绑定门控**：allowed_skills 白名单 / blocked_skills 黑名单，opt-in，`allowed_skills is None` 时不注入）→ `load` 注入。注入消费点为 `run_sync()`（行 496）与 `run_stream()`（行 531），二者都经 `_matched_skill_content`；`run()` 只收预构建 messages、不做 Skill 注入。**第三处注入点**在 `im_gateway/normalizer.py`（行 91-100），独立调 `match` + `check_skill_access` + `load`。

**关键事实订正（spec 写在合并前、已过期）**：origin 的 `match` **已带** `disabled_skills` 过滤（行 94 的 `disabled_skills` 入参），注入 **已经过** `_matched_skill_content` 的 agent 绑定门控。因此切换到「全部命中」时，**绝不能**改用一个不带这些过滤的 `match_all` 而把过滤推给 SK6——那会回归掉 origin 已落地的禁用过滤 + agent 绑定。

**统一 apply / 归档序 + match_all owner**（Track G 全局决策）：本轨顺序 SK4 → SK5 → SK1 → SK3（本 change）→ SK6。本 change 是 **`match_all` 共享中间产物结构的 owner**：SK1 仅建立 L1/L2 注入基线（始终注入 L1、命中注入单个 L2），SK3 扩展 `match_all`（返回带「命中 / 已过 disabled 过滤」的候选名）并据此改写 L2 选定，SK6 在 SK3 的候选中间产物上叠加禁用标注 + trace（SK6 不返回禁用项，但保留禁用信息供 trace）。本 capability 为纯 ADDED。

skill.md「多 Skill 共存（v1.0）」明确三条策略：①所有命中 Skill 的 L1 摘要共存于 system prompt；②L2 全文保持首次命中原则（避免注入内容过多）；③`exclusive: true` 的 Skill 命中**且真有冲突时**向用户询问选择。流程图 `conflict` 子图同此。

SK2 已把索引升级为 `dict[str, SkillEntry]` 并以 `yaml.safe_load` 解析 frontmatter，新增布尔字段只需在 `SkillEntry` 加字段并在 `scan` 填充。SK1 引入「L1 全量清单始终注入 + L2 命中注入」，其 L1 清单天然覆盖「全部命中的 L1 共存」（清单本就是全量）。

约束（CLAUDE.md）：禁止 AI 框架；禁止全局可变状态；新模块结构 import → 常量 → 数据类 → 函数；mypy strict；行长 100；TDD Hard Gate；测试 skills 目录隔离 tmp_path，LLM 调用 mock。

## Goals / Non-Goals

**Goals:**
- 提供确定性的「全部命中」匹配（`match_all`），消除依赖扫描顺序的隐式偏置，**并保留 origin `match` 已有的 disabled 过滤**。
- 注入链对每个候选**逐项保留** `check_skill_access` 的 agent 绑定门控（不回归）。
- 多命中时 L1 摘要共存（复用 SK1 的全量 L1 清单）。
- 多命中时 L2 全文保持「只注入一个」，确定性选定。
- 命中数 > 1 且含 `exclusive: true`（真冲突）时产出「请用户选择」信号，不擅自选定 L2；**单个 exclusive 独命中正常注入**。
- 明确给出「用户选定后回灌选中 L2」的语义（D5）。

**Non-Goals:**
- 不改关键词匹配的命中判定算法（仍是 description 关键词出现判定）。
- 不实现「多篇 L2 全文同时注入」（明确违背 skill.md 的注入最小化）。
- 不实现 exclusive 的自动仲裁（由谁优先）——真冲突即交还用户决定。
- 不实现询问用户的具体 UI/交互通道（注入链只产出可被调用方消费的信号），但**定义回灌语义**（D5）。
- 不实现热加载、安全审计（SK6 的禁用标注 + trace）。

## Decisions

### D1：新增 `match_all` 返回确定性全部命中，保留 disabled 过滤
`skill_registry` 新增 `match_all(user_input: str, disabled_skills: list[str] | None = None) -> list[str]`：复用现有关键词命中判据，**沿用 `match` 的 `_resolve_disabled_skills` + `_disabled_reason` 禁用过滤**（跳过 `enabled_by_default` 为假或名在 `disabled_skills` 内的项并 log），收集**所有**命中且未被禁用过滤掉的 Skill 名，按**确定性顺序**（如名称升序）返回。原 `match()`（首次命中）保留供向后兼容，但注入链改用 `match_all`。
**为何**：skill.md 要求「所有命中 Skill 的 L1 共存」与「确定性选 L2」，都需要先拿到全部命中而非首个；名称升序是稳定可解释的顺序，去掉「扫描插入顺序」偏置。`disabled_skills` 入参与默认解析必须与 `match` 一致，否则注入链切到 `match_all` 会丢失 origin 已落地的禁用过滤（回归）。
**Alternatives**：①给 `match()` 加 `all=True` 参数——被否，单函数承载两种返回形态（str vs list）类型不清晰，mypy strict 下别扭；②`match_all` 不带 disabled 过滤、把过滤全推给 SK6——**被否（核心订正）**，origin `match` 已有过滤，下放即回归；③按 description 命中关键词数排序——被否，引入隐式打分语义，本 change 不做相关性排序，名称序已足够且可解释。

### D2：L1 共存复用 SK1 全量清单，L2 改写为「match_all 确定性首个过门控非互斥命中」
**与 SK1 的交接点（重要）**：SK1 落地的 L2 选定是「`match()` 单命中即注入」；本 change **改写这同一段注入逻辑**——按 Track G 全局决策统一到 `match_all` 共享中间产物，由其确定性候选列表派生 L2，而非 `match()` 的首个命中。SK3 排在 SK1 之后实施，故是在 SK1 基线之上替换 L2 选定，而非并存两套。
- L1 共存：SK1 的 `l1_summary()` 注入的就是**全量** Skill 清单，天然包含所有命中 Skill 的摘要，无需为「多命中」另做 L1 逻辑（SK1 已先合入，直接复用）。
- L2 选定：从 `match_all` 的确定性列表里取**首个过 agent 绑定门控（`check_skill_access`）的非互斥**命中作为唯一注入的 L2 全文，替换 SK1 的 `match()` 首个命中选定。
**为何**：贴合 skill.md「L2 保持首次命中原则」；确定性列表 + 取首个 = 可复现、可解释的单一 L2；统一到 `match_all` 共享中间产物让 SK6 的禁用标注、互斥判定有单一派生源。
**Alternatives**：按相关性打分选 L2——被否，超出本 change 范围（无打分机制），徒增不确定性。

### D3：`exclusive` 字段 + **真冲突**（命中数 > 1 且含互斥）才产出询问信号
`SkillEntry` 新增 `exclusive: bool = False`，由 SK2 的 frontmatter 解析在 `scan` 处填充（`bool(frontmatter.get("exclusive", False))`）。注入链对 `match_all` 的（已过 disabled 过滤、逐候选过绑定门控的）命中集合判定：
- **命中数 > 1 且其中存在至少一个 `exclusive: true` 的 Skill**（即真有冲突）时——**不注入任何 L2**，产出一个可被调用方消费的「请用户在这些命中里选择」信号（含候选 Skill 名）。
- **单个 Skill 独自命中（命中数 == 1），即便它 `exclusive: true`**——按普通命中正常注入其 L2，**不产出询问信号**。无冲突对象，独占即生效。
- 命中数 > 1 但无任何互斥项时——按 D2 注入首个命中的 L2，不询问。
**为何（核心订正）**：原规则「命中集合中存在任一 exclusive → 不注入 + 询问」有 bug——一个 exclusive Skill **单独命中**（无任何冲突对象）也会被触发「1 个候选的询问」、且**永远无法被正常注入**，等于把 exclusive Skill 变成不可用。`exclusive` 的语义是「不与其他 Skill 同时生效」，独占命中恰恰满足该约束，应正常注入。仅当 > 1 个候选且含互斥（真有取舍）才交还用户。
**Alternatives**：①exclusive 命中时直接注入优先级最高者——被否，违背「真冲突时询问用户选择」；②保留「任一 exclusive 即询问」原规则——**被否（本 change 修复对象）**，使单 exclusive Skill 不可用；③exclusive 真冲突时全不注入且静默——被否，用户无从得知为何 Skill 没生效，应给出候选让其选。

### D4：询问信号的默认承载形态 = 注入辅助返回 `(system_prompt, ask_signal | None)`
注入链在真冲突命中时不直接调用任何 IM/CLI 发问 API，而是产出结构化信号（候选 Skill 名列表）由上层决定如何向用户呈现。**本 change 给定默认承载形态，使 spec scenario 可写可执行断言**：

三处注入点（`run_sync` / `run_stream` 经 `_matched_skill_content`、`normalizer`）共用的单一注入辅助函数返回一个二元组 `(system_prompt: str, ask_signal: AskSignal | None)`，其中 `AskSignal` 为 frozen dataclass，至少含 `candidates: list[str]`（真冲突命中的候选 Skill 名）。
- 非真冲突命中（含单个 exclusive 独命中、多命中无互斥）：`ask_signal = None`，system_prompt 含 L1 共存 + 单个 L2。
- 真冲突命中（> 1 命中且含互斥）：`system_prompt` 不含任一命中 Skill 的 L2（仅 L1 共存），`ask_signal = AskSignal(candidates=[...])`。

`run_sync()` / `run_stream()` / `normalizer` 各自决定如何呈现该信号：`run_sync()`（CLI）可将其转为返回给用户的提示文本；`run_stream()` 可作为一个 SSE 事件（如 `{"type": "skill_choice", "candidates": [...]}`）发出；`normalizer` 可经 `reply_func` 发回。注入链与 skill_registry 本身不耦合具体通道。
**为何**：返回值（而非异常）让「注入照常返回 system_prompt + 可选信号」语义清晰、对三条调用路径一致、便于单测断言信号内容；与「permission_gate 产出审批信号、上层消费」的既有分层一致。
**Alternatives**：①抛异常承载——被否，真冲突是正常分支而非错误，异常会打断三条路径的正常返回；②把提示直接拼进 system prompt 文本——被否，绑定了呈现形态、上层无法按通道差异化处理、也难以结构化断言。

### D5：用户选定后的回灌语义（结构化选择 → 回灌选中 L2）
D4 的 `ask_signal(candidates=[...])` 只是「产出待选项」，**用户选定后如何让选中 Skill 生效**这一回灌语义此前缺失。本 change 定义（不实现具体 UI 通道，但定语义）：

- **承载形态 = 结构化选择 → 回灌选中 L2**（首选语义）：调用方向用户呈现 `candidates` 后，用户选定一个 Skill 名，调用方携该选定名**再次进入注入辅助**（如以一个「forced_skill / chosen_skill」入参，或在下一轮请求里把选定名作为单一命中传入），注入辅助对该选定 Skill **正常注入其 L2 全文**（仍经 `check_skill_access` 绑定门控与 disabled 过滤，门控不通过则视为无效选择、不注入）。即「选择」等价于把命中集合收敛为单个候选，从而走 D3 的「单命中正常注入」分支。
- **退化语义（备选）**：若上层不实现结构化选择回传，可提示用户**改措辞使只触发一个 Skill**——用户下一轮输入只命中单个 Skill 时，自然走单命中注入分支。此为无需新增入参的最小可用回退。

本 change 在 spec/scenario 层断言「选定名回灌 → 注入辅助对该名注入 L2、ask_signal 为 None」这一可观察契约；选择回传的具体通道（CLI prompt / SSE 往返 / IM 按钮）属呈现细节，不在本 change 实现范围。
**为何**：补齐缺失的闭环——只产出 candidates 而无回灌语义，则 exclusive 询问后用户无路可走。结构化回灌复用 D3 的单命中分支，无需新增仲裁逻辑。
**Alternatives**：自动选优先级最高者回灌——被否，违背「交还用户」；询问后永久不注入——被否，等于 exclusive Skill 在多命中下不可用。

### D6：单一 `injectable` 谓词作为与 SK1/SK5/SK6 的协调点
为让 SK1（L1/L2 基线）、SK5（per-agent 绑定 / 若涉及）、SK6（禁用标注 + trace）在同一注入链上叠加而不互相覆盖，本 change 把「一个 Skill 是否可注入」收敛为单一谓词 `injectable(name)`：

```
injectable(name) ⇔ 命中(name)
                  ∧ enabled(SkillEntry.enabled_by_default)
                  ∧ ¬disabled(name ∈ disabled_skills 来源)
                  ∧ ¬default_disabled(SK5/SK6 的默认禁用约定，若有)
                  ∧ 过绑定(check_skill_access(name, allowed_skills, blocked_skills))
                  ∧ ¬audit_blocked(SK6 安全审计阻断，若有)
```

`match_all` 负责前三项（命中 ∧ enabled ∧ ¬disabled），注入链在其结果上逐候选应用 `过绑定`，SK5/SK6 后续在此谓词上挂 `¬default_disabled` / `¬audit_blocked`。L2 选定 = 确定性列表中**首个 `injectable` 且非互斥**的候选；真冲突判定 = `injectable` 候选中 `exclusive` 项与总数的关系（见 D3）。
**为何**：把分散在三处注入点、跨多个 change 的「能否注入」判据收敛成单一可组合谓词，避免 origin 已有的 disabled 过滤 / 绑定门控在多命中改造中被某一处漏掉（即本次订正的回归风险），也给 SK6 一个明确挂载点。
**Alternatives**：各注入点各自零散判定——被否，正是当前三处逻辑漂移、易回归的根因。

## Risks / Trade-offs

- [`match_all` 比 `match` 遍历全表不再短路] → Skill 数量级很小（人工编写的领域指南），全表关键词判定成本可忽略；换取多命中正确性。
- [名称升序选 L2 可能与「用户预期的优先级」不一致] → 本 change 不引入相关性/优先级语义，确定性优先于「智能」；如需优先级可后续在 frontmatter 加 `priority` 字段（不破坏本 capability 契约）。
- [真冲突询问信号若上层未消费会导致候选都不注入] → spec 明确真冲突命中时不注入 L2 是预期行为；上层须消费信号向用户发问并回灌选定（D5），这是分层契约，由调用方测试覆盖。
- [多命中改造误删 origin 的 disabled 过滤 / 绑定门控] → **本次订正的核心风险**；D1 要求 `match_all` 保留 disabled 过滤、D2/D6 要求逐候选保留绑定门控，tasks 有专门失败测试守护（多命中下禁用项/越权项不注入）。
- [与 SK1 的合入顺序耦合] → SK1 先合入，本 change 在其 L1/L2 基线上替换 L2 选定；design 标注协调点，两者对 L1 的语义一致不冲突。

## Open Questions

- 真冲突询问信号的承载形态已由 D4 定为默认形态、回灌语义由 D5 定为「结构化选择→回灌选中 L2（退化为改措辞）」；剩余开放项仅为 `run_stream` 的 SSE 事件 `type` 字段命名（如 `skill_choice`）、选择回传的具体通道与 CLI 提示文案，属呈现细节、不影响 spec 可观察契约。
- 是否需要 `priority` frontmatter 字段来替代「名称升序」选 L2——本 change 不引入，留作后续按需扩展。

## Context

`match()`（skill_registry.py 行 59-70）对 `_index` 逐项做关键词命中判定，命中即 `return name`——**只取第一个**，且顺序就是 `dict` 的插入顺序（扫描 `base.glob("*/SKILL.md")` 的遍历顺序），不可解释。`agent_loop` 注入链拿到这单个名后 `load()` 注入——注入只在 `run_sync()`（行 408-415）与 `run_stream()`（行 451-453），`run()`（行 234）只收预构建 messages、不做 Skill 注入。

**统一 apply / 归档序 + match_all owner**（Track G 全局决策）：本轨顺序 SK4 → SK5 → SK1 → SK3（本 change）→ SK6。本 change 是 **`match_all` 共享中间产物结构的 owner**：SK1 仅建立 L1/L2 注入基线（始终注入 L1、命中注入单个 L2），SK3 扩展 `match_all`（返回带「命中 / 禁用来源 / exclusive」标注的候选）并据此改写 L2 选定，SK6 在 SK3 的候选中间产物上叠加禁用标注 + trace（SK6 不返回禁用项，但保留禁用信息供 trace）。本 capability 为纯 ADDED。

skill.md「多 Skill 共存（v1.0）」明确三条策略：①所有命中 Skill 的 L1 摘要共存于 system prompt；②L2 全文保持首次命中原则（避免注入内容过多）；③`exclusive: true` 的 Skill 命中后向用户询问选择。流程图 `conflict` 子图同此。

SK2 已把索引升级为 `dict[str, SkillEntry]` 并以 `yaml.safe_load` 解析 frontmatter，新增布尔字段只需在 `SkillEntry` 加字段并在 `scan` 填充。SK1 引入「L1 全量清单始终注入 + L2 命中注入」，其 L1 清单天然覆盖「全部命中的 L1 共存」（清单本就是全量）。

约束（CLAUDE.md）：禁止 AI 框架；禁止全局可变状态；新模块结构 import → 常量 → 数据类 → 函数；mypy strict；行长 100；TDD Hard Gate；测试 skills 目录隔离 tmp_path，LLM 调用 mock。

## Goals / Non-Goals

**Goals:**
- 提供确定性的「全部命中」匹配（`match_all`），消除依赖扫描顺序的隐式偏置。
- 多命中时 L1 摘要共存（复用 SK1 的全量 L1 清单）。
- 多命中时 L2 全文保持「只注入一个」，确定性选定。
- `exclusive: true` 命中时产出「请用户选择」信号，不擅自选定 L2。

**Non-Goals:**
- 不改关键词匹配的命中判定算法（仍是 description 关键词出现判定）。
- 不实现「多篇 L2 全文同时注入」（明确违背 skill.md 的注入最小化）。
- 不实现 exclusive 的自动仲裁（由谁优先）——互斥即交还用户决定。
- 不实现询问用户的具体 UI/交互通道（注入链只产出可被调用方消费的信号）。
- 不实现热加载、安全审计、禁用机制、per-agent 绑定。

## Decisions

### D1：新增 `match_all` 返回确定性全部命中
`skill_registry` 新增 `match_all(user_input: str) -> list[str]`：复用现有关键词命中判据，收集**所有**命中的 Skill 名，按**确定性顺序**（如名称升序）返回。原 `match()`（首次命中）保留供向后兼容，但注入链改用 `match_all`。
**为何**：skill.md 要求「所有命中 Skill 的 L1 共存」与「确定性选 L2」，都需要先拿到全部命中而非首个；名称升序是稳定可解释的顺序，去掉「扫描插入顺序」偏置。
**Alternatives**：①给 `match()` 加 `all=True` 参数——被否，单函数承载两种返回形态（str vs list）类型不清晰，mypy strict 下别扭；②按 description 命中关键词数排序——被否，引入隐式打分语义，本 change 不做相关性排序，确定性的名称序已足够且可解释。

### D2：L1 共存复用 SK1 全量清单，L2 改写为「match_all 确定性首个非互斥命中」
**与 SK1 的交接点（重要）**：SK1 落地的 L2 选定是「`match()` 单命中即注入」；本 change **改写这同一段注入逻辑**——按 Track G 全局决策统一到 `match_all` 共享中间产物，由其确定性候选列表派生 L2，而非 `match()` 的首个命中。SK3 排在 SK1 之后实施，故是在 SK1 基线之上替换 L2 选定，而非并存两套。
- L1 共存：SK1 的 `l1_summary()` 注入的就是**全量** Skill 清单，天然包含所有命中 Skill 的摘要，无需为「多命中」另做 L1 逻辑（SK1 已先合入，直接复用）。
- L2 选定：从 `match_all` 的确定性列表里取**首个非互斥**命中作为唯一注入的 L2 全文，替换 SK1 的 `match()` 首个命中选定。
**为何**：贴合 skill.md「L2 保持首次命中原则」；确定性列表 + 取首个 = 可复现、可解释的单一 L2；统一到 `match_all` 共享中间产物让 SK6 的禁用标注、互斥判定有单一派生源。
**Alternatives**：按相关性打分选 L2——被否，超出本 change 范围（无打分机制），徒增不确定性。

### D3：`exclusive` 字段 + 互斥命中产出询问信号
`SkillEntry` 新增 `exclusive: bool = False`，由 SK2 的 frontmatter 解析在 `scan` 处填充（`bool(frontmatter.get("exclusive", False))`）。注入链判定命中集合：
- 命中集合中存在任一 `exclusive: true` 的 Skill（或存在多个互斥 Skill）时——**不注入任何 L2**，产出一个可被调用方消费的「请用户在这些命中里选择」信号（含候选 Skill 名）。
- 不含互斥项时——按 D2 注入首个命中的 L2。
**为何**：直接落实 skill.md「`exclusive: true` 命中后向用户询问选择」；把「擅自替用户选」改为「交还用户」，避免互斥指令同时注入导致 agent 行为矛盾。
**Alternatives**：①exclusive 命中时直接注入优先级最高者——被否，违背「询问用户选择」的明文要求；②exclusive 命中时全不注入且静默——被否，用户无从得知为何 Skill 没生效，应给出候选让其选。

### D4：询问信号的默认承载形态 = 注入链返回 `(system_prompt, ask_signal | None)`
注入链在互斥命中时不直接调用任何 IM/CLI 发问 API，而是产出结构化信号（候选 Skill 名列表）由上层决定如何向用户呈现。**本 change 给定默认承载形态（不再推迟到实现首步），使 spec scenario 可写可执行断言**：

构造 system prompt 的注入辅助函数返回一个二元组 `(system_prompt: str, ask_signal: AskSignal | None)`，其中 `AskSignal` 为 frozen dataclass，至少含 `candidates: list[str]`（互斥命中的候选 Skill 名）。
- 非互斥命中：`ask_signal = None`，system_prompt 含 L1 共存 + 单个 L2。
- 互斥命中：`system_prompt` 不含任一命中 Skill 的 L2（仅 L1 共存），`ask_signal = AskSignal(candidates=[...])`。

`run_sync()` / `run_stream()` 各自决定如何呈现该信号：`run_sync()`（CLI）可将其转为返回给用户的提示文本；`run_stream()` 可作为一个 SSE 事件（如 `{"type": "skill_choice", "candidates": [...]}`）发出。注入链与 skill_registry 本身不耦合具体通道。
**为何**：返回值（而非异常）让「注入照常返回 system_prompt + 可选信号」语义清晰、对两条调用路径一致、便于单测断言信号内容；与「permission_gate 产出审批信号、上层消费」的既有分层一致。spec scenario 因此可断言「互斥命中 → 注入链产出含候选名的 ask_signal 且不含 L2」这一可观察行为。
**Alternatives**：①抛异常承载——被否，互斥命中是正常分支而非错误，异常会打断两条路径的正常返回；②把提示直接拼进 system prompt 文本——被否，绑定了呈现形态、上层无法按通道差异化处理、也难以结构化断言。

## Risks / Trade-offs

- [`match_all` 比 `match` 遍历全表不再短路] → Skill 数量级很小（人工编写的领域指南），全表关键词判定成本可忽略；换取多命中正确性。
- [名称升序选 L2 可能与「用户预期的优先级」不一致] → 本 change 不引入相关性/优先级语义，确定性优先于「智能」；如需优先级可后续在 frontmatter 加 `priority` 字段（不破坏本 capability 契约）。
- [互斥询问信号若上层未消费会导致两个 Skill 都不注入] → spec 明确互斥命中时不注入 L2 是预期行为；上层须消费信号向用户发问，这是分层契约，由调用方测试覆盖。
- [与 SK1 的合入顺序耦合] → 若 SK1 后合入，本 change 自带最小 L1 共存；design 标注协调点，两者对 L1 的语义一致不冲突。

## Open Questions

- 互斥询问信号的承载形态已由 D4 定为默认形态（注入链返回 `(system_prompt, ask_signal | None)`，`run_sync`/`run_stream` 各自呈现）；剩余开放项仅为 `run_stream` 的 SSE 事件 `type` 字段命名（如 `skill_choice`）与 CLI 提示文案，属呈现细节、不影响 spec 可观察契约。
- 是否需要 `priority` frontmatter 字段来替代「名称升序」选 L2——本 change 不引入，留作后续按需扩展。

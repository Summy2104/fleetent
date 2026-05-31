## Why

`skill_registry.match()`（行 94）遍历索引，**第一个**关键词命中（且未被禁用过滤掉）的 Skill 名一返回就停（`return name`），后续即便有同样命中的 Skill 也被丢弃。`agent_loop` 经 `_matched_skill_content(user_input, allowed_skills, blocked_skills)`（行 231）调用 `match` → `check_skill_access`（agent 绑定门控）→ `load`，只 `load()` 并注入这单个 Skill；注入发生在 `run_sync()`（行 496）与 `run_stream()`（行 531）经由 `_matched_skill_content`，`run()` 只收预构建 messages、不做 Skill 注入。第三处注入点在 `im_gateway/normalizer.py`（行 91-100），同样调 `match` + `check_skill_access` + `load`。这导致：

- **多领域请求只得到一半指导**：用户一句话同时涉及「客户查询」与「合同审批」两个 Skill 时，只有索引顺序靠前的那个被注入，另一个的行为规范完全缺席，agent 的回复会遗漏一方（违背 skill.md 验收场景 3）。
- **命中即停带有隐式优先级偏置**：哪个 Skill 被注入取决于 `_index` 的插入顺序（扫描顺序），既非确定性语义也不可解释。
- **无法表达互斥**：两个指令实际冲突（如两套不可同时遵循的操作流程）的 Skill 同时命中时，没有任何机制提示用户取舍。

SK2 已提供结构化索引，SK1（渐进式加载）确立了「L1 全量摘要 + L2 命中全文」的分级。本 change 落实 docs/capabilities/skill.md「规划中」的**多 Skill 共存**：所有命中 Skill 的 L1 共存，L2 保持首次命中原则避免注入膨胀，`exclusive: true` **且真有冲突时**向用户询问选择。

## What Changes

- `skill_registry` 新增**返回全部命中**的匹配能力（如 `match_all(user_input, disabled_skills=None) -> list[str]`，按确定性顺序返回所有关键词命中、且未被禁用过滤掉的 Skill 名）。`match_all` **必须保留** `match` 已有的 `disabled_skills` 过滤（`enabled_by_default` / `disabled_skills` 来源），不得丢弃——否则切到不带过滤的 `match_all` 会回归掉 origin 已落地的禁用过滤。原 `match()`（首次命中）保留供向后兼容。
- **agent 绑定门控不下放**：注入链经 `_matched_skill_content`（行 231）对**每个**候选做 `check_skill_access(name, allowed_skills, blocked_skills)` 门控（与 normalizer 行 100 一致）。改为多命中后，绑定门控必须仍**逐候选**应用——要么 `match_all` 候选已带 disabled 过滤后由注入链逐项过绑定，要么注入链在 `match_all` 外统一应用绑定 + disabled 过滤。不可把绑定/禁用过滤全部推迟到 SK6。
- 注入链对**多个命中**的处理：所有命中且过门控 Skill 的 **L1 摘要**共存于 system prompt（沿用 SK1 的 L1 清单始终注入即天然满足）；**L2 全文**保持「首次（最高优先）命中只注入一个」，避免多篇全文灌爆 context。
- 引入 **`exclusive` frontmatter 字段**（布尔，缺省 `false`）：`exclusive` 字段**由本 change（SK3）新增定义**——SK2 提供的是通用 YAML frontmatter 解析能力（其 spec 只枚举 `tags`/`platforms`/`version`/`enabled_by_default`，**不含** `exclusive`），SK3 在 `SkillEntry` 新增 `exclusive: bool = False` 并在 `scan` 处用该通用解析能力填充。**仅当命中数 > 1 且其中含 `exclusive: true`（即真有冲突）时**，注入链**不擅自选定**，而是产出「请用户选择」的信号，由调用方向用户询问；**单个 exclusive Skill 独自命中（无冲突）时按普通命中正常注入 L2**，不询问。
- 命中顺序**确定性化**：多命中时按可解释的稳定顺序（如索引名排序）选定 L2 注入对象，消除「依赖扫描插入顺序」的隐式偏置。
- **三处注入收敛为单一共享注入函数**：`run_sync()` / `run_stream()`（经 `_matched_skill_content`）与 `im_gateway/normalizer.py` 三处共用同一注入辅助（产出 `(system_prompt, ask_signal | None)`），避免三份逻辑各自漂移。

## Capabilities

### New Capabilities
- `skill-multi-coexistence`: 同一请求命中多个 Skill 时的共存策略——全部命中且过禁用过滤 + agent 绑定门控的 Skill 的 L1 摘要共存、L2 全文保持首次命中只注入一个（确定性选定）、命中数 > 1 且含 `exclusive: true`（真冲突）时产出询问用户选择的信号而非擅自选定；用户选定后回灌选中 Skill 的 L2（语义见 design D5）。

### Modified Capabilities
<!-- 无既有 spec 的需求级行为变更。SK2 的 frontmatter 解析与关键词匹配算法不变；origin 的 `match` 已有 disabled_skills 过滤、注入经 _matched_skill_content 已有 agent 绑定，本次在匹配/注入层新增「全部命中」与「真冲突询问」并保留既有过滤/门控。多 Skill 共存此前无既有 spec 承载，故收口在本新 capability 内。 -->

## Impact

- **代码**：
  - 修改 `src/fleetent/skill_registry.py`：新增 `match_all(user_input, disabled_skills=None) -> list[str]`（确定性顺序返回全部命中、**保留 disabled 过滤**；本 change 是 `match_all` 共享中间产物结构的 **owner**）；`SkillEntry` 新增 `exclusive: bool = False`（SK3 定义，经 SK2 的通用 YAML 解析能力在 `scan` 处填充）；可新增 `exclusive_hits(names) -> list[str]` 辅助判定命中集合中的互斥项。
  - 修改 `src/fleetent/agent_loop.py`：`_matched_skill_content`（行 231）注入逻辑改用 `match_all`（替换 SK1 落地的 `match` 首个命中 L2 选定），**逐候选保留** `check_skill_access` 绑定门控；命中数 > 1 且含互斥时产出询问信号（不注入 L2，返回 `(system_prompt, ask_signal | None)` 供调用方消费）；否则按确定性顺序选首个过门控的非互斥命中注入 L2。`run_sync()`（行 496）/ `run_stream()`（行 531）经此函数；`run()` 不涉及。本 change 改写 SK1 落地的 L2 单命中选定逻辑（详见 design D2）。
  - 修改 `src/fleetent/im_gateway/normalizer.py`（行 91-100）：第三处注入点改用同一共享注入辅助，保留其 `check_skill_access` 门控。
- **配置**：无新增 Settings 字段（共存策略为静态规则；`disabled_skills` 沿用 origin 现有字段）。
- **测试**：扩展 `tests/test_skill_registry.py`（`match_all` 返回全部命中且顺序确定、保留 disabled 过滤、`exclusive` 解析）与 `tests/test_agent_loop.py`（多命中时 L1 全含、L2 仅一个、绑定门控逐候选生效、单个 exclusive 独命中正常注入、命中数 > 1 含互斥触发询问信号）。LLM 调用按规范 mock，skills 目录隔离到 `tmp_path`。
- **不影响**：关键词匹配算法本身、SK2 的 frontmatter 解析、`load()` / `list_skills()` 契约、SK1 的 L1/L2 分级语义（本 change 在其上扩展多命中）、origin 已有的 `disabled_skills` 过滤与 agent 绑定门控（**保留不回归**）、热加载/安全审计（各自后续）。

## Dependencies

- **依赖 SK2（`skill-yaml-frontmatter`）**：本 change 新增的 `exclusive` 字段经 SK2 提供的通用 YAML frontmatter 解析能力在 `scan` 处填充（字段定义本身由 SK3 新增，非 SK2 承载）。
- **统一 apply / 归档序**：SK4 → SK5 → SK1 → SK3（本 change）→ SK6。SK3 排在 SK1 之后，复用 SK1 的「L1 全量清单始终注入」满足「多命中 L1 共存」，并改写 SK1 落地的 L2 单命中选定逻辑（统一到 `match_all` 共享中间产物，SK3 为该结构 owner）。`match_all` 的 disabled 过滤复用 origin 已合入的 `match` 过滤，SK6 在此基础上叠加禁用标注 + trace。

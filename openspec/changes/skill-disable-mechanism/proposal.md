## Why

docs/capabilities/skill.md「规划中」的**禁用机制**含三个子诉求：①全局禁用（对所有 agent 生效）；②agent 级禁用（只对指定 agent 生效）；③**禁用状态记录在运行日志中**，便于排查「为什么这个 Skill 没有生效」。其中前两者已被并行 change 覆盖：

- `builtin-skills`（SK 域）已落实**全局禁用开关**：`Settings.disabled_skills` 名单强制禁用 + `enabled_by_default` 默认启用态，被禁用 Skill 排除出 `match` 并记日志。
- `agent-skill-binding`（governance 域）已落实 **per-agent 白名单**（`allowed_skills` / `blocked_skills`），即「agent 级」的启用/禁用边界。

因此本 change（SK6）**只做剩余真正的 delta**，即上述两者都未覆盖的「**单个 Skill 自声明禁用**」与「**禁用判定的统一裁决 + 禁用原因写入 trace**」：

- **frontmatter `enabled: false` 单 Skill 自禁用**：Skill 作者可在自己的 frontmatter 里**显式关停**该 Skill。**诚实标注（边界 fidelity）**：`enabled` 字段是 **roadmap（docs/capabilities/skill.md）之外的新增**——skill.md「禁用机制」L81-84 只写了「管理员显式关闭（=`disabled_skills` 配置）」的全局/agent 两个维度，并**未提及** frontmatter 自禁用。本 change 引入 `enabled` 不是「落实 skill.md 既有诉求」，而是补一个 builtin-skills（管的是默认态 `enabled_by_default`）与 agent-skill-binding（管的是 per-agent 白名单）**都不覆盖**的语义缺口：**作者级、单 Skill 的硬关停**（区别于 `enabled_by_default` 的「默认要不要参与」，`enabled` 是「这个 Skill 当前是否被显式关停」的硬开关，优先级高于默认态）。
- **禁用原因写入运行日志（trace）**：当某 Skill 因任一禁用来源（自禁用 / 全局 `disabled_skills` / 默认态关闭 / per-agent 黑名单）未参与注入时，把**禁用来源**作为可查询字段写入该次运行的 trace。**这一条确属落实 skill.md L84 第③条「禁用状态记录在运行日志中，便于排查」**——该子诉求目前**无人承载**（builtin-skills 记的是即时 structlog 日志行，不是按某次运行可查询的 trace 字段），本 change 保留并补上。

> **范围划界（关键）**：本 change **不**重复实现 builtin-skills 的 `disabled_skills` 配置开关与内置类别，也**不**重复 agent-skill-binding 的 per-agent 白名单。本 change 只新增「`enabled` 自禁用字段」与「禁用来源写入 trace 的统一可观察性」，并复用前两者已建立的禁用过滤机制。

## What Changes

- 引入 **frontmatter `enabled` 字段**（布尔，缺省 `true`，经 SK2 的通用 YAML 解析能力承载入 `SkillEntry`）：`enabled: false` 的 Skill 被视为**显式禁用**，不被自动注入，**优先于** `enabled_by_default` 的默认态判定（自禁用是硬关停）。
- **禁用判定基于 SK3 的 `match_all` 候选中间产物，保留「本可命中但被禁」信息**：原 `match()` 一旦把禁用 Skill `continue` 排除，注入链就无从知道「本可命中但被禁」、也就写不出 trace。本 change**对齐 SK3 的 `match_all` 共享中间产物**——禁用判定作用在 `match_all` 返回的逐项带标注的候选上（每项带「命中 / 禁用来源」标注）：最终 `match()`/注入链**不返回禁用项**，但中间产物**保留**这些「命中但被禁用 + 来源」信息供 trace 收集。SK3 是该 `match_all` 中间产物结构的 owner，本 change 在其上叠加禁用来源标注。
- **禁用来源写入 trace**：某 Skill 因禁用未注入时，把禁用来源标识（`frontmatter_disabled` / `config_disabled` / `default_disabled` / `agent_blocked` / `audit_blocked`）写入该次运行的运行日志（trace），供「为什么这个 Skill 没生效」的事后查询。复用 `eval_logger` 既有 trace 出口，新增可选字段（默认空，向后兼容）。其中 `audit_blocked` 是 SK5（安全审计）的 **severe 拒绝**来源——对「这个 Skill 为什么没生效」的排查，被审计拒绝同样是一个原因，故纳入同一禁用来源 trace（与 SK6 自身的四个来源并列为第 5 个来源；判定归 SK5，本 change 仅识别并记录来源）。
- **不改** builtin-skills 的 `disabled_skills` 配置语义与 agent-skill-binding 的白名单语义；本 change 的 `enabled` 与禁用来源记录与二者**叠加生效**（任一来源命中即禁用），并在 design 明确叠加裁决顺序。
- `load()` 按名显式加载**不受** `enabled` 约束（与 builtin-skills 一致：禁用只约束自动匹配注入，不影响显式加载契约）。

## Capabilities

### New Capabilities
- `skill-disable-mechanism`: 单个 Skill 的通用禁用与禁用可观察性——frontmatter `enabled: false` 显式自禁用（硬关停，优先于默认态）从匹配中排除；某 Skill 因任一禁用来源未注入时，把禁用来源写入运行日志（trace）便于排查；不影响 `load` 显式加载。

### Modified Capabilities
<!-- 无既有 spec 的需求级行为变更。不改 builtin-skills 的 disabled_skills / enabled_by_default 语义，不改 agent-skill-binding 白名单语义；本次新增 enabled 自禁用字段与禁用来源 trace 写入，与既有禁用来源叠加生效。 -->

## Impact

- **代码**：
  - 修改 `src/fleetent/skill_registry.py`：`SkillEntry` 新增 `enabled: bool = True`（经 SK2 解析填充）；禁用过滤在判定 `enabled_by_default` / `disabled_skills`（builtin-skills 提供）的基础上叠加 `enabled is False` 的硬关停；禁用判定作用在 SK3 的 `match_all` 候选中间产物上——`match`/注入链最终不返回禁用项，但中间产物保留「命中但被禁用 + 来源」供注入链收集 trace。
  - 修改 `src/fleetent/agent_loop.py`：**解决禁用来源写 trace 经 `run()` 的断链（关键）**——注入只发生在 `run_sync()`（行 408-415）/ `run_stream()`（行 451-453），但 `log_run` 的正常路径调用在 `run()`（行 389）与 `run_stream()`（行 589）；`run_sync()` 不直接调 `log_run`，而是把注入构造好的 messages 委托给 `run()`，`run()` 只收 messages、**无参数承载 `disabled_skills_trace`**。修法：**给 `run()` 新增参数 `disabled_skills_trace: dict[str, str] | None = None`（默认 None 向后兼容）**，`run()` 把它透传给末尾的 `log_run`；`run_sync()` 在注入时收集被禁用 Skill 及来源，调用 `run(..., disabled_skills_trace=...)` 透传（类比现有 `agent_name` 的透传方式）。`run_stream()` 路径自带 `log_run` 调用（行 589），注入与 `log_run` 在同一函数体内，禁用来源就近收集后直接传入 `log_run` 即可，较好接。
  - 修改 `src/fleetent/eval_logger.py`：`log_run`（行 20）新增末位可选字段 `disabled_skills_trace: dict[str, str] | None = None`（默认 None 向后兼容、None 不写入 entry）承载本次被禁用 Skill 及其来源。
- **配置**：无新增 Settings 字段（`enabled` 来自 frontmatter；`disabled_skills` 配置归 builtin-skills，不在此重复）。
- **依赖**：不引入新依赖（沿用 SK2 的 `pyyaml`、既有 structlog / eval_logger）。
- **测试**：扩展 `tests/test_skill_registry.py`（`enabled: false` 解析与硬关停优先级）、`tests/test_agent_loop.py`（自禁用 Skill 不注入且禁用来源写入 trace；多禁用来源叠加时来源记录正确）；`tests/test_eval_logger.py`（新字段默认 None 向后兼容、非 None 写入）。skills 目录隔离 `tmp_path`，LLM 调用 mock。
- **不影响**：builtin-skills 的 `disabled_skills` / `enabled_by_default` / 内置类别行为、agent-skill-binding 的白名单行为、关键词匹配算法、SK2 解析、`load`/`list_skills` 契约、热加载/安全审计/渐进式加载/多 Skill 共存（各自后续）。

## Dependencies

- **依赖 SK2（`skill-yaml-frontmatter`）**：`enabled` 字段经 SK2 的通用 YAML 解析能力承载入 `SkillEntry`。
- **统一 apply / 归档序**：SK4 → SK5 → SK1 → SK3 → SK6（本 change，最后）。SK6 排在 SK3 之后，**复用 SK3 owner 的 `match_all` 候选中间产物**叠加禁用来源标注（保留「命中但被禁」供 trace）；排在 SK1 之后，禁用作用于 L1/L2 注入基线。
- **与 `builtin-skills` 叠加（不重复）**：复用其禁用过滤骨架与 `disabled_skills` / `enabled_by_default` 语义；本 change 仅叠加 `enabled` 硬关停与禁用来源 trace。
- **与 `agent-skill-binding` 叠加（不重复）**：per-agent 白/黑名单由其负责；本 change 在禁用来源 trace 中识别 `agent_blocked` 来源以统一可观察性，但不重新实现白名单判定。
- **与 `skill-security-audit`（SK5）叠加（不重复）**：SK5 的审计 severe 拒绝由其负责；本 change 在禁用来源 trace 中识别 `audit_blocked` 来源以统一可观察性，把「被审计拒绝」纳入同一「为什么这个 Skill 没生效」trace，但不重新实现审计判定。

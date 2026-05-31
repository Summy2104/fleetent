## Context

skill.md「禁用机制」列三条：①全局禁用（对所有 agent 生效）；②agent 级禁用（只对指定 agent 生效）；③禁用状态记录在运行日志中，便于排查「为什么这个 Skill 没有生效」。

两个并行 change 已分担其中两条：

- `builtin-skills`：`Settings.disabled_skills: list[str]` 强制全局禁用 + `enabled_by_default` 默认启用态；被禁用 Skill 从 `match` 排除、记日志；`load` 不受约束。**= 第①条「全局禁用」。**
- `agent-skill-binding`：agent 定义 `allowed_skills` / `blocked_skills`（fnmatch），注入链按当前 agent 过滤；默认 opt-in。**= 第②条「agent 级禁用」。**

**剩余 delta（本 change 的真正范围）：**
- skill.md 明文列出但二者都没单独承载的「**禁用状态记录在运行日志中**」（第③条）——builtin-skills 记的是即时的结构化 warning/info 日志，**不是写入该次运行的 trace 供事后按运行查询**；本 change 补这条可观察性。
- 一个 builtin-skills 的 `enabled_by_default`（默认态）与 agent-skill-binding 的白名单都**未覆盖**的语义：Skill 作者**显式硬关停单个 Skill** 的 `enabled: false` 开关。`enabled_by_default` 语义是「这个 Skill 默认要不要参与匹配」（可被场景启用），而 `enabled: false` 是「此 Skill 当前被关停」的硬开关，优先级最高。二者并存：`enabled_by_default=true` 但 `enabled=false` → 仍禁用。

> **结论（边界）**：SK6 已被 builtin-skills + agent-skill-binding **大部分覆盖**。本 change 收窄到两块真正的 delta：`enabled` 自禁用硬开关 + 禁用来源写入 trace 的统一可观察性，复用而**不重复**前两者的禁用过滤与白名单。

error-classification（AR5）已确立「把可查询字段写入 trace（`log_run` 新增可选 kw、默认 None 向后兼容）」的范式，本 change 复用同款方式写禁用来源。

**统一 apply / 归档序 + 与 SK3 `match_all` 的协调点**（Track G 全局决策）：本轨顺序 SK4 → SK5 → SK1 → SK3 → SK6（本 change，最后）。`match_all` 共享中间产物结构的 owner 是 SK3；SK6 在 SK3 已落地的 `match_all` 候选（逐项带「命中 / exclusive」标注）上**叠加禁用来源标注**。本 capability 为纯 ADDED。

**注入链与 `log_run` 的事实（关键）**：注入只发生在 `run_sync()`（行 408-415）与 `run_stream()`（行 451-453）；`run()`（行 234）只收预构建 messages、不做 Skill 注入。`log_run` 的正常路径调用在 `run()`（行 389）与 `run_stream()`（行 589）。`run_sync()` 不直接调 `log_run`——它在注入后把 messages 委托给 `run()`，由 `run()` 调 `log_run`。因此 `run_sync()` 路径上「注入时收集的禁用来源」与「`run()` 里的 `log_run` 调用」之间**隔着一次函数委托**，而 `run()` 当前**没有参数承载禁用来源**——这是必须解决的断链（见 D3a）。

约束（CLAUDE.md）：禁止 AI 框架；禁止 ORM；禁止全局可变状态；新模块结构 import → 常量 → 数据类 → 函数；mypy strict；行长 100；TDD Hard Gate；测试 skills 目录隔离 tmp_path，LLM 调用 mock。

## Goals / Non-Goals

**Goals:**
- frontmatter `enabled: false` 显式禁用单个 Skill，硬关停、优先于 `enabled_by_default` 默认态。
- 某 Skill 因任一禁用来源未注入时，把禁用来源写入该次运行的 trace。
- 与 builtin-skills 的 `disabled_skills` / `enabled_by_default` 及 agent-skill-binding 的白名单**叠加生效**（任一来源命中即禁用），裁决顺序明确。
- `load()` 显式加载不受 `enabled` 约束。

**Non-Goals（明确不做，避免与并行 change 重叠）:**
- **不**实现 builtin-skills 的内置 Skill 类别与 `disabled_skills` 配置开关（属 builtin-skills）。
- **不**实现 agent-skill-binding 的 per-agent 白名单 / 黑名单判定逻辑（属 agent-skill-binding）。
- 不实现运行期动态禁用 API/CLI（禁用经 frontmatter `enabled` 静态声明；运行期开关如需要属后续）。
- 不实现热加载、安全审计、渐进式加载、多 Skill 共存。

## Decisions

### D1：新增 frontmatter `enabled` 硬关停字段，优先于默认态
`SkillEntry` 新增 `enabled: bool = True`，由 SK2 的 frontmatter 解析在 `scan` 处填充（`bool(frontmatter.get("enabled", True))`）。`match` 的禁用过滤在 builtin-skills 已有判定基础上**叠加**：`enabled is False` → 直接排除，**不看** `enabled_by_default`、不看是否被场景启用——自禁用是硬关停。
**为何**：`enabled_by_default`（默认态，可被启用流程开启）与 `enabled`（当前是否被关停）是两种正交语义；作者需要一个「无论默认态如何、先把这个 Skill 关掉」的硬开关。优先级最高保证「关停」可靠。
**Alternatives**：①复用 `enabled_by_default=false` 表达禁用——被否，语义混淆（默认态 ≠ 硬关停），且 builtin-skills 已把 `enabled_by_default` 定义为「默认启用态」，再塞「硬关停」语义会冲突；②另建配置名单——被否，那是 builtin-skills 的 `disabled_skills`，本 change 不重复，只补 frontmatter 自声明这一缺口。

### D2：禁用裁决基于 SK3 `match_all` 候选中间产物（保留「本可命中但被禁」）
**问题（review Major）**：原 `match()` 在遍历中一旦遇禁用 Skill 即 `continue` 排除，注入链就**无从知道**「这个 Skill 本可关键词命中、只是被禁」，也就写不出「为什么没生效」的 trace。
**修法**：禁用判定**不在 `match()` 里直接 `continue` 丢弃**，而是作用在 **SK3 owner 的 `match_all` 候选中间产物**上——`match_all` 对每个关键词命中的 Skill 产出一个带标注的候选项（至少含「是否命中」「禁用来源（若被禁）」「exclusive」）。最终对外的 `match()`/注入链**不返回被禁用的候选**（行为对外不变：禁用 Skill 不注入），但中间产物**保留**「命中但被禁用 + 来源」的项，供注入链收集进 trace。SK3 是该候选结构的 owner，本 change 在其标注上叠加「禁用来源」一维。

某 Skill 对当前请求是否被禁用 = 以下任一命中即禁用，并在候选标注里记录命中来源（用于 trace）：
1. `enabled is False` → 来源 `frontmatter_disabled`（本 change 新增判定）
2. 命中 `disabled_skills` 配置名单 → 来源 `config_disabled`（builtin-skills 提供判定，本 change 仅识别来源）
3. `enabled_by_default is False` 且未被显式启用 → 来源 `default_disabled`（builtin-skills 提供判定）
4. 未通过 per-agent 白名单 / 命中黑名单 → 来源 `agent_blocked`（agent-skill-binding 提供判定）
5. 被 SK5 安全审计 severe 拒绝 → 来源 `audit_blocked`（skill-security-audit / SK5 提供判定，本 change 仅识别来源）
本 change **只新增第 1 条的判定**，第 2-5 条复用并行 change 的既有判定；统一在 `match_all` 候选标注里汇总「被禁用 Skill → 来源」，注入链据此写 trace。第 5 条 `audit_blocked` 是协调点①：对「这个 Skill 为什么没生效」的排查，被 SK5 审计拒绝与配置禁用同样是「没生效」的原因，故纳入同一禁用来源 trace。
**为何**：禁用是「任一来源命中即禁用」的 OR 叠加；候选中间产物保留禁用项才能让 trace 回答「本可命中但凭什么被禁」。不重新实现 2-4 条避免与并行 change 重叠。
**Alternatives**：①仍在 `match()` 里 `continue` 丢弃禁用项——被否，丢弃后注入链拿不到「本可命中」信息，trace 无从写；②把全部禁用判定集中重写到本 change——被否，与 builtin-skills / agent-skill-binding 重叠，违反范围划界。

### D3：禁用来源写入 trace（复用 AR5 范式）
`eval_logger.log_run`（行 20）新增末位可选字段 `disabled_skills_trace: dict[str, str] | None = None`（键=Skill 名、值=禁用来源标识，取值集合 `frontmatter_disabled` / `config_disabled` / `default_disabled` / `agent_blocked` / `audit_blocked`；默认 None 向后兼容，None 不写入 entry）。注入链在「跳过被 `match_all` 候选标注为禁用（含被 SK5 审计 `audit_blocked`）、但本可命中的 Skill」时收集 `{skill_name: 来源}`，运行结束经 `log_run` 写入。
**为何**：落实 skill.md 第③条「禁用状态记录在运行日志中，便于排查」；复用 AR5 已验证的「log_run 新增可选 kw、默认 None 向后兼容」，改动最小、不破坏既有 trace 调用。
**Alternatives**：①只记即时 structlog（builtin-skills 已做）——被否，那是「发生时的日志行」，不是「按某次运行可查询的 trace 字段」，无法回答「**这次运行**为什么这个 Skill 没生效」；②单建禁用审计表——被否，trace 已是 append-only 运行轨迹的单一出口，复用即可。

### D3a：解决 `run_sync()` 经 `run()` 委托的 trace 断链 —— 给 `run()` 新增透传参数（review Blocker）
**问题**：禁用来源在 `run_sync()`（行 408-415）注入时收集，但 `run_sync()` 不直接调 `log_run`——它把注入好的 messages 委托给 `run()`，由 `run()`（行 389）调 `log_run`。`run()` 当前签名**只收 messages 等参数、没有承载禁用来源的入口**，收集到的 `disabled_skills_trace` 无法传到 `run()` 内的 `log_run`。
**修法**：给 `run()` **新增参数 `disabled_skills_trace: dict[str, str] | None = None`（默认 None，向后兼容现有所有 `run()` 调用方）**；`run()` 把它原样透传给末尾的 `log_run(..., disabled_skills_trace=disabled_skills_trace)`。`run_sync()` 在注入时收集被禁用 Skill 及来源，调用 `run(messages, ..., disabled_skills_trace=collected)` 透传——**完全类比现有 `agent_name` 的透传范式**（`agent_name` 同样在上层确定、经 `run()` 参数传到 `log_run`）。
**`run_stream()` 路径**：注入（行 451-453）与 `log_run` 调用（行 589）**在同一函数体内**，无委托断链——禁用来源就近收集为局部变量、运行结束直接传入该处 `log_run` 即可，较好接，不需要新增透传参数。
**为何**：默认 None 的新增参数对现有 `run()`/`run_stream` 调用方零影响（向后兼容）；透传而非「在 `run()` 内重新计算禁用」保持了「注入逻辑在 `run_sync`/`run_stream`、`run()` 只跑循环」的既有分层。
**Alternatives**：①把 Skill 注入整体下沉进 `run()`——被否，blast radius 大且改变现有「`run()` 收预构建 messages」契约，影响所有调用方（im_gateway 等）；②`run_sync()` 自己再调一次 `log_run`——被否，会产生重复 trace 记录，且 `run_sync` 拿不到 `run()` 内的 usage/stop_reason 等运行结果。

### D4：`load()` 不受 `enabled` 约束
`load(name)` 仍按名读 SKILL.md 原文，不因 `enabled is False` 拒绝。
**为何**：与 builtin-skills「禁用只约束自动匹配，不影响显式加载契约」一致；显式加载常用于排查 / 管理，禁用不应阻断。
**Alternatives**：禁用即 `load` 失败——被否，破坏既有 `load` 契约且妨碍排查。

### D5：显式定义单一 `injectable` 谓词，L1 / L2 与三个注入点都查同一谓词（协调点②，全轨收敛结论）
全轨把「一个 Skill 当前是否可被自动注入」收敛为**单一谓词**，作为唯一裁决源：

```
injectable(skill, request) =
    命中(skill, request)              # 关键词命中（SK3 候选）
  ∧ skill.enabled                     # frontmatter 非硬关停（SK6，本 change）
  ∧ skill.name ∉ disabled_skills      # 非全局配置禁用（builtin-skills）
  ∧ ¬default_disabled(skill)          # 非「默认态关闭且未被显式启用」（builtin-skills）
  ∧ passes_agent_binding(skill)       # 过 per-agent 白名单 / 不在黑名单（agent-skill-binding）
  ∧ ¬audit_blocked(skill)             # 非 SK5 审计 severe 拒绝（skill-security-audit）
```

`injectable` 为假 ⇔ 上述某项失败，该失败项即对应一个禁用来源（D2/D3 的五来源集合），写入 `disabled_skills_trace`。

- **单一裁决源**：SK3 owner 的 `match_all` 候选结构累积四方信息——命中(SK3) + `exclusive`(SK3) + 禁用来源(SK6：`frontmatter_disabled` / 复用 `config_disabled` / `default_disabled` / `agent_blocked`) + `audit_blocked`(SK5)，共同构成 `injectable` 这个**单一谓词**。注入裁决不得在 `match_all` 之外另起一套判定。
- **L1(SK1) 与 L2 都查同一谓词**：L1（SK1 的注入基线，含轻量/前置注入）与 L2（关键词匹配注入）**MUST** 通过同一个 `injectable` 谓词决定某 Skill 是否注入。这样**同时解掉 L1 注入被禁 / 被审计 Skill 的绕过**——若只在 L2 过滤，L1 仍可能注入一个已 `enabled: false` 或被 SK5 拒绝的 Skill。
- **三个注入点都经它**：当前三个注入点（`run_sync()`、`run_stream()`，以及 `im_gateway/normalizer.py` 的 IM 路径）**MUST** 都经 `injectable` 共享函数裁决，不得各自实现一份过滤。

**为何**：单一谓词 + 单一裁决源消除「不同注入点对同一 Skill 给出不同启用结论」的不一致；把 SK1/SK5/SK6 与 builtin-skills/agent-skill-binding 的判定收拢到一处，禁用来源 trace 也自然只在这一处收集。
**Alternatives**：每个注入点各写一份过滤——被否，必然漂移（L1 绕过即是例证），且禁用来源 trace 会重复/遗漏。

### D6：normalizer IM 路径的禁用 trace 当前不写（已知 gap，与「注入收敛为单一共享函数」一并解决）（minor）
**事实**：D3a 的 trace 透传覆盖的是 `run_sync()` 经 `run()` 委托 + `run_stream()` 两条路径；`im_gateway/normalizer.py` 的 IM 注入路径**当前不会写 `disabled_skills_trace`**——透传链未覆盖 normalizer。
**处置**：作为**已知 gap 显式标注**，不在本 change 单独打补丁，而是与 D5「三个注入点收敛为单一共享 `injectable` 函数」**一并解决**——当 normalizer 改为经同一共享注入函数（内含禁用来源收集）后，IM 路径的禁用 trace 随之自动覆盖。
**诚实标注**：`enabled` 自禁用（D1）是 roadmap（docs/capabilities/skill.md）之外的新增，proposal/design 已诚实标注，**保持**不变。

## Risks / Trade-offs

- [与并行 change 的合入顺序耦合：本 change 复用 builtin-skills / agent-skill-binding 的判定] → 本 change 只硬依赖 SK2；第 2-4 条来源识别在对应 change 未合入时降级为「该来源恒不命中」，`enabled` 自禁用（第 1 条）与 trace 写入独立可用；design 标注协调点，叠加判定按「能拿到的来源」工作。
- [`enabled` 与 `enabled_by_default` 语义易被混淆] → spec 与 design 明确二字段正交：`enabled` 是硬关停（优先），`enabled_by_default` 是默认态（builtin-skills）；测试覆盖「`enabled_by_default=true` + `enabled=false` → 仍禁用」。
- [trace 字段膨胀] → `disabled_skills_trace` 仅在确有 Skill 被禁用且本可命中时写入；正常无禁用的运行不写该字段（默认 None）。
- [范围被误解为重复 builtin-skills/agent-skill-binding] → proposal 与本 design 显式划界，spec 的需求只描述 `enabled` 自禁用与禁用来源 trace，不含配置名单/白名单的判定需求。

## Open Questions

- 禁用来源标识的最终取值集合（`frontmatter_disabled` / `config_disabled` / `default_disabled` / `agent_blocked` / `audit_blocked`）与 trace 字段结构——实现首步结合 builtin-skills / agent-skill-binding / skill-security-audit（SK5）已落地的判定接口确定，确保来源可被各 change 统一填充。（trace 的写入路径已由 D3/D3a 定死：`log_run` 新增 `disabled_skills_trace` 字段，`run()` 新增同名透传参数，`run_sync` 透传、`run_stream` 就近传入；IM 路径见 D6 已知 gap，随 D5 注入收敛一并覆盖。）
- 是否需要运行期（非 frontmatter）动态禁用单个 Skill 的开关——本 change 不做（禁用经 frontmatter 静态声明 + builtin-skills 的配置名单），如运维需要运行期单 Skill 开关可后续在热加载之上扩展。

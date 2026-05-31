## Context

`agent_loop` 当前的 Skill 注入链：`run_sync`（行 280-287）与 `run_stream`（行 319-321）调用 `match_skill(user_input)` 拿到首个命中的 Skill 名，再 `load_skill(name)` 把 SKILL.md 全文拼进 system prompt。`match`（`skill_registry` 行 27-38）对 `_index` 中**全体**已扫描 Skill 做关键词匹配，与「当前是哪个 agent」无关。

工具维度早已有 per-agent 访问控制的成熟先例：`run()`（行 141）接收 `allowed_tools: list[str] | None`，用 `agent_policy.check_tool_access`（`fnmatch` 白名单，行 4-5）过滤 `get_schemas()` 暴露给当前 agent 的工具（agent_loop 行 163-164）。本 change 是该机制在 Skill 维度的类比。

agent 定义存于 `agent_store.Agent`（行 13-19：`id` / `name` / `system_prompt` / `allowed_tools`）及 `agents` 表（行 122-128）。`allowed_tools` 已是 JSON 列入库的先例——`allowed_skills` / `blocked_skills` 将沿用同款存储形态。**注意 `agent_store` 属 governance 域（张亮），跨域。**

依赖 **SK2（`skill-yaml-frontmatter`）**：SK2 用标准 YAML 解析 frontmatter 并把索引扩为结构化元数据，确保 Skill 名（frontmatter `name`）作为白名单匹配键稳定可靠。本 change 排其后。

约束（CLAUDE.md）：禁止 AI 框架；禁止全局可变状态（白/黑名单经参数注入，不落模块级可变态）；fnmatch 复用既有 `agent_policy` 风格；新模块结构 import → 常量 → 数据类 → 函数；mypy strict；行长 100；TDD Hard Gate；测试隔离（skills 目录 `tmp_path`、LLM mock）。

## Goals / Non-Goals

**Goals:**
- 为 Skill 注入引入 per-agent 白名单 `allowed_skills`（fnmatch）+ 可选 `blocked_skills`，语义与工具的 `allowed_tools` 一致。
- `agent_loop` 的 `match→load` 注入链按当前 agent 的白/黑名单过滤命中的 Skill。
- `run()` / `run_stream()` 增加 `allowed_skills` / `blocked_skills` 参数透传（类比 `allowed_tools`）。
- 默认 posture = opt-in：未声明 `allowed_skills` 时不注入任何 Skill。
- 复用 `agent_policy` 的 fnmatch 判定，保持单一实现风格。

**Non-Goals:**
- 不做内置 Skill 类别 / 全局禁用开关（并行的 `builtin-skills` change）。
- 不改关键词匹配算法本身（`skill_registry.match` 的实现不动）。
- 不引入新依赖。
- 不实现 Skill 的渐进式加载 / 热加载 / 安全审计（各自后续）。
- 不强行实现「默认 agent 经配置声明 allowed_skills」的缓解（列为 Open Question）。

## Decisions

### D1：per-agent Skill 白名单，类比 allowed_tools
agent 定义新增两个可选字段，语义对齐工具维度：
- `allowed_skills: list[str] | None`：Skill 名 / fnmatch 模式白名单。`None` = 未声明（触发 opt-in 默认，见 D3）；`[]` = 显式声明「不允许任何 Skill」。
- `blocked_skills: list[str] | None`：在白名单命中后再排除的 fnmatch 模式（可选；缺省 `None` 视为无排除）。

判定顺序：命中的 Skill 名先经 `allowed_skills` fnmatch 判定，命中后再经 `blocked_skills` fnmatch 判定排除，二者皆通过才注入。
**为何**：与 `allowed_tools` / `check_tool_access` 同款 fnmatch 语义，运维心智一致；白名单优先、黑名单做精排是访问控制惯例。
**Alternatives**：①只做白名单不做黑名单——被否，黑名单允许「允许 hr-* 但排除 hr-payroll」这类常见精排，成本低；②用正则而非 fnmatch——被否，与既有工具白名单风格割裂。

### D2：在注入链上加过滤层，不改 match 算法
`skill_registry.match()` 仍对全体索引做关键词匹配，返回命中的 Skill 名；`agent_loop` 在 `match` 之后、`load` 之前插入一道按白/黑名单的过滤：命中的 Skill 名未通过白名单（或被黑名单排除）则**不 load、不注入**。fnmatch 判定复用 `agent_policy` 风格的纯函数（白名单判定可直接复用 `check_tool_access`；黑名单判定为其镜像）。
**为何**：注入链是 Skill 与 agent 唯一交汇点，过滤放此处 blast radius 最小；不动 `match` 算法符合 Non-Goals 与「不改关键词匹配」。
**Alternatives**：①把 agent 上下文传进 `skill_registry.match` 内部过滤——被否，让 registry 感知 agent 概念是跨层耦合，registry 应只管「索引 + 匹配」；②注入后再在 prompt 层裁剪——被否，已 load 全文再丢弃浪费且语义混乱。

### D3：默认 posture = opt-in 显式绑定（行为变更）
当 `allowed_skills is None`（agent 未声明）时，注入链**不注入任何 Skill**（等价于空白名单）。这是相对**现状（全局注入命中的 Skill）的行为变更**：现状任何命中 Skill 都注入，opt-in 后必须显式声明 `allowed_skills` 才会注入。
**为何**：多 agent 治理要求默认最严格——「未明确允许即不注入」避免 Skill 跨 agent 领域泄漏，与「数据/能力边界清晰」一致。显式绑定让 Skill 的可见性可审计。
**Alternatives**：①默认 opt-out（未声明 = 全局注入，沿用现状）——被否，与多 agent 边界治理诉求相悖，且白名单成了「可选增强」而非「访问控制」；②默认注入但 `blocked_skills` 排除——被否，黑名单驱动的默认开放同样不满足最严格 posture。

### D4：run()/run_stream() 参数透传，位置类比 allowed_tools
`run()` / `run_stream()` 新增 `allowed_skills: list[str] | None = None`、`blocked_skills: list[str] | None = None`，置于 `allowed_tools` 参数邻位，由上游（绑定了 agent 的调用方）从 agent 定义读出后透传。
**为何**：与 `allowed_tools` 同一透传路径，调用方心智一致；参数化注入符合「禁止全局可变状态、经参数注入」。
**注**：`run_sync` 内部构造注入链，需同样接入过滤（默认无 agent 绑定 → opt-in 不注入，见 D5）。

### D5：默认 / 未绑定路径（CLI run_sync）的行为变更与缓解
`run_sync` 是 CLI 入口，当前无 agent 绑定，直接对全局索引 `match→load` 注入。opt-in（D3）下，无 agent 绑定 = `allowed_skills is None` = **不注入任何 Skill**——这是 CLI 用户可感知的行为变更（此前会注入命中的 Skill）。
缓解方向：让「默认 agent」可经配置（`Settings.default_agent_name` 已存在，`agent_store.get_default_agent()` 可取）声明 `allowed_skills`，使 CLI 走默认 agent 的白名单而非空。
**本次定位**：列为 **Open Question / 设计点，不强行实现**——避免与 governance 域的默认 agent 配置语义抢跑。本 change 先把过滤层与参数透传做对，CLI 默认 opt-in 不注入作为已知行为变更在 proposal/design 明示。
**为何**：行为变更必须显式记录；缓解涉及默认 agent 配置语义（governance 域），不宜在 Skill 侧 change 内单方面定死。

## 跨域协调点

- **`allowed_skills` / `blocked_skills` 字段加在 agent 定义（`agent_store`，属 governance 域 / 张亮）**。需协同添加：
  - `agent_store.Agent` 数据类新增两字段（沿用 `allowed_tools` 的 `list[str]` + JSON 入库形态；黑名单可空）。
  - `agents` 表新增列与 `create_agent` / `get_by_name` / `get_agent_for_user` / `get_agent_for_channel` 的读写路径同步。
  - 字段命名 / 缺省语义（`None` = opt-in 不注入）需与张亮就 governance 域的 agent 定义约定一致后落库。
- 本 change 的职责边界：**Skill 侧过滤逻辑 + `run()`/`run_stream()` 参数透传**；agent 字段落库为协同项，过滤层先按「调用方传入白/黑名单」工作，字段就绪后由上游读出透传。

## Risks / Trade-offs

- [opt-in 默认不注入是行为变更，可能让现状依赖「全局注入」的 CLI / 未绑定路径突然不再注入 Skill] → proposal/design 明示为已知行为变更；CLI 缓解列 Open Question；用例覆盖「未声明白名单 → 不注入」。
- [agent 字段属 governance 域，跨域改动需协调，存在落库时序风险] → 本 change 过滤层不依赖字段落库即可独立工作（按传入参数过滤），字段为上游协同项；design 标注跨域协调点。
- [fnmatch 白名单对 Skill 名的匹配口径与工具名不同（Skill 名可能含连字符等）] → 复用 `agent_policy` 同款 fnmatch，对名称形态无特殊假设；用例覆盖含连字符的 Skill 名匹配。
- [`run()` 与 `run_stream()` / `run_sync` 注入链各自独立，过滤逻辑可能漂移] → 过滤判定收敛为 `agent_policy` 风格的共享纯函数，三处仅调用；用例覆盖各路径。
- [黑名单在空/None 时的语义易混淆] → 明确 `blocked_skills is None` 或 `[]` 均视为无排除；用例覆盖。

## Open Questions

- 「默认 agent 经配置声明 `allowed_skills`」作为 CLI opt-in 行为变更的缓解——是否本波接入、字段语义如何与 governance 域默认 agent 配置对齐，待与张亮协调后定，本次不实现。
- `allowed_skills` 为 fnmatch 模式时，是否需要与 SK2 的 frontmatter `tags`/`platforms` 维度联动（如「按 tag 而非 Skill 名授权」）——本次仅做 Skill 名 / fnmatch 模式，tag 维度授权列后续。
- agent 字段的最终命名与缺省值由 governance 域 owner（张亮）拍板；本 change 先以 `allowed_skills` / `blocked_skills` 占位。

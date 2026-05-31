## Context

`agent_loop` 的 Skill 注入链当前在两处入口构造 messages 时实现（`run_sync()` 行 408-415、`run_stream()` 行 451-453），形态一致：`scan_skills()`（仅 run_sync）→ `matched = match_skill(user_input)` → `if matched: full_system = f"{full_system}\n\n{load_skill(matched)}"`。`run()`（行 234）接收预构建好的 messages、**不做任何 Skill 注入**——注入只在上述两个入口。即：未命中不注入任何 Skill 信息，命中则把 `load()` 返回的整篇 SKILL.md 拼到 system prompt 末尾。

**统一 apply / 归档序**（Track G 全局决策）：本轨 5 个 change 按 SK4（热加载）→ SK5（注入审计）→ SK1（本 change）→ SK3（多 Skill 共存）→ SK6（禁用机制）的顺序实施与归档。`match_all` 共享中间产物结构的 owner 是 SK3；SK1 仅建立 L1/L2 注入基线（始终注入 L1、命中注入单个 L2），SK3 在其上扩展 `match_all` 并改写 L2 选定逻辑（见 SK3 design），SK6 再叠加禁用标注与 trace。本 capability 均为纯 ADDED，无既有 spec 的 MODIFIED。

`skill_registry` 现有对外面：`match()`（首次命中即返回 Skill 名）、`load(name)`（读整篇 SKILL.md）、`list_skills()`（返回 `[{"name", "description"}]`）。SK2 已把索引升级为 `dict[str, SkillEntry]`，`SkillEntry` 含 `description` / `path` / `tags` / `platforms` / `version` / `enabled_by_default`，是 L1 摘要的现成数据来源。

docs/capabilities/skill.md 定义三级：L1（始终加载，全量名称+一句话描述，让 AI 知道有哪些 Skill）、L2（命中时加载完整 SKILL.md）、L3（SKILL.md 引用的附属文件，AI 经文件读取工具按需获取）。

约束（CLAUDE.md）：禁止 AI 框架；禁止全局可变状态（skills 目录路径已可注入）；新模块结构 import → 常量 → 数据类 → 函数；mypy strict；行长 100；TDD Hard Gate；测试 skills 目录隔离到 tmp_path，LLM 调用 mock。

## Goals / Non-Goals

**Goals:**
- skill_registry 产出 L1 全量「名称+描述」清单，供注入链始终拼入 system prompt。
- 注入链改为「L1 始终 + L2 命中」分级：未命中也注入 L1，命中再追加该 Skill 的 L2 全文。
- 明确 L3 边界：附属资源不随 L2 注入，由 AI 经既有文件读取工具按需获取。
- 保持 `match` / `load` / `list_skills` 既有契约不变。

**Non-Goals:**
- 不改关键词匹配算法（漏召问题由 L1 让 AI 可主动援引来缓解，不在本 change 重写匹配）。
- 不实现 aux LLM 路由（skill.md「规划中」的 L1 摘要 → LLM 路由命中，是独立后续）。
- 不实现多 Skill 共存的 L2 策略（多命中只注入首个 L2 仍成立；完整多 Skill 处理是 SK3）。
- 不实现新的 L3 资源读取工具（依赖既有文件读取工具，本 change 只定义 L3 不进 prompt）。
- 不实现热加载、安全审计、禁用机制（各自后续）。

## Decisions

### D1：新增 `l1_summary()` 产出 L1 清单，与 match/load 职责分离
`skill_registry` 新增纯函数 `l1_summary() -> str`：遍历 `_index`，把每个 `SkillEntry` 渲染为一行「`- {name}: {description}`」，拼成一段清单文本（空索引返回空串）。注入链始终调用它拼入 system prompt。
**为何**：L1（全量摘要，始终注入）与 L2（命中全文，按需注入）是两种不同粒度，分由 `l1_summary()` 与 `match`+`load` 承载，职责清晰、各自可单测；复用既有 `_index` 数据，不新增索引结构。
**Alternatives**：①复用 `list_skills()` 在 agent_loop 里自行拼字符串——被否，渲染逻辑散到调用方、难单测，且 `list_skills` 返回结构化列表其契约不应被注入格式绑架；②把 L1 渲染塞进 `match()` 返回——被否，`match` 是命中判定，混入全量摘要违背单一职责。

### D2：注入链改为「L1 始终 + L2 命中」分级
`run_sync()`（行 408-415）/ `run_stream()`（行 451-453）注入链改为：先 `full_system = f"{full_system}\n\n{l1_summary()}"`（清单非空时），再 `matched = match_skill(...)`；命中则 `full_system = f"{full_system}\n\n{load_skill(matched)}"`。L1 段与 L2 段以清晰分隔拼接。`run()` 不涉及（只收预构建 messages）。
**为何**：直接落实 skill.md 的分级定义——AI 始终看得到「有哪些 Skill」，命中才付出全文 token 成本；可观察行为相对现状的增量是「未命中时多了 L1 清单、命中时在 L2 全文前多了 L1 清单」，符合渐进式加载目标。
**Alternatives**：把 L1 作为 system_prompt 的固定前缀在 `scan` 后一次性构建缓存——被否，索引会因热加载（后续 change）变化，固定前缀会过期；动态拼接每次请求读最新 `_index`，与 `scan` 每次 CLI 调用 / lifespan 启动的现状一致（见 Open Questions）。

### D3：L3 边界 = 不随注入进入 prompt
L3（SKILL.md 内 `references/` 等引用的附属文件）明确**不**由注入链读取拼入。AI 若需要，经既有文件读取工具按需获取。本 change 仅以 spec 钉死「L2 注入不包含 L3 附属文件内容」这一边界。
**为何**：L3 延迟加载的全部价值就是「不为可能用不到的资料预付 token」；把边界写进 spec 可被「附属文件内容不出现在 prompt」这一端到端断言验证。
**Alternatives**：随 L2 一并注入引用文件——被否，正是渐进式加载要消除的 context 浪费。

## Risks / Trade-offs

- [L1 清单本身也消耗 token，Skill 数量大时清单不小] → L1 仅含「名称+一句话描述」，单条开销远小于一篇全文；若未来规模过大，可在不改本 capability 契约的前提下引入 LLM 路由（skill.md 规划中）替代全量清单注入，本次接受全量清单。
- [动态每请求拼接 L1 与「固定前缀」相比有重复拼接成本] → 拼接是纯字符串操作、开销可忽略；换取热加载后清单不过期的正确性，权衡取动态拼接（见 Open Questions）。
- [L2 仍保持首次命中只注入一个] → 与现状一致，多 Skill 的 L2 策略属 SK3，本 change 不扩大范围。
- [L3 不注入可能让 AI 拿不到关键附属信息] → 这是渐进式加载的预期：附属资料由 AI 显式按需读取，避免无差别预载；SKILL.md 正文应自带「需要时去读哪个文件」的指引。

## Open Questions

- L1 清单注入方式：作为 system_prompt 固定前缀还是每次请求动态拼接？（skill.md 已列为待决）本 change 取动态拼接最小实现以兼容后续热加载；若 token 评估显示固定前缀更优，可在热加载 change 落地后重新评估。
- L1 → aux LLM 路由（用 L1 摘要让 LLM 规划命中）是否纳入：本 change 不实现，留作独立后续；当前仅靠关键词匹配决定 L2，L1 只负责让 AI「可见」。

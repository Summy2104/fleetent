## Context

`agent_loop` 的 Skill 注入当前经 `_matched_skill_content(user_input, allowed_skills, blocked_skills)`（行 231）封装：`matched = match_skill(user_input)` 命中后，用 `check_skill_access(matched, allowed_skills, blocked_skills)` 做 **agent skill 绑定门控**（opt-in：`allowed_skills is None` 时不注入），通过才 `load_skill(matched)`。该函数由 `run_sync()`（行 479，调用在行 496）与 `run_stream()`（行 505，调用在行 531）共用。**此外存在第三个注入点**：`im_gateway/normalizer.py`（行 81-82）独立内联了同一套 `match`+`check_skill_access`+`load` 逻辑，注入 IM 渠道消息。`run()`（行 299）接收预构建好的 messages、**不做任何 Skill 注入**。即：未命中不注入任何 Skill 信息，命中且过门控则把 `load()` 返回的整篇 SKILL.md 拼到 system prompt 末尾。

**统一 apply / 归档序**（Track G 全局决策）：本轨 5 个 change 按 SK4（热加载）→ SK5（注入审计）→ SK1（本 change）→ SK3（多 Skill 共存）→ SK6（禁用机制）的顺序实施与归档。`match_all` 共享中间产物结构的 owner 是 SK3；SK1 仅建立 L1/L2 注入基线（始终注入按 agent 过滤的 L1、命中注入单个 L2），SK3 在其上扩展 `match_all` 并改写 L2 选定逻辑（见 SK3 design），SK6 再叠加禁用标注与 trace。本 capability 均为纯 ADDED，无既有 spec 的 MODIFIED。

`skill_registry` 现有对外面：`match(user_input, disabled_skills=None)`（行 94，首次命中即返回 Skill 名，已带 `disabled_skills` 过滤）、`load(name)`（读整篇 SKILL.md）、`list_skills()`（返回 `[{"name", "description"}]`）；`scan()`（行 38，扫 builtin + 用户两个源）。SK2 已把索引升级为 `dict[str, SkillEntry]`，`SkillEntry` 含 `description` / `path` / `tags` / `platforms` / `version` / `enabled_by_default`，是 L1 摘要的现成数据来源。

docs/capabilities/skill.md 定义三级：L1（始终加载，全量名称+一句话描述，让 AI 知道有哪些 Skill）、L2（命中时加载完整 SKILL.md）、L3（SKILL.md 引用的附属文件，AI 经文件读取工具按需获取）。

约束（CLAUDE.md）：禁止 AI 框架；禁止全局可变状态（skills 目录路径已可注入）；新模块结构 import → 常量 → 数据类 → 函数；mypy strict；行长 100；TDD Hard Gate；测试 skills 目录隔离到 tmp_path，LLM 调用 mock。

## Goals / Non-Goals

**Goals:**
- skill_registry 产出 L1「名称+描述」清单，按**当前 agent 可用且启用**过滤，供注入链始终拼入 system prompt。
- 注入链改为「L1 始终 + L2 命中」分级：未命中也注入（过滤后的）L1，命中且过门控再追加该 Skill 的 L2 全文。
- 三处注入入口（`run_sync` / `run_stream` / `normalizer`）经**单一共享注入函数**统一，避免漏掉 IM 渠道。
- 明确 L3 边界：附属资源不随 L2 注入，由 AI 经既有文件读取工具按需获取。
- 保持 `match` / `load` / `list_skills` 既有契约不变。

**Non-Goals:**
- 不改关键词匹配算法（漏召问题由 L1 让 AI **感知**可用 Skill 来缓解，不在本 change 重写匹配）。
- **不实现 on-demand skill-load 工具**：L1 让 AI 看到清单，但 AI 无法主动拉取某个未命中 Skill 的 L2；按需拉取需要一个独立工具，留作后续 change。
- 不实现 aux LLM 路由（skill.md「规划中」的 L1 摘要 → LLM 路由命中，是独立后续）。
- 不实现多 Skill 共存的 L2 策略（多命中只注入首个 L2 仍成立；完整多 Skill 处理是 SK3）。
- 不实现新的 L3 资源读取工具（依赖既有文件读取工具，本 change 只定义 L3 不进 prompt）。
- 不实现热加载、安全审计、禁用机制（各自后续）；本 change 只在 L1/L2 的 `injectable` 谓词上预留这些维度的接口。

## Decisions

### D1：新增 `l1_summary(allowed_skills, blocked_skills, disabled_skills=None)` 产出**按 agent 过滤**的 L1 清单
`skill_registry` 新增纯函数 `l1_summary(allowed_skills, blocked_skills, disabled_skills=None) -> str`：遍历 `_index`，**仅保留对当前 agent `injectable` 的 Skill**（过 agent 绑定 `check_skill_access` ∧ enabled ∧ ¬disabled_skills，见 D4），把每个保留的 `SkillEntry` 渲染为一行「`- {name}: {description}`」，拼成一段清单文本（无可注入项时返回空串）。注入链始终调用它拼入 system prompt。
**为何**：L1 若裸 dump 全量 `_index`，会向 AI 展示它对当前 agent **用不了**的 Skill（不在白名单、被 blocked、或被禁用），既误导 AI 又泄露不可用能力。L1 必须与 L2 共享同一可见性边界——AI 看得到的，必须正是它（通过关键词命中后）真能注入的那批。L1（过滤后摘要，始终注入）与 L2（命中全文，按需注入）是两种不同粒度，分由 `l1_summary()` 与 `match`+`check_skill_access`+`load` 承载，职责清晰、各自可单测；复用既有 `_index` 数据，不新增索引结构。
**Alternatives**：①L1 裸 dump 全量 `_index`——被否，理由如上；②复用 `list_skills()` 在 agent_loop 里自行拼字符串并过滤——被否，渲染+过滤逻辑散到三个调用方、难单测且易漂移，且 `list_skills` 返回结构化列表其契约不应被注入格式绑架；③把 L1 渲染塞进 `match()` 返回——被否，`match` 是命中判定，混入摘要违背单一职责。

### D2：注入链改为「L1 始终 + L2 命中」分级，经**单一共享注入函数**统一三处入口
把现有 `_matched_skill_content` 扩展（或抽出）为一个单一共享注入函数 `_skill_injection(user_input, allowed_skills, blocked_skills) -> str | None`：先 `l1 = l1_summary(allowed_skills, blocked_skills)`（按 agent 过滤），再 `matched = match_skill(...)`；命中且 `check_skill_access` 通过则取 `l2 = load_skill(matched)`；最后把 L1 段与 L2 段以清晰分隔拼接返回（均空时返回 None）。`run_sync()`（行 496）/ `run_stream()`（行 531）/ `im_gateway/normalizer.py`（行 81-82）三处**全部改调此函数**，不再各自内联 `match`+`check_skill_access`+`load`。`run()`（行 299）不涉及（只收预构建 messages）。
**为何**：直接落实 skill.md 的分级定义——AI 始终看得到「（当前 agent 可用的）有哪些 Skill」，命中才付出全文 token 成本。注入逻辑此前已散在三处（两处共用 `_matched_skill_content`、normalizer 自己内联一份），若 L1/L2 改造只动 agent_loop，IM 渠道会拿不到 L1、行为分叉；收敛为单一函数是覆盖三处、防止漏改的结构前提。
**Alternatives**：①只改 agent_loop 两处、normalizer 保持内联——被否，IM 渠道会缺 L1 且未来每次注入语义变更都要双改、必然漂移；②把 L1 作为 system_prompt 的固定前缀在 `scan` 后一次性构建缓存——被否，索引会因热加载（后续 change）变化、且 L1 现在依赖 per-request 的 `allowed_skills`，固定前缀无法表达 per-agent 过滤；动态拼接每次请求读最新 `_index` 并带入当次 agent 绑定，与 `scan` 每次 CLI 调用 / lifespan 启动的现状一致（见 Open Questions）。

### D3：L3 边界 = 不随注入进入 prompt
L3（SKILL.md 内 `references/` 等引用的附属文件）明确**不**由注入链读取拼入。AI 若需要，经既有文件读取工具按需获取。本 change 仅以 spec 钉死「L2 注入不包含 L3 附属文件内容」这一边界。
**为何**：L3 延迟加载的全部价值就是「不为可能用不到的资料预付 token」；把边界写进 spec 可被「附属文件内容不出现在 prompt」这一端到端断言验证。
**Alternatives**：随 L2 一并注入引用文件——被否，正是渐进式加载要消除的 context 浪费。

### D4：引入单一 `injectable(skill, request)` 谓词，L1 与 L2 共查
定义一个统一可注入性谓词：`injectable(skill, request)` 当且仅当
`命中 ∧ enabled ∧ ¬disabled_skills ∧ ¬default_disabled ∧ 过 agent 绑定（check_skill_access）∧ ¬audit_blocked`
为真时返回真（其中「命中」仅对 L2 适用，L1 用其余条件）。L1（`l1_summary`）与 L2（命中后注入）都查这一组同源条件，保证「AI 在 L1 看得见的 Skill」与「关键词命中后真能注入 L2 的 Skill」是同一集合，不出现 L1 列了但 L2 注不进、或反之的偏差。
**本 change 落地范围**：本 change 实装 `enabled`（`enabled_by_default`）、`disabled_skills`（复用 `Settings.disabled_skills`，`match` 行 94 已支持）、`过 agent 绑定`（`check_skill_access`）三个维度。`audit_blocked`（SK5 注入审计）与更细的禁用标注/trace（SK6）按 Track G 序由后续 change 在同一谓词上叠加——本 change 将谓词留作扩展点，不预先实现其判定，仅在结构上为 SK3（`match_all` 中间产物）/ SK5 / SK6 的协调点。
**为何**：可见性（L1）与可注入性（L2）若各算各的过滤，极易随后续 change 叠加维度时分叉；单一谓词把「一个 Skill 此刻是否该出现在该 agent 的 prompt」收敛成一处定义，是与 SK3/SK5/SK6 协调的锚点。
**Alternatives**：L1 与 L2 各写一套过滤——被否，必然随维度增加而漂移。

## Risks / Trade-offs

- [L1 清单本身也消耗 token，Skill 数量大时清单不小] → L1 仅含「名称+一句话描述」、且已按当前 agent 过滤（通常远小于全量），单条开销远小于一篇全文；若未来规模过大，可在不改本 capability 契约的前提下引入 LLM 路由（skill.md 规划中）替代清单注入，本次接受过滤后清单。
- [动态每请求拼接 L1 与「固定前缀」相比有重复拼接成本] → 拼接是纯字符串操作、开销可忽略；且 L1 依赖 per-request 的 agent 绑定，本就无法固定前缀；换取热加载后清单不过期与 per-agent 正确性，权衡取动态拼接（见 Open Questions）。
- [L1 让 AI 看到 Skill 却无法主动拉取其 L2] → 当前 L2 仍由关键词 `match` 驱动，AI 对未命中 Skill 只能「感知+松散遵循其一句话描述」，不能强制拉全文；真正按需拉取需 on-demand skill-load 工具（后续 change），本 change 接受此限制并在 proposal/Non-Goals 明确标注。
- [L2 仍保持首次命中只注入一个] → 与现状一致，多 Skill 的 L2 策略属 SK3，本 change 不扩大范围。
- [L3 不注入可能让 AI 拿不到关键附属信息] → 这是渐进式加载的预期：附属资料由 AI 显式按需读取，避免无差别预载；SKILL.md 正文应自带「需要时去读哪个文件」的指引。

## Open Questions

- L1 清单注入方式：作为 system_prompt 固定前缀还是每次请求动态拼接？（skill.md 已列为待决）本 change 取动态拼接最小实现以兼容后续热加载；若 token 评估显示固定前缀更优，可在热加载 change 落地后重新评估。
- L1 → aux LLM 路由（用 L1 摘要让 LLM 规划命中）是否纳入：本 change 不实现，留作独立后续；当前仅靠关键词匹配决定 L2，L1 只负责让 AI「感知」当前 agent 可用的 Skill。
- on-demand skill-load 工具（让 AI 主动拉取某个 L1 可见但未命中 Skill 的 L2 全文）何时落地：本 change 不实现，作为独立后续；它将与本 change 的 `injectable` 谓词复用同一可注入性边界。

## Why

`agent_loop` 当前的 Skill 注入是「全有或全无」的单段拼接：调用 `match_skill(user_input)` 取第一个命中的 Skill 名，命中则 `load_skill(matched)` 把**整篇 SKILL.md** 拼到 system prompt 末尾。注入逻辑经 `agent_loop._matched_skill_content(user_input, allowed_skills, blocked_skills)`（行 231）封装——它先 `match_skill` 命中，再用 `check_skill_access(matched, allowed_skills, blocked_skills)` 做 **agent skill 绑定门控**（白名单/黑名单），通过才 `load_skill`，因此并非「简单 match→load」链。三处入口共用该门控注入：`run_sync()`（行 479，注入调用在行 496）、`run_stream()`（行 505，注入调用在行 531），以及 **IM 渠道** `im_gateway/normalizer.py`（行 81-82：`match`+`check_skill_access`+`load` 内联注入）。`run()`（行 299）接收的是**预构建好的 messages**、自身不做 Skill 注入。未命中则什么都不注入。这有两个 token 维度的硬伤：

- **未命中即 AI 完全不知有哪些 Skill 可用**：关键词匹配漏召（description 用词与用户措辞不一致）时，AI 既看不到 Skill 列表、也无从感知，等于该 Skill 不存在。
- **命中即灌入全文**：一篇 SKILL.md 连同其引用的附属资料若都进 prompt，无关大段长期占用 context，与 v1.0「减少无关 Skill 对 context 占用」的诉求相悖。

SK2（`skill-yaml-frontmatter`）已把索引升级为结构化 `SkillEntry`（含 `description` 等元数据），为分级注入提供了元数据来源。本 change 落实 docs/capabilities/skill.md「规划中」的**渐进式加载（L1 / L2 / L3）**：始终注入 L1 全量摘要、命中时加载 L2 全文、L3 附属资源延迟到 AI 用文件读取工具按需获取。

## What Changes

- 新增 **L1 摘要索引注入**：注入前由 skill_registry 产出 Skill 的「名称 + 一句话描述」清单（L1），由注入链始终拼入 system prompt，让 AI **感知**「有哪些 Skill 可用」并松散遵循其一句话描述，即便关键词未命中也能看到清单。L1 清单 MUST 按**当前 agent 可用且启用**的 Skill 过滤产出（应用 `allowed_skills` / `blocked_skills` / `disabled_skills` 等维度），**不**裸 dump 全量 `_index`——否则会向 AI 展示它对当前 agent 用不了的 Skill。
- 形式化 **L2 全文按需加载**：关键词命中**且**通过 agent 绑定门控的 Skill 才 `load()` 其完整 SKILL.md 正文（L2）并注入，保持「命中才灌全文」的最小化原则。
- 明确 **L3 附属资源延迟加载边界**：SKILL.md 中引用的附属文件（L3）**不**随 L2 注入，由 AI 经既有文件读取工具按需获取；本 change 只定义「L3 不进 prompt」这一边界，不实现新的资源读取工具。
- skill_registry 新增产出 L1 清单的函数 `l1_summary(allowed_skills, blocked_skills, disabled_skills=None)`，接收并应用 agent 绑定/启用过滤维度，与既有 `match()`（L2 命中判定）/ `load()`（L2 全文）职责分离；`list_skills()` 既有契约不变。
- 注入链按 L1（始终，按 agent 过滤）+ L2（命中且过门控）分段拼接，替代现有「命中才拼一段、未命中不拼」的单段逻辑；三处注入入口（`run_sync` / `run_stream` / `normalizer`）经**单一共享注入函数**统一改造，避免漏掉 IM 渠道。
- **限制说明**：L1 仅让 AI 感知可用 Skill，当前注入仍由关键词 `match` 驱动；AI **无法**主动拉取某个未命中 Skill 的 L2 全文——真正的按需拉取需要一个 on-demand skill-load 工具（后续 change），不在本 change 范围。

## Capabilities

### New Capabilities
- `skill-progressive-disclosure`: Skill 注入的渐进式分级——L1「名称+摘要」清单始终注入（按当前 agent 可用且启用过滤），让 AI 感知可用 Skill；L2 仅命中且过门控的 Skill 完整正文按需注入；L3 附属资源不随注入进入 prompt、由 AI 经文件读取工具按需获取。

### Modified Capabilities
<!-- 无既有 spec 的需求级行为变更。关键词匹配算法与 frontmatter 解析（SK2）不变；本次仅把注入链由「单段全文」改为「L1+L2 分级」，并新增 L1 清单产出。Skill 注入此前无既有 spec 承载，故 L1 注入这一新行为收口在本新 capability 内描述。 -->

## Impact

- **代码**：
  - 修改 `src/fleetent/skill_registry.py`：新增 `l1_summary(allowed_skills, blocked_skills, disabled_skills=None) -> str` 产出**当前 agent 可用且启用**的 Skill「名称+描述」清单（L1），数据来自既有 `_index` 的 `SkillEntry`，应用 `check_skill_access`（agent 绑定）与 `disabled`（`enabled_by_default` / `disabled_skills`）过滤；不改 `match` / `load` / `list_skills` 契约。
  - 修改 `src/fleetent/agent_loop.py`：把 `_matched_skill_content` 扩展（或抽出）为一个**单一共享注入函数**（如 `_skill_injection(user_input, allowed_skills, blocked_skills) -> str | None`），产出「L1 清单 + 命中 L2 全文」分段拼接结果；`run_sync()`（行 496）/ `run_stream()`（行 531）改调它。`run()`（行 299）不涉及。
  - 修改 `src/fleetent/im_gateway/normalizer.py`（行 81-82）：IM 渠道注入改调同一共享函数，使 L1/L2 改造覆盖三处入口、不漏 IM 渠道。
- **配置**：无新增 Settings 字段（分级为静态策略，不需部署级配置）；`disabled_skills` 复用既有 `Settings.disabled_skills`。L1 注入形态（固定前缀 vs 动态拼接）见 design Open Questions，本次取动态拼接最小实现。
- **测试**：扩展 `tests/test_skill_registry.py`（`l1_summary` 仅含当前 agent 可用且启用的 Skill、被 blocked/未在 allowed/被 disabled 的 Skill 不出现、空结果时为空串）；扩展 `tests/test_agent_loop.py`（命中时 system prompt 同时含 L1 清单与 L2 全文；未命中时仍含 L1 清单但不含任一 L2 全文；L3 附属文件内容不进 prompt；三处注入入口行为一致）。LLM 调用按规范 mock，skills 目录隔离到 `tmp_path`。
- **不影响**：关键词匹配算法本身、SK2 的 frontmatter 解析、`load()` / `list_skills()` 契约、skills 目录解析（环境变量名为 `skill_registry.py:48` 的 `FLEETENT_SKILLS_DIR`，本 change 不改其解析，仅照此实际名称引用）、热加载/安全审计/禁用机制（各自后续 change，本 change 只在 L1 过滤维度上预留接口）。

## Dependencies

- **依赖 SK2（`skill-yaml-frontmatter`），排其后实施**：L1 清单由结构化 `SkillEntry` 的 `name` / `description` 产出，依赖 SK2 已固化的索引结构。

## Why

`agent_loop` 当前的 Skill 注入是「全有或全无」的单段拼接：`scan()` 后调用 `match_skill(user_input)` 取第一个命中的 Skill 名，命中则 `load_skill(matched)` 把**整篇 SKILL.md** 拼到 system prompt 末尾。注入只发生在两处入口构造 messages 时——`run_sync()`（行 408-415：`scan_skills()` → `match_skill` → `load_skill` 拼入 `full_system`）与 `run_stream()`（行 451-453：`match_skill` → `load_skill`）；`run()`（行 234）接收的是**预构建好的 messages**、自身不做任何 Skill 注入。未命中则什么都不注入。这有两个 token 维度的硬伤：

- **未命中即 AI 完全不知有哪些 Skill 可用**：关键词匹配漏召（description 用词与用户措辞不一致）时，AI 既看不到 Skill 列表、也无从主动援引，等于该 Skill 不存在。
- **命中即灌入全文**：一篇 SKILL.md 连同其引用的附属资料若都进 prompt，无关大段长期占用 context，与 v1.0「减少无关 Skill 对 context 占用」的诉求相悖。

SK2（`skill-yaml-frontmatter`）已把索引升级为结构化 `SkillEntry`（含 `description` 等元数据），为分级注入提供了元数据来源。本 change 落实 docs/capabilities/skill.md「规划中」的**渐进式加载（L1 / L2 / L3）**：始终注入 L1 全量摘要、命中时加载 L2 全文、L3 附属资源延迟到 AI 用文件读取工具按需获取。

## What Changes

- 新增 **L1 摘要索引注入**：注入前由 skill_registry 产出全量 Skill 的「名称 + 一句话描述」清单（L1），由注入链始终拼入 system prompt，让 AI 知道「有哪些 Skill 可用」，即便关键词未命中也可主动援引。
- 形式化 **L2 全文按需加载**：关键词命中的 Skill 才 `load()` 其完整 SKILL.md 正文（L2）并注入，保持「命中才灌全文」的最小化原则。
- 明确 **L3 附属资源延迟加载边界**：SKILL.md 中引用的附属文件（L3）**不**随 L2 注入，由 AI 经既有文件读取工具按需获取；本 change 只定义「L3 不进 prompt」这一边界，不实现新的资源读取工具。
- skill_registry 新增产出 L1 清单的函数（如 `l1_summary()`），与既有 `match()`（L2 命中判定）/ `load()`（L2 全文）职责分离；`list_skills()` 既有契约不变。
- 注入链按 L1（始终）+ L2（命中）分段拼接，替代现有「命中才拼一段、未命中不拼」的单段逻辑。

## Capabilities

### New Capabilities
- `skill-progressive-disclosure`: Skill 注入的渐进式分级——L1 全量「名称+摘要」清单始终注入让 AI 感知可用 Skill；L2 仅命中 Skill 的完整正文按需注入；L3 附属资源不随注入进入 prompt、由 AI 经文件读取工具按需获取。

### Modified Capabilities
<!-- 无既有 spec 的需求级行为变更。关键词匹配算法与 frontmatter 解析（SK2）不变；本次仅把注入链由「单段全文」改为「L1+L2 分级」，并新增 L1 清单产出。Skill 注入此前无既有 spec 承载，故 L1 注入这一新行为收口在本新 capability 内描述。 -->

## Impact

- **代码**：
  - 修改 `src/fleetent/skill_registry.py`：新增 `l1_summary() -> str`（或等价结构）产出全量 Skill 的「名称+描述」清单（L1），数据来自既有 `_index` 的 `SkillEntry`，不改 `match` / `load` / `list_skills` 契约。
  - 修改 `src/fleetent/agent_loop.py`：`run_sync()`（行 408-415）/ `run_stream()`（行 451-453）的注入链改为：始终拼入 L1 清单；命中时追加 L2 全文；L3 不拼入。`run()` 不涉及（它只收预构建 messages，不做 Skill 注入）。
- **配置**：无新增 Settings 字段（分级为静态策略，不需部署级配置）。L1 注入形态（固定前缀 vs 动态拼接）见 design Open Questions，本次取动态拼接最小实现。
- **测试**：扩展 `tests/test_skill_registry.py`（`l1_summary` 含全量名称+描述、空索引时为空）；扩展 `tests/test_agent_loop.py`（命中时 system prompt 同时含 L1 清单与 L2 全文；未命中时仍含 L1 清单但不含任一 L2 全文；L3 附属文件内容不进 prompt）。LLM 调用按规范 mock，skills 目录隔离到 `tmp_path`。
- **不影响**：关键词匹配算法本身、SK2 的 frontmatter 解析、`load()` / `list_skills()` 契约、skills 目录解析（环境变量名当前实现为 `skill_registry.py:34` 的 `MINI_AGENT_SKILLS_DIR`，本 change 不改其解析，仅照此实际名称引用）、热加载/安全审计/禁用机制（各自后续 change）。

## Dependencies

- **依赖 SK2（`skill-yaml-frontmatter`），排其后实施**：L1 清单由结构化 `SkillEntry` 的 `name` / `description` 产出，依赖 SK2 已固化的索引结构。

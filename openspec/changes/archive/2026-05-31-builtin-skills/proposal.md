## Why

当前 `skill_registry` 只扫描用户提供的 `skills/` 目录（`scan()` 行 12-24），平台自身不携带任何开箱即用的 Skill——客户全新部署后索引为空，必须先自行编写 Skill 才能让 agent 具备领域行为指南。同时，`scan()` 一旦把某个 Skill 纳入索引，`match()` 就会无条件参与匹配与注入，**没有任何禁用开关**：管理员无法关闭一个不想要的 Skill，运维侧也无法回答「为什么这个 Skill 没生效 / 凭什么生效」。

SK2（`skill-yaml-frontmatter`）已将索引升级为结构化元数据并解析 `enabled_by_default` 布尔字段，但明确把「`enabled_by_default=false` 接线到匹配过滤」留作后续 change（见其 Non-Goals）。本 change 建立在 SK2 之上，补齐两个缺口：平台**内置 Skill 类别**与**启用/禁用机制**，落实 docs/capabilities/skill.md「规划中」的「禁用机制」(roadmap SK6) 诉求。

## What Changes

- 引入**平台自带「内置 Skill」类别**：平台 ship 一批内置 Skill，放在包内已知位置（`src/fleetent/builtin_skills/`，路径为模块级常量、可 `monkeypatch` 注入）；`scan()` 在扫描用户 `skills/` 目录的同时一并扫描内置目录，索引条目新增 `builtin: bool` 标记以区分「平台内置」与「用户自加」。
- 引入**每个 Skill 的启用/禁用开关**：
  - `enabled_by_default`（frontmatter，SK2 已解析）决定 Skill 的默认启用态。
  - 管理员可经部署级配置**强制禁用**指定 Skill：`config.py` 的 `Settings` 增加 `disabled_skills: list[str]` 字段（env 可配，沿用既有 Settings env 模式）。
  - 被禁用的 Skill（`enabled_by_default=false` 且未被显式启用，或被 `disabled_skills` 命中）从 `match()` 结果中排除、不注入；`load()` 仍可按名加载（启用判定只约束自动匹配，不影响显式加载契约）。
- **禁用原因可观察**：Skill 因禁用未参与匹配时记录结构化 warning/info 日志，便于排查「为什么这个 Skill 没生效」。
- 内置 Skill 与用户 Skill **同名冲突**交并行 change `skill-name-conflict-warning`(SK8) 统一处理（确定性选定 + 告警）；本 change **不自定义覆盖规则**。要替换某内置 Skill 走**禁用开关**（把内置名加入 `disabled_skills`），而非隐式同名覆盖。

## Capabilities

### New Capabilities
- `builtin-skills`: 平台自带内置 Skill 类别（包内已知位置随用户 `skills/` 一并扫描、索引标记 `builtin`）与 Skill 启用/禁用机制（`enabled_by_default` 默认态 + `disabled_skills` 配置强制禁用，被禁用 Skill 排除出匹配并记录原因）。

### Modified Capabilities
<!-- 无既有 spec 的需求级行为变更。SK2 已将 enabled_by_default 解析入索引但不接线过滤；本 change 在新 capability builtin-skills 内首次定义「内置类别」与「禁用过滤」行为，不改 SK2 已固化的解析需求。 -->

## Impact

- **代码**：
  - 修改 `src/fleetent/skill_registry.py`：新增模块级常量 `BUILTIN_SKILLS_DIR`（指向 `src/fleetent/builtin_skills/`，可 `monkeypatch` 注入）；`scan()` 扫内置目录 + 用户目录并给索引条目标记 `builtin`（同名冲突的选定与告警交 SK8，本 change 不实现覆盖逻辑）；`match()` 在筛选时排除被禁用的 Skill。
  - 新增 `src/fleetent/builtin_skills/` 目录（至少含一个示例内置 Skill 的 `SKILL.md`，供扫描与测试）。
  - 修改 `src/fleetent/config.py`：`Settings` 增加 `disabled_skills: list[str] = []`（env 可配，沿用既有字段模式）。
- **配置**：`disabled_skills` 经 Settings env 字段配置；`skill_registry` 提供禁用名单注入点（参数或惰性读 Settings，对齐 `context_mgr._default_config()` 模式），测试通过传参注入、不实例化真 `Settings`。
- **依赖**：不引入新依赖（沿用 SK2 已有的 `pyyaml`）。
- **测试**：扩展 `tests/test_skill_registry.py`：内置目录被扫描且标记 `builtin`、`enabled_by_default=false` 不参与匹配、`disabled_skills` 强制禁用、禁用记录 warning；内置目录与用户 `skills/` 目录均隔离到 `tmp_path`，禁用日志断言 structlog warning。（同名冲突的选定/告警用例属 SK8，本 change 不覆盖。）
- **不影响**：关键词匹配算法本身、注入流程、`load()` 契约、SK2 的 frontmatter 解析行为；per-agent Skill 绑定（独立 change `agent-skill-binding`）；热加载 / 安全审计 / 渐进式加载（各自后续）。

## Dependencies

- **依赖 SK2（`skill-yaml-frontmatter`），排其后实施**：本 change 复用 SK2 已结构化的索引条目与 `enabled_by_default` 解析结果；必须在 SK2 合入后开展。

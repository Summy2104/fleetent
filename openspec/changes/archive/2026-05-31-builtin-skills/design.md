## Context

`skill_registry.scan(skills_dir)`（行 12-24）当前只扫描单一用户目录（默认 `skills/`，env `MINI_AGENT_SKILLS_DIR` 覆盖），遍历 `*/SKILL.md` 写入 `_index`。`match(user_input)`（行 27-38）遍历索引、关键词命中即返回首个 Skill 名；`load(name)`（行 41-44）按名读全文。平台自身不携带任何 Skill，且索引中所有 Skill 一律参与匹配，无禁用开关。

SK2（`skill-yaml-frontmatter`）已把 `_index` 值从 `tuple[str, str]` 升级为结构化元数据（含 `description` / `path` / `tags` / `platforms` / `version` / `enabled_by_default`），并将 `enabled_by_default` 解析为布尔（缺省 `True`）。SK2 明确把「`enabled_by_default=false` 接线到匹配过滤」留作后续（其 Non-Goals）。本 change 在 SK2 之上消费这些字段。

本 change 落实 docs/capabilities/skill.md「规划中」的「禁用机制」(roadmap SK6)，并补上文档尚未单列的「内置 Skill 类别」概念——二者合一为新 capability `builtin-skills`。SK6 在 skill.md 中含「全局禁用」与「agent 级禁用」两层；本 change 实现**全局禁用**层，**agent 级禁用**属并行 change `agent-skill-binding` 范围（见 Non-Goals）。

约束（CLAUDE.md）：禁止 AI 框架；禁止全局可变状态（内置目录路径、禁用名单必须可 `monkeypatch` / 参数注入）；config 走 Settings env 字段；新模块结构 import → 常量 → 数据类 → 函数；mypy strict；行长 100；TDD Hard Gate；测试 skills 目录隔离到 tmp_path、禁用日志断言 structlog warning。

## Goals / Non-Goals

**Goals:**
- 引入平台内置 Skill 类别：包内已知位置（`BUILTIN_SKILLS_DIR`，可注入）随用户 `skills/` 一并被 `scan()` 扫描，索引条目以 `builtin: bool` 区分来源。
- 内置/用户同名冲突**交并行 change `skill-name-conflict-warning`(SK8)统一处理**（确定性选定 + 告警），本 change 不自定义覆盖规则；要替换某内置 Skill 走**禁用开关**（显式），而非隐式同名覆盖。
- 引入全局启用/禁用机制：`enabled_by_default` 定默认态；`Settings.disabled_skills` 配置强制禁用；被禁用 Skill 排除出 `match()`、不注入。
- 禁用导致 Skill 未参与匹配时记录可观察日志（排查「为何没生效」）。
- 启用判定仅约束自动匹配（`match`），不改 `load()` 显式加载契约。

**Non-Goals:**
- 不做 per-agent / agent 级 Skill 禁用与绑定（并行 change `agent-skill-binding`）。
- 不实现热加载、安全审计、渐进式加载（L1/L2/L3）（各自后续 change）。
- 不修改 SK2 已固化的 frontmatter 解析行为，不新增 frontmatter 字段（复用 SK2 的 `enabled_by_default`）。
- 不引入新依赖；不实现「管理员经 API 运行时切换启用态」（本次仅部署级 env 配置 + frontmatter 默认态）。

## Decisions

### D1：内置 Skill 经包内已知目录扫描，索引标记 `builtin`
新增模块级常量 `BUILTIN_SKILLS_DIR: Path`，指向包内相对位置 `Path(__file__).parent / "builtin_skills"`，作为模块级路径常量**可被 `monkeypatch` 注入**（同 CLAUDE.md 对 `DB_PATH` / `SESSIONS_DIR` 的要求）。`scan()` 先扫 `BUILTIN_SKILLS_DIR`（标记 `builtin=True`）再扫用户 `skills_dir`（标记 `builtin=False`），两轮共用既有 `*/SKILL.md` 遍历与 SK2 的 frontmatter 解析逻辑。索引条目（SK2 已结构化）新增 `builtin` 字段。
**为何**：内置 Skill 是平台资产，随包发布、放包内才能保证「全新部署即可用」；标记来源便于排查与后续治理（如 list_skills 区分展示）。路径常量可注入满足测试隔离与「禁止全局可变状态」。
**Alternatives**：①内置 Skill 写死在代码里（字符串常量）——被否，与用户 Skill 形态不一致、无法复用同一扫描/解析路径、维护成本高；②内置 Skill 也放外部 `skills/`——被否，则不随包发布，失去「开箱即用」意义。

### D2：同名冲突交 SK8 统一处理，本 change 不自定义覆盖规则
内置/用户的同名冲突（无论跨来源还是同来源）**一律由并行 change `skill-name-conflict-warning`(SK8)** 的确定性策略（路径字符串排序选胜 + 告警）处理。本 change 只负责「扫描内置目录 + 标记 `builtin` + 禁用开关」，**不引入任何同名覆盖规则**，避免与 SK8 出现两套相互矛盾的冲突策略。`scan()` 先扫内置后扫用户的顺序仅为发现/打标记，不再承担「后写覆盖」语义（胜出由 SK8 路径排序决定，与扫描顺序无关）。
**替换内置 Skill 的显式机制 = 禁用开关**：要让某内置 Skill 不再生效，部署方把其名加入 `disabled_skills`（D3/D4）将其排除出 `match`；如需用自己的版本承担同类职责，再放一个（建议**不同名**以免与 SK8 的确定性选定相互作用）的 Skill。比隐式「同名 shadow」更可控、可观察。
**为何**：冲突策略单一来源（SK8），职责清晰；内置定制走显式禁用而非隐式同名覆盖，避免误命名意外顶掉内置、也避免两 change 规则打架。
**Alternatives**：①本 change 自定义「用户覆盖内置」——被否（与 SK8 路径排序策略冲突，落地会打架，已由用户决定采用方案一）；②内置优先不可替换——被否，禁用开关已提供定制能力。

### D3：禁用判定 = 默认态 + 配置强制禁用，仅约束 match
一个 Skill 视为「被禁用、排除出 `match`」当且仅当满足任一：
- 其 `enabled_by_default` 为 `false`（SK2 解析所得，缺省 `True` 即默认启用）；或
- 其名出现在 `disabled_skills` 配置名单中（强制禁用，优先级最高，可禁用一个默认启用的 Skill）。

`match()` 在遍历索引时跳过被禁用的 Skill。`load(name)` 不受启用判定约束——显式按名加载仍可取得内容（启用判定只治理「自动匹配注入」这一可观察行为，不破坏 load 契约）。
**为何**：`enabled_by_default` 是 Skill 作者声明的默认意图，`disabled_skills` 是部署方的强制覆盖，二者语义正交且后者优先，符合「管理员可显式关闭」诉求；只约束 match 把改动范围收敛在「自动注入」行为，blast radius 最小。
**Alternatives**：①禁用同时让 `load` 报错——被否，会牵连显式加载调用方且超出「不参与匹配注入」的最小诉求；②只用 `disabled_skills` 不消费 `enabled_by_default`——被否，浪费 SK2 已解析的字段且无法表达作者默认意图。

### D4：禁用名单经 Settings env 配置 + 注入点（对齐 context_mgr 模式）
`config.py` 的 `Settings` 增加 `disabled_skills: list[str] = []`（env 可配，pydantic-settings 支持 list 字段，与既有 `context_*` / `permission_gate_*` 同类）。`skill_registry` 提供禁用名单的注入点：`scan()` 或 `match()` 接受可选 `disabled_skills` 参数，缺省时惰性 `from fleetent.config import Settings` 读取（同 `context_mgr._default_config()` 第 11 行的惰性 import 模式）。解析优先级：调用参数 > Settings（env）> 字段默认值（空列表）。测试通过传参注入，不实例化真 `Settings`（避免 `anthropic_api_key` 必填）。
**为何**：项目所有运行旋钮统一走 Settings env 字段；惰性 import + 参数覆盖既满足可配置又满足测试隔离与「禁止全局可变状态」。
**Alternatives**：①模块级可变 `DISABLED: set`——被否，全局可变状态，违反 CLAUDE.md；②settings.yaml——被否，项目无此文件，机制是 pydantic-settings 读 env。

### D5：禁用可观察——记录原因日志
当某 Skill 因禁用未参与匹配（或在 scan/筛选阶段被判定禁用）时，记录一条结构化日志（structlog warning/info，含 Skill 名与禁用来源：`enabled_by_default=false` vs `disabled_skills` 命中），落实 skill.md「禁用状态记录在运行日志中，便于排查为什么这个 Skill 没生效」。
**为何**：禁用是「静默不生效」的常见困惑源，可观察性是 SK6 的明确诉求。
**Alternatives**：完全静默禁用——被否，与 skill.md 诉求相悖、运维不可排查。

## Risks / Trade-offs

- [内置 Skill 随包发布，质量/注入安全未经审计] → 安全审计是独立后续 change；本次内置 Skill 由平台维护、纳入版本控制，范围可控；不引入运行时不可信内容。
- [`disabled_skills` 配错 Skill 名（拼写/大小写）导致预期禁用未生效] → 禁用判定与日志记录使运维可核对实际匹配集；名单为精确名匹配，文档说明取 frontmatter `name`。
- [`enabled_by_default=false` 接线过滤后，原本「能被匹配」的 Skill 突然不生效] → 这正是本 change 的预期行为；为兼容，未声明 `enabled_by_default` 的 Skill 缺省 `True`（SK2 已定），既有 Skill 行为不变。
- [内置目录路径用包内相对位置，打包/安装后路径可能漂移] → 用 `Path(__file__).parent` 锚定包目录而非 cwd，随包安装迁移；常量可 monkeypatch 便于测试与异常部署覆盖。
- [与并行 change `agent-skill-binding` 在「禁用/启用」语义上潜在重叠] → 边界明确：本 change 只做**全局**启用/禁用（部署级 + 作者默认态），agent 级绑定/禁用归 `agent-skill-binding`；二者在不同维度叠加，无需互改主路径。

## Open Questions

- 内置 Skill 首批应包含哪些（数量与主题）——本次只需 ship 至少一个示例内置 Skill 以建立类别与扫描路径，具体清单可后续单独补充，不阻塞本 change 的机制落地。
- `disabled_skills` 名匹配是否需大小写不敏感——本次取精确匹配（与 frontmatter `name` 一致），如有运维需求后续再放宽。

## Context

fleetent 的 skill 模型是 openclaw 式 read-on-demand：`available_skills_prompt()` 把已启用 skill 的 name/description/location 注入 system prompt 作为常驻 catalog，模型用唯一的 `read_skill(name)` 工具加载 SKILL.md 全文，skill 脚本经沙箱执行面 `run_code` 在 `/workspace/skills`（`$SKILLS_DIR`）下运行。`skills/registry.py` 已具备：scan/索引、静态注入审计（`audit.py`，scan 时把 severe 命中标 `audit_blocked`）、`write_skill(name, files, provenance)`（reflection 用的全 bundle 原子写 + 写入期 `_validate_skill_bundle` 审计 + provenance 注入 + 热重载）、热重载、name 冲突解析（user 覆盖 builtin）。

约束（不可逾越）：
- **agent ⊥ platform**：`skills/`、`tools/` 是 agent 运行时模块，MUST NOT `import fleetent.platform.*`；skill 写操作只落文件，MUST NOT 写 platform 管理表。drift 由 platform 观察 agent home 标记，不由 agent 反向写入（见既有 `skill-provenance` spec）。
- **TDD Hard Gate**：每个实现 task 先红后绿。
- **数据主权**：不接任何公网 skill Hub。

工具层：`@tool(risk_level=..., availability=...)` 注册；per-agent 通过 `allowed_tools`(fnmatch) + `is_tool_visible` 在 schema-build 时过滤；动态 risk_level 是 `(args, tool_context) -> band` 的 callable，经 `governance.approval_policy.risk_for` 裁定审批。`ToolContext` 携带 `agent_name` / `session_id` / `scope_key` 等。

## Goals / Non-Goals

**Goals:**
- `read_skill` 能按相对路径读 skill 目录下支撑文件，遍历防护，省略参数时零行为变化。
- 提供 `list_skills(keyword, category)` 按需查询，作为 catalog 被 cap/截断时的逃生口，不改 catalog 注入。
- 提供用户显式驱动的 `skill_manage` CRUD，写操作强制审批、只写 per-agent、builtin 只读、写入期审计、provenance；默认关闭。
- 全程 agent 侧、零 platform 依赖。

**Non-Goals:**
- 不做 agent 自主（无人介入）造 skill：每次写都过审批门。
- 不做 curator（自动 stale/archive）、不做 usage 计数 sidecar（复用 `skill_hit` trace）。
- 不做跨 agent/跨部署分发、不接公网 Hub。
- 不改 catalog 注入逻辑、不改 reflection 的 `write_skill` 现有契约。

## Decisions

### D1：`read_skill` 增 `file_path`，遍历防护在 registry 内
`read_skill(name, file_path=None, tool_context=None)`。`file_path=None` 走现状（返回 SKILL.md 正文 + `_READ_SKILL_GUIDANCE`）。给出相对路径时，新增 registry 函数 `read_skill_file(name, rel_path) -> str` 计算 `skill_dir = Path(_index[name].path).parent`，`resolved = (skill_dir / rel_path).resolve()`，并断言 `resolved` 在 `skill_dir.resolve()` 之内（`os.path.commonpath` 或 `resolved.is_relative_to(skill_dir)`）；越界/不存在返回明确错误文本，不抛。`audit_blocked` 的 skill 同 `read_skill` 主路径一样拒绝。命中后照样写 `skill_hit` trace。
- 备选：在 tool 层做路径校验——否决，校验属 registry 边界（store/registry 是可审计边界），tool 只做编排。

### D2：`list_skills` 工具复用 registry 过滤，与 catalog 解耦
新增 registry `query_skills(keyword=None, category=None, include_disabled=False) -> list[dict]`，在现有 `list_skills()`（返回全量 name+description）基础上做大小写无关子串过滤：`keyword` 命中 name/description/tags 任一；`category` 命中 `tags`（fleetent skill 无独立 category 字段，category 语义即按 tag 归类——在 spec/docstring 写清）。默认排除 `audit_blocked` 与 author-disabled（与 catalog 资格一致），不返回 location 之外的正文。tool `list_skills` 仅包装它。
- 不动 `available_skills_prompt`：catalog 仍常驻、仍 cap/截断；`list_skills` 是补充查询面，二者读同一 `_index`，零回归。
- 备选：让 list_skills 触发 catalog trim——否决，trim 会回退发现性且超出本次范围。

### D3：`skill_manage` 一个工具多 action，强制审批 + 默认关
单 tool `skill_manage(action, name, content=None, file_path=None, file_content=None, old_string=None, new_string=None, replace_all=False, tool_context=None)`，action ∈ `create/patch/edit/delete/write_file/remove_file`。
- **审批门**：用动态 `risk_level` callable，对所有写 action 返回强制审批的 band（≥ `medium`，medium 即强制审批），经现有 `approval_policy.risk_for` 裁定。即使模型自作主张调用，也被审批拦下——「用户显式」由审批确定性保证，而非靠模型自觉。
- **默认关 + schema 门控**：新增 `AgentFile.skill_authoring_enabled: bool = False`。在 loop 组装 schema 处（`get_schemas()` 后、`is_tool_visible` 过滤旁）追加一条：`skill_manage` 仅当该 agent `skill_authoring_enabled` 为真才保留。关闭时模型连工具 schema 都看不到。
- 备选 `availability` 谓词——否决，它无参读全局，无法表达 per-agent；schema-build 时门控才是 per-agent 正解（与 CLAUDE.md「enablement gate 在 schema-build 时」一致）。
- 备选拆成多个 tool（create_skill/edit_skill/...）——否决，hermes 单 `skill_manage` 多 action 更聚合、schema 更省、审批裁定点单一。

### D4：写范围只 per-agent，builtin 只读
所有写 action 的目标 root = 该 agent 的有效用户 skills 根（`effective_skill_root`，即 `_last_skills_dir`/agent `skills_dir`）。delete/edit/patch/write_file/remove_file 前，先 `_index[name]` 定位目标；**若 `entry.builtin` 为真则拒绝**（返回明确错误），builtin/bundled 对工具只读。create 写新目录；同名已存在时按 action 语义（create 拒绝已存在、edit/patch 要求已存在）。写后 `reload()` 热刷新（`write_skill` 已有此行为）。
- 注意 `materialize_builtin_skills` 会把 builtin 拷进用户根——拷贝后该副本 `builtin=False`，本设计据 `_index` 的 `builtin` 标志判定，故「物化的 builtin 副本」可被编辑（已是用户根下的可定制副本），符合现有 user-overrides-builtin 语义；真正 package 内的 builtin 不可达写。

### D5：写入期 + 读取期双端审计
create/edit 经 `write_skill` 路径（已含 `_validate_skill_bundle` → severe 拒绝持久化）。patch/write_file 对**写入后的最终 SKILL.md 全文**跑同一 `_validate_skill_bundle`（patch 改的是 SKILL.md 时）或对支撑文件不审计正文但仍受目录约束。读取期审计沿用既有 `read_skill`/catalog 的 `audit_blocked` 机制。新增/复用 registry 级 helper，使「写入时严重命中拒绝持久化」对所有写 SKILL.md 的 action 一致生效。

### D6：provenance 一行，usage 复用 trace
create 时注入 frontmatter 一行来源标记：复用既有 `SkillWriteProvenance` 形状或新增轻量 `metadata.fleetent.origin = "agent_tool"` + 时间戳（时间戳由 tool 层传入，registry 不取系统时钟以保持可测）。usage 不另存——`skill_manage` 成功写一条 agent 侧 observability trace（同 `skill_hit` 风格，event 如 `skill_authored`），platform 需要时读 agent 侧产物。不引入 `.usage.json`、不引入 curator。

## Risks / Trade-offs

- **写工具被模型滥用** → 默认关 + 强制审批门 + per-agent-only + builtin 只读 + 写入期审计，四重收口；关闭态下 schema 不可见。
- **patch 把 SKILL.md 改坏/注入** → patch 后对最终全文重跑 `_validate_skill_bundle`，severe 命中则回滚不持久化（复用 `write_skill` 的 tmp→rename + 失败清理）。
- **路径遍历**（file_path / write_file / remove_file） → registry 内 `resolve()` + 包含断言，越界拒绝；所有相对路径都经此校验。
- **删 builtin / 误删** → builtin 标志拒绝；delete 经审批门，用户确认才执行。
- **category 语义含糊**（无独立字段） → 明确定义为按 `tags` 过滤，docstring/spec 写清，避免模型误解。
- **审批门在无 IM/审批通道的 standalone 场景** → 沿用现有 approval 机制的降级行为（与其它强制审批工具一致），本设计不改审批基础设施。

## Migration Plan

- 纯增量：新工具、新 registry 函数、一个默认 `false` 的 agent 配置字段。无 DB 迁移、无 platform 改动。
- 部署后默认行为不变：`skill_manage` 默认不可见；`read_skill` 无 file_path 时字节级同旧；catalog 注入不变。
- 回滚：移除新工具注册与配置字段即可，无持久化遗留。

## Open Questions

无（设计决策已在 brainstorming 阶段全部敲定：用户显式触发、工具+强制审批门、per-agent-only/builtin 只读、双端审计、provenance 一行不做 curator、默认关、不接公网 Hub）。

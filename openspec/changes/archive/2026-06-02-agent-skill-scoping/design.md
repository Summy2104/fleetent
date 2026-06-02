## Context

`skill_registry.available_skills_prompt(disabled_skills=None)`（skill_registry.py:319）把所有「已启用」的 skill 渲染为 `<available_skills>` 清单。「已启用」由单一谓词 `_disabled_reason(name, entry, disabled)`（skill_registry.py:281）判定——四个禁用来源按优先级：`audit_blocked` > `frontmatter_disabled`（`enabled: false`）> `config_disabled`（`disabled_skills`）> `default_disabled`（`enabled_by_default: false`）；返回 None 即「进清单」。调用点三处当前都无参调用：`agent_loop.py:1179`（run_sync / CLI）、`agent_loop.py:1235`（run_stream，server 路径）、`im_gateway/normalizer.py:141`（IM 路径，随后调 `agent_loop.run`）。

`agent_store.Agent`（agent_store.py:14）已有 `allowed_tools`、`features`、`plugins` 三个 JSON TEXT 列；`plugins` 由 alembic 003（`op.add_column`）加列、`_init_db` 的 `CREATE TABLE` 内联同时声明，旧行经 `json.loads(row[...] or "[]")` 兜底为 `[]`。最新迁移为 003。

约束（CLAUDE.md）：禁 AI 框架；禁 ORM（`agents` 表用 stdlib sqlite3 裸 SQL，SQLAlchemy 仅供 alembic）；禁全局可变状态；新模块结构 import → 常量 → 数据类 → 函数；mypy strict；行长 100；TDD Hard Gate；测试隔离（DB monkeypatch `tmp_path`、skill 目录隔离、LLM mock）。无新增依赖。

本 change 触及 capability `agent-definition`（`Agent` / `agents` 表加 `allowed_skills`），新增 capability `agent-skill-scoping`（收窄语义本身）；加列方式与 `db-migration` capability（alembic + 禁应用代码裸 ALTER）一致。

## Goals / Non-Goals

**Goals:**
- `Agent` 与 `agents` 表加 `allowed_skills: list[str]`（默认空，向后兼容），照 `plugins` 同款持久化与迁移（alembic 004 + `_init_db` 内联）。
- `available_skills_prompt` 加 `allowed_skills` 参数：空 / None → 不收窄（=现状）；非空 → 清单只保留命中且未被禁用的 skill，与 `_disabled_reason` 叠加。
- `run()` / `run_stream()` 加 `allowed_skills` 入参并透传给 catalog 构建；server / normalizer 从 `agent.allowed_skills` 传入，无 agent 绑定 → None。
- 明确「仅清单可见性、非授权边界」：不动 tool 访问控制、不动按名 `read_skill` 的 `load`。

**Non-Goals:**
- 不把 skill 变成授权边界（模型读了某 SKILL.md 仍受 `allowed_tools` + 审批门约束；这是项目既定原则）。
- 不限制 `read_skill` 按名 `load`（显式按名 load 仍可，与既有「load 不受禁用约束」口径一致）；收窄只改默认清单可见性。
- 不引入新依赖、不新增 Settings 字段、不改四来源禁用谓词的语义。
- 不改 `plugins` / `allowed_tools` 的「空 = 无」语义（`allowed_skills` 独立取「空 = 不限制」，理由见 D2）。

## Decisions

### D1：`Agent.allowed_skills: list[str]`，照 `plugins` 同款持久化 + alembic 004
`Agent` 加 `allowed_skills: list[str] = field(default_factory=list)`；`agents` 表 `CREATE TABLE` 内联加 `allowed_skills TEXT NOT NULL DEFAULT '[]'`（fresh / test 库即带列），既有生产库经 **alembic 004**（`op.add_column("agents", sa.Column("allowed_skills", sa.Text(), nullable=False, server_default="[]"))`，`down_revision="003"`）升级——**非运行时裸 ALTER**。`create_agent` 加 `allowed_skills` 入参（默认 `None → []`）、`_SELECT_COLS` 追加列名、`_row_to_agent` 用 `json.loads(row[6] or "[]")` 兜底旧行（NULL → `[]`）。

**为何**：与 `plugins`（003）完全同构，最小改动、零认知分叉；fresh 库内联 + 生产库 alembic 的双写是仓库既定 db-migration 口径（禁应用代码裸 ALTER 对已存在列重复抛错）。
**Alternatives**：运行时 `_init_db` 内 PRAGMA + ALTER 探测加列——被否，违反 db-migration spec「禁止应用代码裸建表 / 加列」。

### D2：空 = 不限制（与 plugins 的「空 = 无」相反）
`allowed_skills` 为空 list 或 None → `available_skills_prompt` 不施加收窄，全部已启用 skill 仍可见（字节级等于现状）；非空 → 只保留名字在 `allowed_skills` 集合内、且 `_disabled_reason` 返回 None 的 skill。

**为何**：skill 现状默认对所有 agent 全可见。若取 `plugins` 那种「空 = 无」语义，所有未声明 `allowed_skills` 的既有 agent 会突然看不到任何 skill——破坏既有行为。`plugins` 可以「空 = 无」是因为插件工具从来默认不可见（必须显式授权）；两者默认态相反，故语义相反。这是有意的不对称，spec 与字段注释都标注。
**Alternatives**：统一为「空 = 无」与 plugins 对齐——被否，破坏向后兼容；用一个 sentinel（如 `None` vs `[]`）区分「未设置」与「设为空」——被否，引入第三态徒增复杂度，且空 list 与 None 在「不限制」语义下本就等价。

### D3：收窄在 `_disabled_reason` 过滤处叠加（同一谓词点）
`available_skills_prompt` 加 `allowed_skills: list[str] | None = None`。在它构建 `entries` 的列表推导（skill_registry.py:333-337，`if _disabled_reason(...) is None`）处叠加一个收窄条件：当 `allowed_skills` 非空时，额外要求 `name in set(allowed_skills)`。即「命中 allowed_skills（或 allowed_skills 为空 = 不约束）**且** 未被任何来源禁用」才进清单。两个条件 AND 叠加，禁用谓词不变、收窄是其上的额外过滤。

**为何**：收窄与禁用是两个正交关注点——禁用谓词（安全 / 作者意图 / 运维 config / 默认态）仍是唯一裁判「这个 skill 是否还活着」；`allowed_skills` 是「这个 agent 是否被分配看它」。AND 叠加保证：被禁用的 skill 即使在 `allowed_skills` 里也不出现（禁用优先），未授权的 skill 即使未被禁用也不出现。在同一过滤点叠加避免第二套遍历 / 谓词分叉。
**Alternatives**：先收窄成子 index 再跑禁用过滤——被否，等价但要复制 index、且 `collect_disabled_trace` 仍跑全 index 会语义错位；只在 `allowed_skills` 命中时跳过禁用检查——被否，会让收窄变成「绕过禁用」，违反「禁用优先」。

### D4：`run()` / `run_stream()` 透传，调用方从 agent 取
照 `agent_features` / `sandbox_mode` 的透传方式，`run()` 与 `run_stream()` 各加 `allowed_skills: list[str] | None = None`：
- **run_stream**（server 路径）：catalog 在函数内构建（agent_loop.py:1235），把 `allowed_skills` 传给该处 `available_skills_prompt(allowed_skills=allowed_skills)`。server.py 从 `agent.allowed_skills`（无 agent → None）经 kwargs 传入。
- **run()**：本身不构建 catalog（catalog 由调用方预组装进 messages）。`run()` 仍加 `allowed_skills` 入参以保持对外 API 对称、并供未来在 run() 内构建 catalog 的路径使用；当前生产路径（run_sync / normalizer）在调用 run() 之前就已用各自的 `allowed_skills` 构建好 catalog，故 run() 的该入参在现状下不重复施加过滤（避免双重过滤）。
- **normalizer**（IM 路径）：catalog 在调用 `agent_loop.run` 之前于 normalizer.py:141 构建，直接 `available_skills_prompt(allowed_skills=agent.allowed_skills if agent else None)`。
- **run_sync**（CLI）：无 agent 绑定，`available_skills_prompt()` 维持无参（None = 不收窄），与 CLI 暴露全部内置工具的「无 per-agent 授权」口径一致。

**为何**：复用既有透传骨架（`agent.features` → `agent_features`）；catalog 在哪构建就在哪施加收窄，避免在 run() 内重复过滤已组装好的 system prompt。
**Alternatives**：在 run() 内统一重建 catalog——被否，run() 收到的是预组装 messages，重建会改变 system prompt 组装时机与缓存前缀；让所有调用方都走 run_stream——被否，normalizer 用 run()（含审批门），非流式路径不可替换。

### D5：非授权——不动 tool 访问控制与按名 load
`allowed_skills` 只过滤 `available_skills_prompt` 的清单输出。不改 `agent_policy.check_tool_access`、不改 `read_skill` 工具的 `skill_registry.load(name)`（按名 load 仍读任意已注册 skill 的 SKILL.md）。即：被收窄掉的 skill，模型在 `<available_skills>` 里看不到、不会主动 `read_skill` 它，但若有别的渠道得到其名仍能 load——这与既有「load 不受禁用约束」一致，因为真正的能力门是 `allowed_tools` + 审批，而非 skill 可见性。

**为何**：项目铁律「skill 不是授权边界，tool 才是」。把 `allowed_skills` 做成 load 的硬门会与该原则冲突、并和 `_disabled_reason`（同样不挡 load）行为分叉。收窄定位为「降低无关 skill 进上下文的噪音 + 默认不主动读」，而非安全边界。
**Alternatives**：让 `load` 也校验 `allowed_skills`——被否，违反「skill 非授权边界」原则，且 `load` 是无 agent 上下文的纯函数，强加校验需把 agent 透传进 read_skill dispatch，越界。

## Risks / Trade-offs

- [`allowed_skills` 与 `plugins` 语义相反（空 = 不限制 vs 空 = 无）可能让维护者混淆] → 字段 docstring、spec 需求、决策记录三处显式标注不对称及其理由（默认态相反）；测试用例分别锁定两者默认行为。
- [run() 加了 `allowed_skills` 入参但现状不施加过滤，可能被误读为「无效参数」] → docstring 标注「catalog 由调用方预组装；该入参为 API 对称与未来 run()-内建 catalog 路径预留，现状不重复过滤」；测试只断言 run_stream / normalizer 的真实过滤，不对 run() 断言重复过滤。
- [收窄叠加在 `_disabled_reason` 过滤点，若将来禁用谓词重构需同步] → 收窄是该点的额外 AND 条件，不改谓词内部；`collect_disabled_trace` 仍跑全 index（只记禁用、不记收窄），两者关注点分离，互不影响。
- [`collect_disabled_trace` 不记录「因收窄被排除」的 skill] → 这是有意的：trace 记录的是「被禁用」（四来源）而非「未分配」；收窄不是禁用。若未来需审计「被收窄」可另加 trace 字段，本 change 不做（Non-Goal）。

## Migration Plan

- 加列经 alembic 004（`op.add_column`），旧 `agents` 行取 `server_default="[]"`，读取兜底 `or "[]"` → `[]`，行为不变（空 = 不限制 = 现状全可见）。
- 无数据回填需求；无回滚风险（004 `downgrade` 为 `op.drop_column("agents", "allowed_skills")`）。fresh / test 库经 `_init_db` 内联列直接就位。

## Open Questions

无。CLI（run_sync）是否需要支持 per-agent 收窄：现状 CLI 无 agent 绑定、暴露全部内置工具，故维持 None（不收窄），与既有口径一致；若未来 CLI 引入 agent 选择，再在 run_sync 取 `agent.allowed_skills` 传入即可，骨架已就位。

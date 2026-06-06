## Context

`SkillEntry` 字段 + `_scan_dir` 解析 frontmatter。`_disabled_reason` 是唯一的 catalog eligibility predicate（scan 期已定的禁用源），`available_skills_prompt` 用它过滤。`read_skill` 只查 `audit_blocked`，不查 `_disabled_reason`——故 catalog 隐藏 ≠ read_skill 拒绝。loop.py 两处调 `available_skills_prompt(allowed_skills=...)`，且这两处 `allowed_tools` 在 scope。

## Goals / Non-Goals

**Goals:**
- `disable_model_invocation`：catalog 隐藏，read_skill 仍可达
- `requires_tools`：渲染期按当前会话可用工具集过滤 catalog
- `required_env_vars`：解析 + readiness helper（不阻塞 catalog）
- 三字段全向后兼容默认值

**Non-Goals:**
- 不做 admin console readiness 前端（只提供后端 `skill_readiness`）
- `requires_tools` 不做模糊/pattern 匹配（精确工具名）
- 不引入 `metadata.fleetent` 嵌套块（直接顶层字段，更简单；未来如需命名空间再迁移）

## Decisions

### D1：`disable_model_invocation` 经 `_disabled_reason` 隐藏，read_skill 天然可达

在 `_disabled_reason` 加分支返回 `"model_invocation_disabled"`，优先级置于 `audit_blocked` 之后、`frontmatter_disabled` 之前（它是比 enabled:false 更"软"的作者意图——隐藏但仍可组合调用，语义上先于其他禁用源表达）。`read_skill` 不查 `_disabled_reason`（只查 audit_blocked），故自动仍可按名加载——无需改 read_skill。`collect_disabled_trace` 会如实记录该原因（正确，它确实被隐藏）。

### D2：`requires_tools` 渲染期过滤，不进 `_disabled_reason`

工具可用性每会话可变（sandbox 开关、MCP 健康），不能在 scan 期定。`available_skills_prompt` 加 `available_tools: set[str] | None = None`：None 不过滤（兼容）；非 None 时，skill 的 `requires_tools` 有任一不在 `available_tools` 则该 skill 不渲染。与 `_disabled_reason`（scan 期禁用源）正交，分两层。

### D3：loop.py 传 available_tools = agent 实际可用工具名集

两处调用点（run_sync / run_stream）的 `allowed_tools` 在 scope。传 `_visible_tool_names(allowed_tools)` = `{schema name for s in get_schemas() if allowed_tools is None or check_tool_access(name, allowed_tools)}`——与实际暴露给模型的工具集同源，使 requires_tools 检查精确对齐"agent 真能调的工具"。

### D4：`required_env_vars` 仅元数据 + readiness helper，不阻塞 catalog

env 缺失不应让 skill 从 catalog 消失（模型可能正是要 read 它来了解如何配置）。存 `required_env_vars` 于 SkillEntry；`skill_readiness(name) -> {"missing": [...]}` 检查每项非 `optional` 的 `name` 是否在 `os.environ`。供 admin console 调用，运行时 catalog 不受影响。

### D5：字段解析复用现有 normalizer 风格

`disable_model_invocation`：`bool(frontmatter.get(..., False))`。`requires_tools`：`_as_str_list`。`required_env_vars`：取 list[dict]，每项保留 `name`/`optional`，非 mapping 项跳过。

## Risks / Trade-offs

**[Risk] disable_model_invocation 的 skill 仍可被 read_skill 读 → 是否泄漏**
→ 设计如此：它是"不主动暴露给模型发现"而非"安全封禁"。安全封禁是 `audit_blocked`（read_skill 会拒）。两者正交、各司其职。

**[Risk] requires_tools 与 allowed_tools fnmatch 的对齐**
→ D3 用 `check_tool_access` + `get_schemas` 同源计算可见集，与模型实际可调工具一致；requires_tools 用精确名匹配该集合，无歧义。

**[Risk] available_tools=None（默认/未传）时 requires_tools 不生效**
→ 兼容性优先：仅当调用方显式传入工具集时过滤。loop.py 会传；其他调用方（如纯渲染测试）不传则不过滤，行为保守不破坏。

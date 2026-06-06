## Context

`_scan_dir(base, index, errors, *, builtin)` 先扫 `BUILTIN_SKILLS_DIR`（builtin=True）再扫 user dir（builtin=False），合并进同一 `index`。同名冲突当前：`if existing.path <= path: continue`——纯路径字典序，更小路径胜，不看来源。`SkillEntry.builtin` 已记录每个 entry 的来源（无需新字段）。

## Goals / Non-Goals

**Goals:**
- user skill 覆盖同名 builtin skill，与路径排序无关
- 同层级冲突保持既有路径字典序（SK8 不变）
- 冲突告警标注是否层级覆盖

**Non-Goals:**
- 不引入多于 2 层的 precedence（当前只有 builtin / user 两层）
- 不改 `SkillEntry` schema（复用 `builtin` 标志）
- 不改同层级解析规则

## Decisions

### D1：层级优先判定 `keep_existing = builtin`（当 tiers 不同）

冲突时，`existing` 是已索引项、新项的来源由 `builtin` 参数给出：
- tiers 不同（`existing.builtin != builtin`）：user 胜。
  - existing=builtin, 新=user（builtin=False）→ 新胜 → `keep_existing=False`（= `builtin`）
  - existing=user, 新=builtin（builtin=True）→ existing 胜 → `keep_existing=True`（= `builtin`）
  - 两种情形都满足 `keep_existing = builtin`，简洁。
- tiers 相同：`keep_existing = existing.path <= path`（既有规则）。

### D2：告警新增 `tier_override` 字段

`tier_override = existing.builtin != builtin`。运维可区分"user 覆盖 builtin"（预期）与"同层路径排序"（可能需排查重名）。

### D3：builtin 先扫，故跨层冲突时 existing 必为 builtin

实践中 user dir 后扫，跨层冲突时 `existing` 总是 builtin、新项是 user → user 覆盖。但 D1 的判定对两种到达顺序都正确（不依赖扫描顺序），与现有 SK8 的"顺序无关"测试保持一致。

## Risks / Trade-offs

**[Risk] 现有依赖"builtin 路径排序靠前故 builtin 胜"的隐式行为被改变**
→ 这正是要修的：之前 builtin 胜是路径排序的偶然结果，不是设计意图。改后 user 显式覆盖 builtin 是文档化语义。无测试依赖旧的跨层路径排序行为（现有 builtin 测试用不同名 skill，不触发冲突）。

**[Risk] 同名但都在 user 层的冲突仍按路径排序——可能仍不直观**
→ 超出本 change 范围；同层重名是 operator 配置错误，路径排序 + 告警已足够定位。

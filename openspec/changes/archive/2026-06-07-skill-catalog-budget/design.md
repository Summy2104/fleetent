## Context

`available_skills_prompt(disabled_skills, allowed_skills)` 过滤出 eligible entries 后，逐个渲染 `<skill><name><description><location>` 进 catalog，拼到 system prompt 稳定前缀。无上限。所有调用点用 keyword args，故新增 keyword 参数兼容。

## Goals / Non-Goals

**Goals:**
- catalog 受条数 + 字符双预算约束，防 system prompt 静默膨胀
- 超限时保留最大可发现性（compact fallback 而非直接砍掉）
- 截断时明确告知模型 catalog 不完整
- 默认值大到现有部署零影响

**Non-Goals:**
- 不引入 agent_config 字段（函数默认参数更简单；未来若需 per-agent 调可再加，YAGNI）
- 不改变 eligibility 过滤逻辑（disable/allowed 不变）
- 不对 description 做截断（compact 是全有或全无 description，避免半截描述误导）

## Decisions

### D1：函数默认参数承载预算，非 agent_config

`max_skills: int = 150`、`max_chars: int = 18000`。openclaw 同款数值。函数级默认最简单，调用点不变。未来需 per-agent 调节再提到 agent_config，当前无需求。

### D2：两级降级——先条数截断，再字符切 compact

1. eligible entries 按现有顺序，若 `len > max_skills`：截前 `max_skills` 个，记 `truncated=True`、`total=原数量`。
2. 渲染完整格式（含 description）；若总字符 > `max_chars`：改用 compact 格式（name+location，省 description）重渲染。
3. compact 仍 > `max_chars`：在 compact 下进一步按条数截断到拟合（保证产出始终 ≤ max_chars 附近，且至少给警告 + 能放下的条目）。

### D3：截断警告置于指令之前

`⚠ Skills: showing N of M (truncated)` 作为第一行，先于 `_SKILLS_INSTRUCTION`。模型先看到"列表不完整"再看 catalog，避免误以为已是全集。compact 模式额外标注（如 `(compact)`）。

### D4：稳定性——同输入同输出

截断取前 N 个，依赖 `_index` 的迭代顺序（dict 插入序，scan 确定性）。同一 skill 集合渲染结果稳定，保持 prompt cache 友好。

## Risks / Trade-offs

**[Risk] 截断丢失的 skill 模型不可见 → 无法 read_skill**
→ 可接受且有缓解：截断只在 skill 数 > 150 时触发（远超当前规模）；警告告知模型 catalog 不完整；read_skill 仍可按名加载未列出的 skill（catalog 是发现层，非授权边界）。这正是"无声截断"风险的反面——本 change 把无声变有声。

**[Risk] compact 模式模型缺 description 难判断该读哪个**
→ 权衡：compact 只在 catalog 已超 18000 字符（极大库）时触发，此时完整 description 本就吃光预算；保留 name+location 至少维持可发现性，优于整体截断更多条目。

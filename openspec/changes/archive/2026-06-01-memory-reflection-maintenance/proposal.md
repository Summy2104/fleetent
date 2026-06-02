## Why

`reflection-foundation` 目前只生成只读 report，不自动修改 memory。旧规划里曾提到 memory reflection 后续可以
“直接写回（自动维护）”，但这个边界对 User Memory 不安全：当前 memory-layer 是 per-user semantic memory，
owner 是用户本人，reflection 不能默认替用户合并、改写或删除长期记忆。

同时，我们已经明确 Memory 是能力域，不等于当前 `memory_layer` 的全部未来形态。当前已实现的是 User Memory；
未来可能有 Shared Memory，但它应作为 sibling capability 独立设计，不应通过把 team / tenant 内容塞进
`memory_items.user_id` 来实现。

本 change 定义 User Memory 的 reflection maintenance lifecycle：reflection 可以生成维护建议，但真正改变
User Memory 必须经过 memory owner 确认，或用户显式开启的低风险自动维护策略。

## What Changes

- 将当前 `memory_layer` 在文档和 spec 中明确为 User Memory。
- 增加 memory maintenance proposal lifecycle：
  - `pending`
  - `approved`
  - `rejected`
  - `applied`
  - `expired`
- 支持 reflection 生成 User Memory maintenance proposals，但默认不直接修改 memory。
- proposal 归属到 `user_id`，确认主体默认是 memory owner。
- 定义三类确认入口：
  - 交互中轻量确认：当前对话自然相关时，向用户确认 update / merge / mark stale 等动作。
  - 主动 review：用户请求“整理我的记忆”时批量查看 pending proposals。
  - 显式自动维护策略：用户开启后，只允许低风险动作自动 apply。
- 定义 maintenance action 风险边界：
  - 低风险：添加 metadata 标记、生成 proposal、标记候选状态，不改变 memory content。
  - 中风险：merge、rewrite、compact、mark stale，需要 owner approval，除非用户显式开启对应自动策略。
  - 高风险：delete、跨用户影响、低置信度冲突处理，必须 owner approval。
- 如果 reflection 发现某条内容更像团队共识、项目惯例、客户背景或组织运行经验，只能生成“建议迁移到 Shared Memory
  或 KB”的 proposal，不写入 User Memory。

## Out of Scope

- 不实现 Shared Memory 表、provider、权限模型或检索逻辑。
- 不把 `memory_items` 泛化成 `scope_type + scope_id`。
- 不做 team / tenant shared memory maintenance。
- 不做完整 UI、后台管理员审批台或 CI 审批流。
- 不允许管理员默认替用户确认 User Memory 修改。
- 不做 skill proposal 或 knowledge-base reflection apply。
- 不做 LLM 无确认地改写、合并或删除 User Memory。

## Module Boundary Impact

- **Owning package**：`intelligence.reflection` 负责 proposal lifecycle；`intelligence.memory_layer` 负责 User Memory mutation API。
- **Public API surface**：新增 memory maintenance proposal dataclasses 和 query / approve / reject / apply API；
  memory-layer 可能需要暴露受控的 user-memory update / merge / delete public API。
- **Owned tables**：新增 reflection-owned maintenance proposal 表；不修改 `memory_items` schema，除非实现阶段证明需要最小 metadata 字段。
- **Config namespace**：`reflection.memory_maintenance.*`，可选读取 `memory.*` 低风险自动维护策略。
- **Cross-module dependencies**：reflection 通过 memory-layer public API 应用已批准 proposal；observability 可记录 proposal
  created / approved / rejected / applied events。
- **Migration / shim plan**：现有 `run_reflection(scope)` 继续只生成 report；maintenance proposal API 为新增能力。

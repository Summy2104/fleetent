## Context

当前 memory-layer 是 per-user semantic memory：

- 表结构以 `user_id` 为 scope。
- vector namespace 是 `mem:{user_id}`。
- extraction snapshot 只包含当前用户记忆。
- update / delete 只允许作用于当前用户 snapshot 内的合法 `target_id`。

因此，reflection maintenance 的默认 owner 必须是该 `user_id` 对应的用户本人。管理员或 operator 可以维护系统，
但不应该默认替用户确认 User Memory 的内容修改。

同时，Memory 作为能力域应该预留 Shared Memory 的未来空间：

- User Memory：当前已实现，归属单个用户。
- Shared Memory：未来 sibling capability，可能归属 tenant / team / project / agent scope。
- Knowledge Base：正式文档、制度、流程和企业资料，按 tenant + kb 隔离。

本 change 只处理 User Memory。Shared Memory 不在本 change 实现，也不通过改造 `memory_items.user_id` 模拟。

## Proposal Lifecycle

reflection 生成 memory maintenance proposal，proposal 自身不改变 memory。

状态：

- `pending`：已生成，等待确认或自动策略处理。
- `approved`：owner 已确认可执行。
- `rejected`：owner 拒绝执行。
- `applied`：已成功写入 User Memory。
- `expired`：proposal 过期或对应 memory 已不存在，不再可执行。

proposal 至少包含：

- proposal id
- user_id
- action type
- target memory ids
- proposed content / merged content / metadata patch
- risk level
- reason
- evidence ids
- status
- created_at / updated_at / expires_at

## Action Types

MVP 建议支持这些动作：

- `mark_stale`：建议某条 context memory 已过期或不再可靠。
- `merge`：建议把多条重复或高度相似 memory 合并。
- `rewrite`：建议把一条 memory 改写成更清楚、更稳定的表述。
- `compact`：建议把多条长期背景压缩成更短摘要。
- `delete`：建议删除明显错误或用户已明确要求忘记的 memory。
- `suggest_shared_memory_or_kb`：发现内容更像团队共识、项目惯例、客户背景或正式知识时，只建议迁移，不写 User Memory。

## Confirmation Timing

确认入口分三类。

### 交互中轻量确认

当当前对话自然暴露出 memory 修正需求时，agent 可以在回答完成后追加轻量确认。例如用户纠正了身份、偏好或当前项目状态，
agent 可以询问是否更新对应记忆。

约束：

- 不在任务回答前打断。
- 不在一次回复中堆叠大量确认。
- 只用于当前对话证据足够明确的 proposal。
- high-risk `delete` 仍必须明确展示影响后确认。

### 主动 review

用户主动要求整理记忆时，系统列出 pending proposals，允许用户批量 approve / reject。

适合：

- merge
- compact
- stale cleanup
- 多条冲突记忆复核

### 显式自动维护策略

用户可以显式开启低风险自动维护策略。默认关闭。

允许自动 apply 的范围必须窄：

- 只处理 low-risk proposal。
- 不删除 memory。
- 不跨 user。
- 不处理低置信度冲突。
- 每次 apply 必须可被 observability 记录。

## Risk Model

低风险：

- 生成 proposal。
- 给 proposal 标记类别或置信度。
- 标记候选 stale，但不影响默认检索注入。

中风险：

- merge。
- rewrite。
- compact。
- 将 stale 标记变成影响检索或注入的状态。

高风险：

- delete。
- 低置信度冲突处理。
- 用户未明确表达的 identity 修改。
- 任何跨用户或疑似 shared memory 的动作。

## Ownership

User Memory proposal 的 owner 是 `user_id`。默认只有该用户可以 approve / reject / apply。

如果企业未来需要代理确认或合规治理，应作为单独 governance policy 设计；本 change 不默认允许管理员替用户确认。

## Shared Memory Boundary

如果 reflection 发现候选内容更像团队共识、项目惯例、客户背景或组织运行经验：

- 不写入 User Memory。
- 不创建 Shared Memory，因为该能力尚未实现。
- 可以生成 `suggest_shared_memory_or_kb` proposal。
- proposal 应解释为什么它不属于 User Memory，并建议未来进入 Shared Memory 或当前 KB。

## Testing

测试重点：

- proposal 生成不修改 `memory_items`。
- proposal 必须绑定 `user_id`。
- 未 approve 的 proposal 不可 apply。
- rejected / expired proposal 不可 apply。
- high-risk proposal 不能自动 apply。
- 用户显式低风险自动策略只影响 low-risk proposal。
- `suggest_shared_memory_or_kb` 不写 User Memory。
- apply 只通过 memory-layer public API，不直接写 `memory_items`。

## Non-Goals

本 change 不解决：

- Shared Memory 的实体、权限和检索设计。
- KB 写回或文档修改。
- skill proposal apply。
- UI 交互细节。
- permission_gate 的通用人机审批框架。

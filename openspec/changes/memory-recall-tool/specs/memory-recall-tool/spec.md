## ADDED Requirements

### Requirement: 全量记忆列举接口

`memory` SHALL 提供 `list_active_facts(user_id, subject=None)`，直接查库返回该 user_id 名下全部 `status='active'` 的 facts，按写入时间排序。该接口 MUST NOT 走向量检索、MUST NOT 截断（无 top-N limit）、MUST NOT 产生 access 计数或升级等副作用。传入 `subject` 时仅返回该 subject 的 facts；为 None 时返回该 user_id 名下所有 subject。

#### Scenario: 返回某用户全部 active facts

- **WHEN** 某 user_id 名下有 11 条 active facts（含 user 本人、agent、第三方多个 subject）
- **THEN** `list_active_facts(user_id)` 返回全部 11 条，不截断、不漏

#### Scenario: 按 subject 过滤

- **WHEN** 调用 `list_active_facts(user_id, subject="张三")`
- **THEN** 仅返回 subject 为 "张三" 的 active facts，其他 subject 的不返回

#### Scenario: 不返回非 active

- **WHEN** 某 user_id 名下有 active、archived、retracted、superseded 混合的 facts
- **THEN** `list_active_facts` 只返回 active 的，其余状态不出现

#### Scenario: 无记忆返回空列表

- **WHEN** 某 user_id 名下没有任何 active fact
- **THEN** `list_active_facts(user_id)` 返回空列表，不抛异常

### Requirement: agent 记忆查看工具

系统 SHALL 提供 agent 工具 `recall_memory(subject=None)`，使 agent 在用户要求查看/列出记忆时主动读取并完整呈现。工具按当前会话执行身份（`ToolContext.principal.user_id`）取记忆，不由模型传 user_id。工具 MUST NOT 抛异常：身份缺失或后端未接线时返回友好提示文本。

#### Scenario: 列出全部记忆

- **WHEN** 用户要求"列出我的所有记忆"，agent 调用 `recall_memory()`（subject 为空）
- **THEN** 工具返回该用户名下所有 subject 的 active facts（按 subject 分组的可读文本），不漏第三方实体

#### Scenario: 查看某个人的记忆

- **WHEN** 用户问"你记得张三什么"，agent 调用 `recall_memory(subject="张三")`
- **THEN** 工具仅返回 subject 为 "张三" 的记忆

#### Scenario: 身份缺失时不抛

- **WHEN** `ToolContext.principal` 为 None（如无身份的 CLI 运行）
- **THEN** 工具返回说明性文本（无法确定当前用户），不抛异常

#### Scenario: 无记忆时的提示

- **WHEN** 当前用户名下没有任何 active 记忆
- **THEN** 工具返回"暂无记忆"类提示，而非空字符串或报错

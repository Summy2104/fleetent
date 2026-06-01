## ADDED Requirements

### Requirement: 压缩前纯规则清理预处理

压缩 SHALL 在进入 LLM 摘要之前，对待摘要内容执行一道纯规则清理预处理。该清理 MUST 为毫秒级本地操作，MUST NOT 调用 LLM，且 MUST NOT 修改输入（产出新的清理后序列）。清理后的消息序列 MUST 对 LLM 合法。

#### Scenario: 清理在摘要前执行且不调 LLM
- **WHEN** 压缩确定待摘要内容并进入摘要前
- **THEN** 先执行纯规则清理，清理过程中不发起任何 LLM 调用

#### Scenario: 清理产出合法序列
- **WHEN** 清理处理完待摘要内容
- **THEN** 产出的消息序列对 LLM 合法，随后才交给摘要阶段

### Requirement: 图片与二进制占位块兜底替换

清理 SHALL 把消息 content list 内的图片 / 二进制占位块替换为简短文本占位 `[图片：{尺寸}]`，消除原始 base64 / 二进制内容在构造摘要输入时（经对整条 content 的字符串化）造成的膨胀。当尺寸元数据缺失时，清理 MUST 使用兜底值仍产出合法的文本占位，MUST NOT 因缺失元数据而崩溃。

#### Scenario: 图片块替换为文本占位
- **WHEN** 待摘要内容的某条消息 content list 含图片 / 二进制占位块
- **THEN** 该块被替换为 `[图片：{尺寸}]` 文本占位，摘要输入不再含原始 base64 / 二进制

#### Scenario: 尺寸元数据缺失时兜底占位
- **WHEN** 图片块缺少尺寸元数据
- **THEN** 用兜底值生成合法的文本占位，不报错

### Requirement: 重复工具调用去重

清理 SHALL 对「工具名相同 + 调用参数相同 + 结果相同」的 tool_call / tool_result 对，只保留最新一条，删除更早的等价重复。当工具名、参数或结果中任一项不同时，清理 MUST NOT 去重。去重的判等与删除单位为 tool_call **block 粒度**（一条 assistant 消息可含多个 tool_call block，分别对应多条 tool_result）：仅当某条 assistant 消息的全部 tool_call block 都能在更新位置找到等价重复时，清理 MAY 删除整条消息及其全部 tool_result；否则 MUST 保留该消息及其未被去重的 block。去重 MUST 保持序列合法：保留的 tool_call 与其 tool_result 成对保留，MUST NOT 产生孤立的 tool_result。

#### Scenario: 等价重复只留最新
- **WHEN** 待摘要内容含同工具、同参数、同结果的多次工具调用对
- **THEN** 只保留最新一条，更早的等价重复被删除

#### Scenario: 同消息多 tool_use 部分等价不整删
- **WHEN** 一条 assistant 消息含多个 tool_call block，其中仅部分 block 在更新位置有等价重复
- **THEN** 保留该 assistant 消息，不按消息粒度删除非重复 block，且不产生孤立 tool_result

#### Scenario: 结果不同不去重
- **WHEN** 两次工具调用工具名与参数相同但结果不同
- **THEN** 两次调用均保留，不被去重

#### Scenario: 参数不同不去重
- **WHEN** 两次工具调用工具名相同但参数不同
- **THEN** 两次调用均保留，不被去重

#### Scenario: 去重不产生孤立结果
- **WHEN** 去重删除某个等价重复的工具调用
- **THEN** 其对应的 tool_result 一并删除，不留下孤立的 tool_result，序列对 LLM 合法

### Requirement: 清理不改变触发与目标线语义

压缩在进入摘要前 SHALL 先执行纯规则清理（content 内图片占位替换、等价重复工具调用去重），清理后的内容再用于摘要与目标线达成判定。清理 MUST NOT 改变 `Tmax` 触发判定与 `Tretained` 目标线语义，仅瘦身待摘要内容。

#### Scenario: 清理不改变触发与目标线语义
- **WHEN** 压缩在摘要前执行纯规则清理
- **THEN** `Tmax` 触发判定与 `Tretained` 目标线语义不变，清理仅瘦身待摘要内容

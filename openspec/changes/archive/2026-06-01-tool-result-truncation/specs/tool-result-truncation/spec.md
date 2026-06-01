## ADDED Requirements

### Requirement: 超阈值工具结果写入消息前被截断

工具结果在写回 `messages`（占用上下文的 `tool` 角色消息）之前，当其大小超过字节阈值时 SHALL 被截断；截断后写入 `messages` 的内容 MUST NOT 超过该字节阈值。大小度量 MUST 采用 UTF-8 字节口径 `len(s.encode("utf-8"))`，与沙箱输出截断（SB6）的字节口径一致。截断 MUST NOT 调用 LLM（纯规则、毫秒级）。

> 归属说明：本需求首次以 spec 表达 docs 规划项「工具结果截断」，落在本 change 的新 capability `tool-result-truncation` 下以 ADDED 表达。它是工具层通用结果截断，管所有【其他】工具；沙箱 `run_code` 输出的特化截断由 SB6（`sandbox-output-truncation`）**独占**，`run_code` 经 `self_truncates` opt-out 对本能力**豁免**（见下方「自截断工具…豁免」需求）。两者字节口径一致仅为跨 change 度量惯例，各管各的工具、不叠加、无数值耦合。

#### Scenario: 结果超过阈值被截断
- **WHEN** 某工具返回的结果字节数超过阈值
- **THEN** 写入 `messages` 的 `tool` 消息内容被截断，其字节数不超过阈值

#### Scenario: 结果在阈值内原样保留
- **WHEN** 某工具返回的结果字节数不超过阈值
- **THEN** 写入 `messages` 的 `tool` 消息内容与原始结果完全一致，不被修改

#### Scenario: 字节口径与 SB6 一致
- **WHEN** 判断结果是否超阈值
- **THEN** 以 `len(s.encode("utf-8"))` 计算字节数（与沙箱输出截断 SB6 同口径），不按字符数或 token 计

### Requirement: 截断采用头尾保留并插入 breadcrumb

截断 SHALL 采用「头部保留 + 中间省略 + 尾部保留」策略：保留结果的开头与结尾各一段，中间被省略的部分 MUST 由一条 breadcrumb 占位标记替换。breadcrumb MUST 标明原始字节数与被省略的字节数，使 LLM 可知结果不完整及被省略的规模。头部预算、尾部预算与 breadcrumb 之和 MUST NOT 超过字节阈值。

#### Scenario: 截断结果保留头尾并含 breadcrumb
- **WHEN** 一个远超阈值的结果被截断
- **THEN** 写入 `messages` 的内容以原始头部开始、以原始尾部结束，中间含一条标明原始字节数与省略字节数的 breadcrumb 占位

#### Scenario: 截断后总大小不反超阈值
- **WHEN** 头尾保留与 breadcrumb 组合后写入 `messages`
- **THEN** 该 `tool` 消息内容的字节数不超过阈值（头 + 尾 + breadcrumb 已在预算内）

### Requirement: 多字节字符不被截断破坏

按 UTF-8 字节切分头尾时，切点 MUST NOT 落在多字节字符中段；若字节预算边界落在某字符内部，切点 SHALL 回退到上一个完整字符边界。截断后的内容 MUST 为合法 UTF-8 字符串。

#### Scenario: 字节边界落在多字节字符内回退
- **WHEN** 头部或尾部字节预算的边界恰好落在一个多字节字符（如中文）的中间
- **THEN** 切点回退到该字符之前的完整边界，截断结果为合法 UTF-8，不含半个字符

### Requirement: 字节阈值可注入且未配置时回退安全默认

字节阈值 SHALL 来自可注入的单一事实来源（模块级常量，测试可 `monkeypatch`），未显式配置时 MUST 回退到安全默认值。截断函数 SHALL 支持按次传入阈值覆盖默认值。系统 MUST NOT 依赖全局可变状态来持有阈值。

#### Scenario: 未配置取安全默认
- **WHEN** 调用截断且未传入阈值
- **THEN** 使用模块级安全默认阈值进行判断与截断

#### Scenario: 按次传入阈值覆盖默认
- **WHEN** 调用截断时显式传入一个更小的阈值
- **THEN** 以传入阈值判断与截断，不使用默认阈值

### Requirement: 截断只作用于消息副本不削减完整结果来源

截断 SHALL 只作用于写入 `messages`（占上下文）的内容副本；工具 `dispatch()` 的原始返回值 MUST NOT 被本能力修改。trace 通过序列化 `messages` 落盘，而截断发生在 `messages.append` 之前，故 trace 记录的即是 LLM 实际所见的截断内容；breadcrumb 标明的原始字节数与省略字节数即审计所需的大小元数据（符合 `eval_logger`「只记元数据/样本、不落原始大对象」的既有克制原则）。

#### Scenario: dispatch 返回值不被截断
- **WHEN** 工具结果超阈值并在写回 `messages` 前被截断
- **THEN** `dispatch()` 的原始返回值保持完整不变（去重摘要、SSE 事件等下游消费者看到的仍是原始结果）

#### Scenario: trace 记录的是截断后内容
- **WHEN** 一次包含超大工具结果的运行被写入 trace
- **THEN** trace 序列化的 `messages` 中工具结果为已截断内容（与 LLM 实际所见一致），breadcrumb 标明的原始字节数与省略字节数提供审计所需的大小元数据

### Requirement: 自截断工具对工具结果截断豁免

工具 SHALL 可声明自身负责截断输出（通过 `@tool(self_truncates=True)`，该元数据与 `risk_level` / `connector` 等平行存放于 `tool_registry`、MUST NOT 进入 LLM-facing schema）。对已声明 `self_truncates=True` 的工具，本能力（工具结果通用截断）在写回 `messages` 前 SHALL **跳过**截断、原样写回其结果，由该工具的专门截断器负责其输出截断。沙箱 `run_code` MUST 声明 `self_truncates=True`，其 stdout/stderr 输出由 SB6（`sandbox-output-truncation`）独占截断，本能力 MUST NOT 对 `run_code` 结果施加本能力的字节阈值或二次截断。本能力的默认字节阈值 MUST NOT 为迁就单一工具（如 `run_code` 的沙箱输出上限之和）而抬高，以保持工具层通用阈值帽。

> 设计要点：`run_code` 既是「工具」又是「sandbox 输出」，被工具结果上限与 sandbox 输出上限同时覆盖；更具体的 sandbox 上限（SB6）对 `run_code` 生效。本豁免使两者**各管各的工具、不叠加、无数值耦合**——不存在「本能力阈值须 ≥ SB6 两流之和」的脆弱约束。`self_truncates` 是「per-tool 阈值」的退化版（对声明工具直接无本能力上限）。

#### Scenario: run_code 声明 self_truncates 故被跳过不截
- **WHEN** `run_code`（已声明 `self_truncates=True`）返回的结果写回 `messages`
- **THEN** 本能力跳过对该结果的截断，原样写回（其输出已由 SB6 独占截断），本能力不对它施加字节阈值

#### Scenario: 未声明 self_truncates 的工具仍受本能力截断
- **WHEN** 一个未声明 `self_truncates`（即默认 `False`）的工具返回超阈值结果
- **THEN** 本能力照常对其截断（头尾保留 + breadcrumb，不超过字节阈值）

#### Scenario: self_truncates 元数据不进入 LLM schema
- **WHEN** 构建提供给 LLM 的工具 schema
- **THEN** `self_truncates` 不出现在 schema 中（与 `risk_level` / `connector` 等平行元数据同范式）

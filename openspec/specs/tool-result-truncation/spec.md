# tool-result-truncation Specification

## Purpose
TBD - created by archiving change tool-result-truncation. Update Purpose after archive.
## Requirements

### Requirement: 超阈值工具结果写入消息前被截断

工具结果在写回 `messages`（占用上下文的 `tool` 角色消息）之前，当其大小超过字节阈值时 SHALL 被截断；截断后写入 `messages` 的内容 MUST NOT 超过该字节阈值。大小度量 MUST 采用 UTF-8 字节口径 `len(s.encode("utf-8"))`，与沙箱输出截断（SB6）的字节口径一致。截断 MUST NOT 调用 LLM（纯规则、毫秒级）。字节阈值 SHALL 为 **50,000 字节**（由原 40,000 字节调整）。

> 归属说明：本需求更新截断阈值从 40,000 字节升至 50,000 字节，并新增溢出文件行为（见下方「溢出文件」需求）。`run_code` 经 `self_truncates` opt-out 对本能力豁免（`bash_exec` 同理）。

#### Scenario: 结果超过阈值被截断
- **WHEN** 某工具返回的结果字节数超过 50,000 字节
- **THEN** 写入 `messages` 的 `tool` 消息内容被截断，其字节数不超过 50,000 字节

#### Scenario: 结果在阈值内原样保留
- **WHEN** 某工具返回的结果字节数不超过 50,000 字节
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

### Requirement: 超阈值时将完整结果写入溢出文件

当工具结果超过截断阈值时，完整原始结果 SHALL 被写入溢出文件（路径：`data_dir() / "tool_spillover" / "{uuid4}.txt"`），文件内容为原始字符串的 UTF-8 编码。写入操作 MUST 在返回截断结果给 LLM 之前完成。self_truncates 工具豁免于溢出文件写入。

#### Scenario: 超阈值时溢出文件被创建
- **WHEN** 工具结果超过 50,000 字节
- **THEN** `data_dir()/tool_spillover/` 下创建一个 UUID 命名的 `.txt` 文件，内容为完整原始结果

#### Scenario: self_truncates 工具不写溢出文件
- **WHEN** 声明了 `self_truncates=True` 的工具（如 `run_code`、`bash_exec`）返回超阈值结果
- **THEN** 不写入溢出文件（工具自身已处理截断）

### Requirement: 截断结果包含溢出文件路径和分段读取提示

当结果被截断时，返回给 LLM 的内容 SHALL 包含：前 100 行（而非 head 字节）作为 preview；溢出文件的完整路径；以及使用 `read_file(path="...", offset=N, limit=200)` 分段读取的指引。原有 breadcrumb（原始字节数/省略字节数）可保留作为补充信息。

#### Scenario: 截断结果含文件路径和读取提示
- **WHEN** 工具结果超过阈值被截断
- **THEN** 返回内容包含前 100 行 preview、溢出文件路径、`read_file(path="...", offset=N)` 使用提示

#### Scenario: 预览行数以行为单位（非字节）
- **WHEN** 结果被截断时生成 preview
- **THEN** preview 包含原始内容的前 100 行完整文本，即使这 100 行超过 10KB 也完整保留

### Requirement: 溢出文件定期清理

`data_dir() / "tool_spillover"` 目录下超过 7 天的文件 SHALL 定期被删除；清理任务 SHALL 通过现有 `cron_scheduler` 注册为每日执行的维护任务，在应用启动时注册。

#### Scenario: 7 天前的溢出文件被清理
- **WHEN** 每日清理任务执行
- **THEN** `tool_spillover/` 目录下 mtime 超过 7 天的文件被删除

#### Scenario: 7 天内的溢出文件保留
- **WHEN** 每日清理任务执行
- **THEN** mtime 在 7 天内的文件不被删除

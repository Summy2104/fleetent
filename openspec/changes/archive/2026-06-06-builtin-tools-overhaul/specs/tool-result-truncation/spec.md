## MODIFIED Requirements

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

## ADDED Requirements

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

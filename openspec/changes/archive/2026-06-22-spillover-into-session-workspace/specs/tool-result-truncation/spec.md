## MODIFIED Requirements

### Requirement: 超阈值时将完整结果写入溢出文件

当工具结果超过截断阈值时，完整原始结果 SHALL 被写入溢出文件（内容为原始字符串的 UTF-8 编码），写入 MUST 在返回截断结果给 LLM 之前完成。溢出文件位置：当存在 session workspace（截断在已知 run 的 workspace 上下文中发生）时，SHALL 写入该 workspace 的 `.fleetent_spillover/{uuid4}.txt` 子目录，使 `read_file` 能在围栏内读回；无 session workspace 时回退全局 `data_dir() / "tool_spillover" / "{uuid4}.txt"`。self_truncates 工具豁免于溢出文件写入。

#### Scenario: 有 workspace 时溢出落 workspace 子目录
- **WHEN** 工具结果超过阈值，且截断时提供了 session workspace 目录
- **THEN** 在 `<workspace>/.fleetent_spillover/` 下创建 UUID 命名的 `.txt` 文件，内容为完整原始结果

#### Scenario: 无 workspace 时回退全局目录
- **WHEN** 工具结果超过阈值，但无 session workspace 上下文
- **THEN** 在 `data_dir()/tool_spillover/` 下创建 UUID 命名的 `.txt` 文件（向后兼容）

#### Scenario: self_truncates 工具不写溢出文件
- **WHEN** 声明了 `self_truncates=True` 的工具（如 `run_code`、`bash_exec`）返回超阈值结果
- **THEN** 不写入溢出文件（工具自身已处理截断），采用头尾 breadcrumb 截断

### Requirement: 截断结果包含溢出文件路径和分段读取提示

当结果被截断时，返回给 LLM 的内容 SHALL 包含：前 100 行（而非 head 字节）作为 preview；溢出文件路径；以及使用 `read_file(path="...", offset=N, limit=200)` 分段读取的指引。当溢出文件写入 session workspace 时，提示中的路径 SHALL 为 **workspace 相对路径**（如 `.fleetent_spillover/{uuid}.txt`），使 `read_file` 在容器与宿主两种模式下都能解析并读回完整结果；回退全局目录时为该文件的绝对路径。原有 breadcrumb（原始字节数/省略字节数）可保留作为补充信息。

#### Scenario: workspace 溢出的提示用相对路径且可读回
- **WHEN** 工具结果超阈值、溢出写入 session workspace 的 `.fleetent_spillover/`
- **THEN** 返回内容含前 100 行 preview + workspace 相对路径（`.fleetent_spillover/{uuid}.txt`）+ `read_file(path="...", offset=N)` 提示；agent 据此 `read_file` 能读回完整内容（不再 `path escapes workspace`）

#### Scenario: 预览行数以行为单位（非字节）
- **WHEN** 结果被截断时生成 preview
- **THEN** preview 包含原始内容的前 100 行完整文本，即使这 100 行超过 10KB 也完整保留

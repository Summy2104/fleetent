## MODIFIED Requirements

### Requirement: 超预算输出落盘并返回引用替代中段丢弃

当 `run_code` 的某输出流（stdout 或 stderr）经脱敏后仍超过其字节预算时，SHALL 将**完整的脱敏后输出**写入落盘文件，返回值给出 head+tail 预览与文件引用（文件路径、原始字节数、以及「可用 `read_file` 读取完整内容」的提示），不再直接丢弃中段。未超预算时 SHALL 原样返回该流内容、不落盘。落盘内容 MUST 为脱敏后文本——密钥 MUST NOT 被写入磁盘。

Agent runtime 下默认落盘目录 SHALL be `<agent-home>/data/sandbox_output/`; tests or explicit injection MAY override it. The default SHALL NOT be `FLEETENT_HOME/data/sandbox_output/`.

#### Scenario: 未超预算不落盘
- **WHEN** 某流脱敏后字节数未超过其预算
- **THEN** 返回值与该流内容一致，不创建任何落盘文件

#### Scenario: 超预算落盘并返回引用
- **WHEN** 某流脱敏后字节数超过其预算，且当前进程是 agent runtime
- **THEN** 完整脱敏后输出被写入 `<agent-home>/data/sandbox_output/` 下的落盘文件
- **AND** 返回值包含该文件路径、原始字节数与 `read_file` 提示，并附 head+tail 预览
- **AND** 不创建 `FLEETENT_HOME/data/sandbox_output/`

#### Scenario: 落盘内容已脱敏
- **WHEN** 超预算的输出中含密钥（脱敏后落盘）
- **THEN** 落盘文件内容中不含原始密钥（与返回预览一致地被脱敏）

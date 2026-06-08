## MODIFIED Requirements

### Requirement: normalizer 从本轮工具结果提取生成图片路径

`route()` SHALL 在 `agent_loop.run()` 完成后，仅扫描本轮新增的 tool 消息（`role == "tool"`），从内容中匹配以下两种格式，提取已存在于磁盘的路径列表：

1. `generate_image` 工具：`"image generated: <path>"`
2. `write_file` 工具：`"written <N> bytes to <path>"`

路径不存在时跳过。提取到的路径列表传给 `upload_func`。

#### Scenario: 本轮 generate_image 路径被提取
- **WHEN** 本轮 tool 消息含 `"image generated: /path/to/img.png"` 且文件存在
- **THEN** 路径被提取，传给 `upload_func`

#### Scenario: 本轮 write_file 路径被提取
- **WHEN** 本轮 tool 消息含 `"written 42 bytes to /path/to/file.py"` 且文件存在
- **THEN** 路径被提取，传给 `upload_func`

#### Scenario: 历史 turn 的旧路径不被重复上传
- **WHEN** 历史 turn 中有 `generate_image` 或 `write_file` 结果，本轮未调用
- **THEN** 这些路径不被提取，不触发上传

#### Scenario: 路径不存在时跳过
- **WHEN** tool 消息含路径但文件不存在
- **THEN** 该路径被跳过，不进入 paths 列表

# builtin-file-tools Specification

## Purpose
文件系统工具集，提供分页读取（read_file）、精准编辑（edit_file）、内容搜索（search_content）和文件查找（search_files）能力，支持二进制检测、目录列举和多层 fallback 匹配。

## Requirements

### Requirement: read_file 支持行级分页读取
`read_file` SHALL 接受 `offset`（整数，1-indexed，起始行号，默认 1）和 `limit`（整数，最大读取行数，默认 200）参数，返回指定范围内的文件行，每行带行号前缀（宽度对齐至总行数位数）。当 `offset + limit < 总行数` 时，返回内容末尾 SHALL 附加提示，说明当前页范围、总行数，以及使用 `read_file(path, offset=N)` 继续读取的指引。

#### Scenario: 读取文件前 200 行
- **WHEN** 调用 `read_file(path="src/app.py")`（使用默认 offset=1, limit=200）
- **THEN** 返回文件第 1-200 行，每行带行号前缀，末尾附加分页提示（若文件超过 200 行）

#### Scenario: 从指定行开始分页读取
- **WHEN** 调用 `read_file(path="src/app.py", offset=201, limit=200)`
- **THEN** 返回文件第 201-400 行，带行号前缀

#### Scenario: 读取到文件末尾不附加提示
- **WHEN** `offset + limit >= 文件总行数`
- **THEN** 返回剩余行，不附加分页提示

### Requirement: read_file 支持目录列举
当 `path` 指向目录时，`read_file` SHALL 返回目录树形结构，每条目包含文件名、大小（人类可读格式）和最近修改时间；条目按 mtime 降序排列；超过 200 条时截断并附提示。

#### Scenario: 读取目录返回树形结构
- **WHEN** 调用 `read_file(path="src/fleetent/tools")`（path 为目录）
- **THEN** 返回该目录下文件和子目录列表，含文件大小和 mtime，按 mtime 降序

#### Scenario: 目录条目过多时截断
- **WHEN** 目录下条目超过 200 个
- **THEN** 返回前 200 条，末尾附加截断提示和总条目数

### Requirement: read_file 检测二进制文件并拒绝返回乱码
`read_file` 在读取文件前 SHALL 检测文件是否为二进制：通过 magic bytes（PNG/JPEG/GIF/PDF/ZIP/ELF 等常见格式）或非打印字符比例超过 30%（采样前 512 字节）判定为二进制。二进制文件 SHALL 返回明确错误提示（含检测到的类型），不返回乱码字节。

#### Scenario: 图片文件被检测为二进制
- **WHEN** 调用 `read_file(path="logo.png")`
- **THEN** 返回错误提示 `"error: 二进制文件 (image/png)，图片请使用 analyze_image 工具"`

#### Scenario: 普通文本文件正常读取
- **WHEN** 文件非打印字符比例 ≤ 30%
- **THEN** 正常返回文件内容，不触发二进制检测逻辑

### Requirement: edit_file 支持精准字符串替换
`edit_file` SHALL 接受 `path`、`old_string`、`new_string`、`replace_all`（bool，默认 False）参数，在文件中找到 `old_string` 并替换为 `new_string`；`replace_all=False` 时仅替换第一处，`replace_all=True` 时替换全部。替换后返回成功信息（含行号和使用的匹配层）。

#### Scenario: 精确匹配替换成功
- **WHEN** `old_string` 在文件中精确存在
- **THEN** 替换为 `new_string`，返回 `"替换成功（第 N 行，ExactReplacer）"`

#### Scenario: old_string 不存在时返回诊断
- **WHEN** 所有 6 层匹配均失败
- **THEN** 返回错误，说明尝试了 N 层匹配均失败，建议先用 `read_file` 确认实际内容

#### Scenario: replace_all 替换所有匹配
- **WHEN** `replace_all=True` 且文件中有多处 `old_string`
- **THEN** 所有出现处均被替换，返回替换次数

### Requirement: edit_file 应用 6 层 fallback 匹配策略
当精确匹配失败时，`edit_file` SHALL 依次尝试以下 fallback 层，第一层命中即停止：Layer 2 每行 strip 后比较；Layer 3 连续空白字符视为等价；Layer 4 CRLF/LF 归一化；Layer 5 移除公共缩进后比较；Layer 6 首行+尾行精确锚定、中间行 strip 后比较。每层命中时返回中的信息 SHALL 标明使用层编号。

#### Scenario: 缩进不一致时 Layer 2 命中
- **WHEN** `old_string` 与文件内容仅有尾部空格差异
- **THEN** Layer 2（LineTrimmedReplacer）命中并完成替换

#### Scenario: Tab/空格混用时 Layer 3 命中
- **WHEN** `old_string` 使用空格而文件内容使用 tab（或反之）
- **THEN** Layer 3（WhitespaceNormalizedReplacer）命中并完成替换

#### Scenario: Windows 换行文件 Layer 4 命中
- **WHEN** 文件使用 CRLF 换行而 `old_string` 使用 LF
- **THEN** Layer 4（LineEndingNormalizedReplacer）命中并完成替换

### Requirement: edit_file 防止无意义替换
`edit_file` SHALL 在 `old_string == new_string`（规范化后）时提前返回 no-op 结果，不修改文件。

#### Scenario: 相同内容不修改文件
- **WHEN** `old_string` 和 `new_string` 规范化后内容相同
- **THEN** 返回 `"no-op: old_string 与 new_string 内容相同，文件未修改"`

### Requirement: search_content 在文件中搜索正则模式
`search_content` SHALL 接受 `pattern`（正则表达式）、`path`（搜索目录或文件，默认 "."）、`include`（文件 glob 过滤，可选）、`max_results`（默认 100）参数；优先使用 ripgrep 后端，ripgrep 不可用时回退 Python `re`；返回格式为 `文件路径:行号:匹配行`，每行一条；结果数达到 `max_results` 时附加截断提示。

#### Scenario: 搜索代码中的函数定义
- **WHEN** 调用 `search_content(pattern="def read_file", path="src/")`
- **THEN** 返回所有包含 `def read_file` 的行，格式为 `src/fleetent/tools/file_tools.py:15:def read_file(path: str, ...)`

#### Scenario: 按文件类型过滤搜索
- **WHEN** 调用 `search_content(pattern="import", path=".", include="*.py")`
- **THEN** 只搜索 `.py` 文件，返回匹配行

#### Scenario: 结果超过上限时截断
- **WHEN** 匹配结果超过 `max_results`
- **THEN** 返回前 `max_results` 条，末尾附加 `"[截断：仅显示前 N 条，请用 include 参数缩小范围]"`

#### Scenario: ripgrep 不可用时回退 Python re
- **WHEN** 系统中没有 `rg` 二进制
- **THEN** 使用 Python `re` 模块执行搜索，返回相同格式结果

### Requirement: search_files 按 glob 模式查找文件
`search_files` SHALL 接受 `pattern`（glob 模式，如 `"**/*.py"` 或文件名子串）、`path`（搜索根目录，默认 "."）、`max_results`（默认 100）参数；结果按 mtime 降序排列；优先使用 ripgrep `--files` 后端，回退 `pathlib.rglob`。

#### Scenario: 按扩展名查找文件
- **WHEN** 调用 `search_files(pattern="**/*.py", path="src/")`
- **THEN** 返回 src/ 下所有 .py 文件路径，按最近修改时间降序

#### Scenario: 结果超过上限时截断
- **WHEN** 匹配文件数超过 `max_results`
- **THEN** 返回前 `max_results` 条，附加截断提示

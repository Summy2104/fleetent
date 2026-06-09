## ADDED Requirements

### Requirement: 首次 exec 捕获 shell 环境快照

系统 SHALL 在一个 session 的首次容器命令执行时，用登录 shell 捕获导出的环境变量（`export -p`）、shell 函数（`declare -f`）与别名（`alias -p`）到容器内的 session 专属快照文件（`/tmp/snap-<session>.sh`）。快照文件 MUST 每个 session 独立，互不干扰。

#### Scenario: 首次执行捕获快照
- **WHEN** 某 session 在容器内首次执行命令
- **THEN** 容器内生成该 session 专属的快照文件，包含其导出环境、函数与别名

### Requirement: 逐命令恢复使环境跨 exec 连续

后续每条命令 SHALL 被包装为：先 `source` 快照、再 `cd` 到持久化的工作目录、然后执行命令、最后重新 `export -p` 覆盖快照。由此，前一条命令对 `PATH`、虚拟环境等导出变量的修改 MUST 对后续命令可见。

#### Scenario: 环境变量跨命令连续
- **WHEN** 第一条命令执行 `export FOO=bar`，第二条命令执行 `echo $FOO`
- **THEN** 第二条命令输出 `bar`

#### Scenario: 工作目录跨命令连续
- **WHEN** 第一条命令 `cd /workspace/sub`，第二条命令执行 `pwd`
- **THEN** 第二条命令在 `/workspace/sub` 下执行

### Requirement: 工作目录经 marker 持久化且不泄露给调用方

系统 SHALL 通过在命令尾部打印一个唯一 marker 包裹的 `pwd` 来提取并持久化当前工作目录。该 marker 行 MUST 从返回给调用方（及写入 trace/上下文）的输出中剥离，不得出现在 agent 可见结果里。

#### Scenario: marker 不出现在输出
- **WHEN** 执行任意命令并提取其新的工作目录
- **THEN** 调用方收到的输出不包含 cwd marker 文本

### Requirement: 快照失败时降级且不影响命令正确性

当快照捕获或恢复失败（如首次捕获出错、快照文件不可用）时，系统 SHALL 降级为以登录 shell（`bash -l`）执行命令，保证命令仍能正确运行，仅损失跨 exec 的环境连续性。

#### Scenario: 快照不可用时降级执行
- **WHEN** session 的快照文件缺失或捕获失败
- **THEN** 命令仍以登录 shell 正确执行并返回结果

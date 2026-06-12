# file-tools-sandbox-execution Delta

## MODIFIED Requirements

### Requirement: path 锁定在 workspace 内

文件工具的 path 参数 SHALL 解释为双根命名空间内路径：相对路径相对 `/workspace`；绝对路径规范化后必须落在 `/workspace` 内，或落在 `/exchange/<server_id>/` 内（后者 MUST 经 file-exchange 的归属校验，归属不符或未登记即拒绝）。两根之外的路径 MUST 被拒绝并返回明确错误，不执行任何读写。

#### Scenario: 相对路径落在 workspace

- **WHEN** read_file 收到相对路径 `sub/a.txt`
- **THEN** 实际操作 `/workspace/sub/a.txt`

#### Scenario: 越界绝对路径被拒

- **WHEN** read_file 收到 `/etc/passwd` 或 `../../etc/passwd`
- **THEN** 返回越界错误，不读取该文件

#### Scenario: 本会话 /exchange 路径放行

- **WHEN** read_file 收到 `/exchange/srv/a.xlsx` 且该工件台账归属当前会话
- **THEN** 解析到有效文件根下真实文件并正常读取

#### Scenario: 跨会话 /exchange 路径被拒

- **WHEN** read_file 收到归属其他会话的 `/exchange` 路径
- **THEN** 返回归属校验失败的明确错误，不读取该文件

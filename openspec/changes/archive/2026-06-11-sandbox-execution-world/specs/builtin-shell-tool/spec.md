## MODIFIED Requirements

### Requirement: bash_exec 在宿主机直接执行 Shell 命令
`bash_exec` SHALL 在宿主机 Shell 环境中执行任意命令，返回 stdout、stderr 和退出码。`bash_exec` 与 `run_code` 互补：`run_code` 为 Docker 隔离的 Python 沙箱（不可信代码执行），`bash_exec` 为宿主机直接执行（运维/DevOps 场景）。二者同时存在，不互相替代。

`bash_exec` 模型可见描述的**首行**(schema_builder 只取 docstring 首行作为工具 description)MUST 写明其世界观：**在宿主执行，看不到 /workspace 与会话文件；处理会话文件请用容器内执行工具（run_code）**。该首行 MUST 使模型不把 `bash_exec` 误用于读写 `/workspace` 内的上传、生成产物或 skill 资源。

#### Scenario: 执行系统命令并返回输出
- **WHEN** 调用 `bash_exec(command="git status", description="查看 git 工作区状态")`
- **THEN** 返回命令的 stdout 输出、非零退出码（若有）和 stderr（若非空）

#### Scenario: 命令退出码非零时包含在返回值中
- **WHEN** 执行命令返回非零退出码
- **THEN** 返回结果末尾附加 `"[exit N]"` 标记，stdout/stderr 正常返回

#### Scenario: 描述首行声明宿主世界观
- **WHEN** schema_builder 由 `bash_exec` 的 docstring 取其首行作为工具 description
- **THEN** 该 description 表明 `bash_exec` 在宿主执行、看不到 /workspace 与会话文件，并引导处理会话文件改用容器内执行工具（run_code）

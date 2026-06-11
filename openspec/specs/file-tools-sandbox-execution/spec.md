# file-tools-sandbox-execution Specification

## Purpose
让 5 个文件工具（read_file/write_file/edit_file/search_content/search_files）经 sandbox 容器执行并锁定 workspace 边界：容器内 shell 命令执行、path 限制在 workspace 内、workspace 外宿主路径不可达、tool_context 定位 scope 容器、docker 不可用时降级宿主 + 路径围栏、read/search 保持安全 LOW，并保留既有功能行为。

## Requirements

### Requirement: 文件工具经容器执行操作 workspace

当 sandbox 可用且选定后端声明 `workspace_mount` capability 时，5 个文件工具（read_file/write_file/edit_file/search_content/search_files）SHALL 经 `SandboxManager` 取得 scope 容器并通过后端 `exec` 在容器内执行 shell 命令操作 `/workspace`，而非在宿主进程直接读写。

#### Scenario: read_file 走容器
- **WHEN** sandbox 可用、后端支持挂载，agent 调用 read_file 读 workspace 内文件
- **THEN** 文件内容经容器内命令读取并返回，宿主进程不直接 open 该路径

#### Scenario: write_file 走容器
- **WHEN** sandbox 可用、后端支持挂载，agent 调用 write_file 写 workspace 内文件
- **THEN** 内容经容器内命令写入，落在容器 `/workspace`（= 宿主 workspace 目录）

### Requirement: path 锁定在 workspace 内

文件工具的 path 参数 SHALL 解释为 workspace 内路径：相对路径相对 `/workspace`；绝对路径规范化后必须落在 `/workspace` 内。越界路径 MUST 被拒绝并返回明确错误，不执行任何读写。

#### Scenario: 相对路径落在 workspace
- **WHEN** read_file 收到相对路径 `sub/a.txt`
- **THEN** 实际操作 `/workspace/sub/a.txt`

#### Scenario: 越界绝对路径被拒
- **WHEN** read_file 收到 `/etc/passwd` 或 `../../etc/passwd`
- **THEN** 返回越界错误，不读取该文件

### Requirement: workspace 外宿主路径在容器内不可达

经容器执行时，workspace 以外的宿主路径（`/etc`、`~/.ssh`、宿主项目源码等）SHALL NOT 可读——容器内访问这些路径只得到容器镜像自身内容或不存在，靠 mount namespace 物理隔离。

#### Scenario: 宿主敏感文件不可达
- **WHEN** 通过文件工具尝试读取宿主真实 `/etc/passwd` 的内容
- **THEN** 读到的是容器镜像内容或路径不存在，宿主真实文件不泄露

### Requirement: tool_context 定位 scope 容器

文件工具 SHALL 接受 tool_context（session_id/agent_name），据此定位与 run_code 一致的 scope 容器；无 tool_context 时使用与 run_code 一致的默认 key。

#### Scenario: 同 session 复用容器
- **WHEN** 同一 session 先后调用 run_code 与文件工具
- **THEN** 二者操作同一 scope 容器的同一 `/workspace`

### Requirement: read/search 保持安全 LOW，write/edit 保持 medium

在 workspace 边界保证下，read_file/search_content/search_files 的风险等级 SHALL 保持 LOW（不经审批）；write_file/edit_file SHALL 保持 medium。

#### Scenario: 读取类零审批
- **WHEN** agent 调用 read_file/search_content/search_files
- **THEN** 不触发审批门，直接在 workspace 边界内执行

### Requirement: 保留现有文件工具功能行为

走容器后，文件工具 SHALL 保留既有功能：read_file 的行级分页与目录列举与二进制检测、edit_file 的 6 层 fallback 匹配与无意义替换防护、search 的正则/glob 与 ripgrep 回退。

#### Scenario: read_file 分页保留
- **WHEN** read_file 读取超过一页的文件
- **THEN** 返回带行号的分页内容与续读提示，与既有行为一致

#### Scenario: edit_file 6 层匹配保留
- **WHEN** edit_file 的 old_string 与文件内容有空白/缩进差异
- **THEN** 仍按 6 层 fallback 策略匹配并替换，返回命中的层名

### Requirement: sandbox 不可用或后端不支持挂载时降级为宿主执行加路径围栏

当 sandbox 不可用（后端不可用或 mode=off），或选定后端未声明 `workspace_mount` capability 时，文件工具 SHALL 降级为宿主执行，但路径经规范化 + workspace 根前缀判定限制在宿主 workspace 目录内；越界路径 MUST 被拒绝。降级取宿主视图与 IM 附件暂存（写宿主 workspace）保持一致；此时 `run_code` 的容器内 `/workspace` 与文件工具视图分歧为已知限制（见 sandbox-workspace-mount 降级条款）。

#### Scenario: 降级仍锁 workspace
- **WHEN** 后端不可用（或不支持挂载）且文件工具收到越界路径
- **THEN** 路径围栏拒绝该路径，不读写 workspace 外宿主文件

#### Scenario: 不支持挂载的后端附件仍可读
- **WHEN** 选定后端不支持挂载，IM 附件已暂存到宿主 workspace，agent 调用 read_file 读取
- **THEN** 文件工具以宿主围栏路径读到附件内容

### Requirement: 基础设施错误不得谎报为路径状态

文件工具的容器后端在解析 exec 输出前 SHALL 先判定执行是否为基础设施失败（容器失踪、daemon 错误等）；此类失败 MUST 以明确的沙箱不可用错误返回给模型，MUST NOT 解析为「路径不存在」「无匹配文件」等路径状态。`probe` 的 `missing` 判定 MUST 仅来源于容器内命令对路径的真实检查结果。

#### Scenario: 死容器下 read_file 报沙箱错误而非路径不存在
- **WHEN** 会话容器已死且未被自愈（极端情形），read_file 的容器内探测命令执行失败
- **THEN** 工具返回指明沙箱基础设施不可用的错误文案，不返回「路径不存在」

#### Scenario: 死容器下 search_files 报错而非"无匹配"
- **WHEN** 容器失踪导致 find 命令未真正执行
- **THEN** 工具返回沙箱错误，不返回「(无匹配文件)」

#### Scenario: 真实缺失路径仍如实报告
- **WHEN** 容器存活，read_file 探测一个确实不存在的路径
- **THEN** 工具返回「路径不存在」（既有语义不变）

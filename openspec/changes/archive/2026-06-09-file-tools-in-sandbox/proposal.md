## Why

`tools/file_tools.py` 的 5 个文件工具（read_file/write_file/edit_file/search_content/search_files）都是宿主进程 Python 函数、**零路径限制**：agent 一句 prompt injection 就能 `read_file("/etc/passwd")`、`search_content("api_key|password", "/")` 扫宿主全盘密钥，而且 read_file/search_content/search_files 是 LOW 风险、**不经审批**。这是当前最大的敏感信息泄露通道（威胁 C/E）。`sandbox-workspace` 已提供「容器挂载 workspace + namespace 隔离」的边界，本 change 让文件工具走容器、锁定在 workspace 内。

## What Changes

- **5 个文件工具走容器执行**：经 `SandboxManager`（复用 run_code 的 session/agent scope 容器，已挂载 `/workspace`）在容器内执行 shell 命令操作 workspace；文件操作映射为容器内命令（cat/sed/ls/grep/find），**判定与执行同在容器内**（避开宿主判定/容器执行的跨文件系统视图失真）。
- **path 锁定在 workspace 内**：相对路径相对 `/workspace`；绝对路径必须落在 `/workspace` 内，否则拒绝。workspace 外宿主路径靠容器 mount namespace 物理不可达——**不在宿主写 O_NOFOLLOW 围栏**。
- **tool_context 贯穿**：5 个工具接收 session_id/agent_name 以定位 scope 容器，复用 run_code 的 session snapshot/scope 逻辑。
- **降级**：docker/sandbox 不可用时，文件工具降级为宿主执行 + workspace 根目录路径围栏（`normpath` + 前缀判定，限制在 workspace 内、挡直接路径攻击），作为无 namespace 时的务实兜底。
- **风险定级**：read/search 在 workspace 边界结构性保证下保持安全 **LOW**（零审批、零摩擦，符合审批最小化）；write/edit 保持 **medium**。
- 保留现有功能行为：行级分页、二进制检测、edit 6 层 fallback 匹配、ripgrep/grep 回退。

无 BREAKING（工具签名兼容；行为从「读宿主任意路径」收紧为「读 workspace 内」，对正常 agent 用法透明——agent 的工作文件本就该在 workspace）。

## Capabilities

### New Capabilities
- `file-tools-sandbox-execution`: 文件工具走容器执行并锁定 workspace 边界的契约——容器内 shell 命令执行、path 限制在 workspace 内、workspace 外宿主路径不可达、tool_context 定位 scope 容器、docker 不可用时降级宿主+路径围栏、read/search 保持安全 LOW、保留现有功能行为。

### Modified Capabilities
<!-- 无：builtin-file-tools 的功能契约（分页/二进制检测/edit 6 层/搜索）不变；本 change 叠加「执行模型 + workspace 边界」新契约。 -->

## Impact

- **代码**：`tools/file_tools.py`（5 工具改造为走容器 + 降级）；新增文件操作→容器命令的 helper（可在 `tools/file_tools.py` 或 `integrations/sandbox/`）；复用 `integrations/sandbox` 的 `SandboxManager`/`client.exec`/workspace 挂载。
- **约束**：纯 agent 运行时（tools/ + integrations/sandbox/），不依赖 platform；asyncio。
- **测试**：unit（路径解析 workspace 限制、命令组装、降级路径围栏、风险定级）；integration（真实 docker：文件工具在容器内读写 workspace、workspace 外不可达、edit/search 端到端）。
- **依赖**：基于已合并入 main 的 `sandbox-workspace`（workspace 挂载 + session snapshot）。

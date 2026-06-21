## ADDED Requirements

### Requirement: stdio MCP 入参的容器 /workspace 路径翻译为宿主路径

沙箱 `/workspace` 是该 run 宿主工作区目录的 bind mount(`target=/workspace`);而 stdio MCP server 是宿主进程,运行在没有 `/workspace` 的宿主 mount namespace 中,直接对其文件路径参数做宿主文件系统 I/O。因此系统 SHALL 在 MCP 工具调用送达 server 之前,对**目标为 stdio transport 的 server**,把工具入参中所有等于 `/workspace` 或以 `/workspace/` 开头的字符串值翻译为该 run 宿主工作区的真实路径:`/workspace` → `<host_workspace_dir>`,`/workspace/<rel>` → `<host_workspace_dir>/<rel>`,其中 `<host_workspace_dir>` 按本次调用的 `scope_key` 派生(与 `/workspace` bind-mount 源同一目录)。翻译 SHALL 递归处理嵌套的 dict / list,非字符串值原样保留。

翻译 MUST NOT 改写非 `/workspace` 前缀的字符串(含工作区相对路径如 `generated/x.png`)。翻译 MUST NOT 应用于 http transport 的 server(远端服务,宿主路径无意义)。当本次调用没有 `scope_key`(无工作区上下文)时 MUST NOT 翻译(字节级透传,保持既有行为)。该翻译仅作用于**入参**,与既有的**结果/输出**路径改写与登记互不影响。

#### Scenario: stdio server 的 /workspace 附件路径被翻译为宿主路径
- **WHEN** 一次工具调用以 `scope_key` 投向某 stdio server(如 email/google-drive),入参含 `/workspace/generated/x.png`
- **THEN** server 实际收到的入参为 `<host_workspace_dir>/generated/x.png`(该 run 宿主工作区下的真实路径),从而能读到该文件

#### Scenario: http server 的入参不被翻译
- **WHEN** 一次工具调用投向某 http server,入参含 `/workspace/generated/x.png`
- **THEN** server 收到的入参仍为原始 `/workspace/generated/x.png`(不翻译)

#### Scenario: 嵌套结构与非 workspace 路径
- **WHEN** stdio server 入参为 `{"files": ["/workspace/a.png", "/etc/hosts"], "name": "x"}`
- **THEN** `/workspace/a.png` 被翻译为 `<host_workspace_dir>/a.png`,`/etc/hosts` 与 `"x"` 原样保留

#### Scenario: 无 scope_key 时不翻译
- **WHEN** 一次投向 stdio server 的调用没有 `scope_key`
- **THEN** 入参字节级透传,不发生任何路径改写

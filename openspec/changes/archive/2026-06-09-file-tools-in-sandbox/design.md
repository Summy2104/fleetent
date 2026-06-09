## Context

`tools/file_tools.py` 的 5 个工具用宿主 `Path` 直接读写、无路径限制。`sandbox-workspace`（已入 main）提供了「容器挂载宿主 `data/workspaces/{scope}` 到 `/workspace` + mount namespace 隔离 + session snapshot」。本 change 把文件工具的 IO 从宿主迁到容器内、锁定 workspace。约束：纯 agent 运行时、asyncio、保留现有功能行为（分页/二进制检测/edit 6 层匹配/ripgrep）。

## Goals / Non-Goals

**Goals:**
- 5 个文件工具走容器、操作 `/workspace`，path 锁定 workspace 内，workspace 外宿主路径不可达。
- 保留现有功能行为；read/search 保持安全 LOW，write/edit 保持 medium。
- docker 不可用时务实降级（宿主 + workspace 路径围栏）。

**Non-Goals:**
- O_NOFOLLOW/dir_fd 级宿主防护（靠容器 namespace）。
- workspace 文件的 populate（附件如何进 workspace）——另行处理。
- Action Gate 分级路由（下一个 change）。

## Decisions

**D1：新增容器文件 IO helper（`tools/file_sandbox_io.py`），5 工具复用。**
提供 `resolve_ws_path`（路径解析+边界校验）、`read`(cat)、`write`(cat> via stdin)、`list_dir`(ls)、`search_content`(grep/rg)、`search_files`(find/rg)。helper 经 `SandboxManager.acquire` 取 scope 容器，`client.exec(ws_id, cmd, session_id=...)` 执行。备选：每个工具内联 exec——否决，5 工具重复逻辑、难测。

**D2：路径模型——相对路径相对 `/workspace`，绝对路径必须落在 `/workspace` 内，容器内判定。**
`resolve_ws_path` 把入参规范化为容器内绝对路径并校验 `startswith("/workspace")`；越界返回错误。判定用容器内 `realpath`/`cd` 校验（与执行同视图），不在宿主 resolve（避开 hermes 跨视图坑）。

**D3：功能逻辑留宿主，对「容器读出的内容」处理。**
edit 的 6 层 fuzzy match、二进制检测、分页都是对文本内容的纯计算——容器 `cat` 读出内容到宿主，宿主跑现有逻辑，结果（write/edit）再 `cat>` 写回容器。路径不逃逸（IO 在容器），逻辑复用（不重写）。

**D4：降级——sandbox 不可用（docker 不可用或 mode=off）时，宿主执行 + workspace 路径围栏。**
helper 先探 sandbox 可用性（复用 `enablement`/`docker_available`）：可用走容器；不可用走宿主 `Path` IO，但路径经 `normpath` + workspace 根前缀判定限制在宿主 workspace 目录内。降级无 namespace，靠路径围栏挡直接路径攻击（prompt injection 主体），symlink/TOCTOU 不防（记录为已知限制）。备选：docker 不可用即禁用文件工具——否决，开发/无 docker 环境文件工具仍需可用。

**D5：风险定级——read_file/search_content/search_files 保持 LOW，write_file/edit_file 保持 medium。**
workspace 边界结构性保证读/搜不出圈，故 read/search 安全地零审批（审批最小化）。

**D6：tool_context 贯穿 5 工具。**
工具签名加 `tool_context: ToolContext | None`，从中取 session_id/agent_name 定位 scope 容器（同 run_code）。无 tool_context（直接调用）时用默认 key，与 run_code 一致。

## Risks / Trade-offs

- **降级路径的 symlink/TOCTOU**：宿主降级仅 normpath+前缀，挡不住 symlink 逃逸 → 缓解：仅在 docker 不可用时降级，且记录为已知限制；首选始终是容器路径（namespace 兜底）。
- **每次文件操作 acquire 容器**：首次创建容器有开销 → 缓解：acquire 复用 registry 容器（同 run_code），仅首次创建。
- **二进制内容经 cat 读到宿主**：大二进制文件 cat 到宿主内存 → 缓解：read 前先 `wc -c` 探大小 + `head -c` 探二进制，超限/二进制提前拒绝（保留现有二进制检测，移到容器探测）。
- **edit 读-改-写非原子**：容器内 cat 读→宿主 match→cat 写回，期间文件可能被改 → 接受：单 agent session 串行执行，并发风险低；与现有宿主 edit 同等语义。

## Migration Plan

增量：工具签名加可选 tool_context（兼容现有调用）。行为从「读宿主任意路径」收紧为「读 workspace 内」——对正常用法透明。Rollback：还原 file_tools.py 为宿主 IO。无数据迁移。

## Why

把沙箱里生成的文件作为附件发出去(email 发附件、google-drive 上传)100% 失败。现网实测(2026-06-18):用户让 agent「生成小狗图发邮件给 X」,两次审批都过、但 email server 报 `Attachment file not found: /workspace/generated/2f3993bf….png`,邮件根本没发出去。

根因是**容器/宿主路径视图错配**:

- 沙箱 `/workspace` 是 host 目录的 bind mount(`docker.py`:`--mount type=bind,source=<workspace_host_path>,target=/workspace`)。模型/`run_code`/image-gen 生活在**容器视图**,产物路径是 `/workspace/generated/x.png`。
- email、google-drive 等 **stdio MCP server 是宿主进程**(`uvx`/`npx`,与 fleetent 同 mount namespace,实测 `mnt:[4026531841]`),宿主上**没有 `/workspace`**,它们对 `localPath`/附件做的是直接 `fs.open()`(google-drive 甚至强制 `isAbsolute`)。
- 现状 MCP 调用 chokepoint(`integrations/mcp/client.py` 的 `_call_via_session_inner`)把工具入参 `args` **逐字透传**给 server,无任何路径改写(只有**结果/输出**侧有 `rewrite_and_register`/`diff_register`)。于是 `/workspace/...` 容器路径原样到宿主进程 → 找不到 → 失败。

`/workspace/<rel>` 对宿主进程而言是**会话歧义**的(实测 104 个 per-session 工作区目录,同一字符串在不同 session 指不同文件),且其所在 namespace 无 `/workspace`——所以任何静态 symlink/挂载/env 都无法让宿主进程解析它。唯一持有 session 上下文的是 chokepoint(本次调用的 `scope_key`)。因此正确解法是在 chokepoint 用 `scope_key` 把入参里的 `/workspace/<rel>` 翻译成宿主真实路径 `<workspace_host_path>/<rel>` 再透传(零拷贝,同一 bind-mount inode)。

> 已排除的替代:同路径挂载(取消 `/workspace` 抽象、泄露宿主布局、牵连 skills/exchange/提示词、动安全围栏);宿主 symlink(会话歧义 + 根目录需 root);nsenter / server 进容器(生命周期与隔离矛盾)。详见 design.md。

## What Changes

- **chokepoint 入参翻译**:`_call_via_session_inner` 在 `session.call_tool(tool_name, args)` 之前,当 `(server.transport == "stdio" 且存在 scope_key)` 时,把 `args` 中所有等于 `/workspace` 或以 `/workspace/` 开头的字符串值,改写为 `<workspace_host_path(scope_key)>` / `<host>/<rel>`;递归处理 dict/list;其余字符串与非 stdio(http)server 原样不动。
- **新增宿主目录派生函数**:`integrations/sandbox/manager.py` 增公开 `host_workspace_dir(scope_key) -> Path`(= `paths.workspaces_dir() / _name_key(scope_key)`,与 bind-mount 源、`workspace_host_path` 同一目录;纯计算、不建目录)。

不动:结果/输出侧改写与登记;`/exchange` 解析;http server 行为;`url_private` 等其它链路。只补「入站到 stdio server 的 `/workspace` 路径 → 宿主路径」这一向。

## Capabilities

### New Capabilities
<!-- 无 -->

### Modified Capabilities
- `file-exchange`:在既有「stdio server 文件根映射 / 结果改写登记 / `/exchange` 解析」之上,新增一条**入参路径翻译**要求——MCP 调用送达 stdio server 前,系统 SHALL 把工具入参中的容器 `/workspace[/<rel>]` 路径翻译为该 run 宿主工作区的真实路径(按 `scope_key` 派生),使宿主型 stdio server 能读到 `/workspace` 下的文件;http server 与非 `/workspace` 字符串不受影响。

## Impact

**owning package**:agent runtime —— `src/fleetent/integrations/mcp/client.py`(chokepoint 入参翻译)+ `src/fleetent/integrations/sandbox/manager.py`(`host_workspace_dir` 派生)。二者同属 `integrations` 包,intra-package import 不越界;全程 agent runtime 侧,不 import `fleetent.platform.*`。

**public API surface**:`integrations/sandbox/manager.py` 新增模块级 `host_workspace_dir(scope_key: str) -> Path`(供 chokepoint 调用)。`call_tool` / `_call_via_session*` 签名不变(已 thread `scope_key`)。

**owned tables**:无(零 schema、零迁移)。

**config namespace**:无(无新配置;翻译对 stdio server 无条件生效)。

**cross-module dependencies**:`mcp/client.py` 惰性 import `integrations.sandbox.manager.host_workspace_dir`(同包,无循环——manager 不 import mcp);依赖既有 `scope_key` thread 路径,不触碰 agent↔platform 边界。

**migration / shim plan**:无。

**受影响代码**:`integrations/mcp/client.py`(新增纯函数 `_translate_workspace_args` + chokepoint 接线)、`integrations/sandbox/manager.py`(`host_workspace_dir`);测试 `tests/unit/test_mcp_exchange_injection.py`(纯函数翻译用例)+ `tests/unit/test_mcp_workspace_arg_translation.py`(chokepoint stdio 翻译/http 不翻译 wiring)。

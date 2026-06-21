# Design — translate-workspace-paths-for-stdio-mcp-args

## 问题精确化（live 验证）

| 事实 | 证据 |
|---|---|
| `/workspace` 是 host 目录的 bind mount | `docker.py`: `--mount type=bind,source={workspace_host_path},target=/workspace` |
| 宿主上无 `/workspace` | `ls /workspace` → No such file |
| 工作区 per-session、高并发 | `data/workspaces/` 下 104 个 session 目录 |
| email/google-drive 是宿主进程、宿主 mount ns | 进程 `mnt:[4026531841]`（= fleetent，非容器 ns）|
| stdio server 直接 `fs.open(localPath)` | email `_validate_attachment` os.path.exists；google-drive `if(!isAbsolute) throw` + createReadStream/WriteStream |
| chokepoint 入参零改写 | `_call_via_session_inner` 直接 `session.call_tool(tool_name, args)`；改写函数 `_rewrite_result_paths`/`rewrite_and_register` 全是**结果侧** |

`/workspace/<rel>` 对宿主共享进程**会话歧义**(字符串不含 session、ns 无 `/workspace`)。唯一能消歧的是 chokepoint 持有的本次调用 `scope_key`。

## 决策

### D1. 在 chokepoint 入参侧翻译，对称于既有结果侧改写
`_call_via_session_inner`(client.py ~1186)在 `session.call_tool(tool_name, args)`(~1225)**之前**,对入参做一次 `/workspace` → 宿主路径翻译。这与既有「结果路径改写」`_rewrite_result_paths`(~1108,出站)正好对称(入站)。翻译一次即可,两条 call 路径(首次 + lazy-reconnect retry)复用同一 `args`。

### D2. 仅对 stdio server 翻译；http server 不动
`server = _server_registry.get((scope, server_id))` 已在手,判 `server.transport == "stdio"`。http server(jira/confluence/armada/knowledge-bridge/middle)是远端,`/workspace`/宿主路径对它都无意义,故跳过——避免误改远端工具入参。

### D3. 宿主目录由 scope_key 派生，复用单一来源
chokepoint 已 thread `scope_key`(= `workspace_scope_key(scope, session_id, agent_name)`,与 `/workspace` bind-mount 同源)。宿主目录 = `paths.workspaces_dir() / _name_key(scope_key)`,与 `workspace_host_path` 落点完全一致。

新增 `integrations/sandbox/manager.py` 模块级公开函数:

```python
def host_workspace_dir(scope_key: str) -> Path:
    """The host dir bind-mounted at /workspace for a run's workspace scope key.
    Same dir workspace_host_path returns, keyed by the already-resolved scope_key the
    MCP chokepoint threads, so stdio arg translation and the bind mount agree. Pure:
    does not create the directory."""
    return paths.workspaces_dir() / _name_key(scope_key)
```

- 复用 `_name_key`(含 sha256 截断逻辑,**不可复制**)+ `paths.workspaces_dir()`,保证与挂载源同一目录。
- 纯计算、不 mkdir:翻译是读路径,目录在 `acquire` 时已建;不存在时翻成的路径不存在,server 报错与今天等价(但已是正确宿主路径)。

### D4. 翻译为纯函数，递归处理 dict/list/str
client.py 新增模块级纯函数:

```python
_WORKSPACE_PREFIX = "/workspace"

def _translate_workspace_arg(value: str, host_dir: Path) -> str:
    if value == _WORKSPACE_PREFIX:
        return str(host_dir)
    if value.startswith(_WORKSPACE_PREFIX + "/"):
        return str(host_dir / value[len(_WORKSPACE_PREFIX) + 1 :])
    return value

def _translate_workspace_args(args, host_dir):  # dict/list/str 递归
    ...
```

- 只认 `/workspace` 与 `/workspace/` 前缀(沙箱挂载点,极具体,误伤率近零);**不**翻译工作区相对路径(`generated/x.png`,语义模糊且 google-drive 要求绝对路径,留作 out-of-scope)。
- 纯函数、无 I/O → unit 层可直接红/绿。

### D5. 接线位置与惰性 import
在 `_call_via_session_inner` 拿到 `server`、过完 health 短路之后、`session.call_tool` 之前:

```python
if scope_key and server.transport == "stdio":
    from fleetent.integrations.sandbox.manager import host_workspace_dir
    args = _translate_workspace_args(args, host_workspace_dir(scope_key))
```

惰性 import(同 `from fleetent import artifact_exchange` 风格)避免任何潜在循环(且 manager 不 import mcp,本无循环)。

## 测试策略（unit）

1. **纯函数翻译**(`test_mcp_exchange_injection.py` 补):`/workspace/generated/x.png` → `<host>/generated/x.png`;精确 `/workspace` → `<host>`;非 `/workspace` 串不动;dict/list 递归;`host_dir` 用 `tmp_path`。
2. **`host_workspace_dir`**:断言 `host_workspace_dir(k) == paths.workspaces_dir()/_name_key(k)`(conftest 已把 FLEETENT_HOME 钉 tmp)。
3. **chokepoint wiring**(新文件 `test_mcp_workspace_arg_translation.py`):`monkeypatch.setitem(_server_registry,(None,id),server)` + stub `_active_sessions` 的 fake session(`call_tool` 记录收到的 args);monkeypatch `_result_to_text`→"ok"。断言:stdio server 收到**翻译后**路径;http server 收到**原始** `/workspace/...`;无 scope_key 时不翻译。均 mock,无真实 subprocess/DB/HTTP,合 unit 边界。

## 可观测信号

修复后:发邮件/传 Drive 时 stdio server 收到的附件路径是 `<FLEETENT_HOME>/data/workspaces/<session>/generated/x.png`,文件存在 → 附件成功、邮件发出;不再有 `Attachment file not found: /workspace/...`。

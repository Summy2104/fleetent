## Context

`_register_stdio_server` 与 `_probe_stdio_tools` 都有：
```python
merged_env = {**os.environ, **server.env} if server.env else None
params = StdioServerParameters(command=..., args=..., env=merged_env)
```
当 `server.env` 非空时，子进程拿到**整个** `os.environ`（含平台密钥）+ server.env。当 server.env 为空时传 `env=None`，此时 MCP SDK 用其 `get_default_environment()`（一组安全默认变量）。即：泄漏只在「声明了任意 env」时发生——而那恰恰是接入真实服务的常见情形。

## Goals / Non-Goals

**Goals:**
- 子进程仅继承一组经审定的安全宿主变量 + server 显式 env；不泄漏平台密钥。
- register 与 probe 行为一致；始终传受控 env（不再 None 分支）。
- server 显式 env 覆盖白名单同名键。

**Non-Goals:**
- 不新增配置字段（如 `env_passthrough` 显式转发列表）——保持本变更收敛在 client.py；需转发宿主值时用现有 `server.env` 显式声明。记为未来增强。
- 不做子进程沙箱/seccomp（属 sandbox 模块范畴）。
- 不动 HTTP 传输（无子进程）。

## Decisions

**D1 自带白名单常量。** 定义 `_SAFE_ENV_KEYS_POSIX` / `_SAFE_ENV_KEYS_WIN`（镜像 MCP SDK `DEFAULT_INHERITED_ENV_VARS` 并补 locale/临时目录等运行必需项：POSIX = HOME/LOGNAME/PATH/SHELL/TERM/USER + LANG/LC_ALL/LC_CTYPE/TMPDIR/TZ；WIN = APPDATA/HOMEDRIVE/HOMEPATH/LOCALAPPDATA/PATH/PROCESSOR_ARCHITECTURE/SYSTEMDRIVE/SYSTEMROOT/TEMP/TMP/USERNAME/USERPROFILE）。`_safe_base_env()` 按 `os.name` 选集并从 `os.environ` 过滤出存在者。不直接 import SDK 私有 `get_default_environment`，避免依赖内部 API。

**D2 `_subprocess_env(server)` 单点构建。** 返回 `{**_safe_base_env(), **server.env}`。register 与 probe 都改用它，`StdioServerParameters(env=_subprocess_env(server))`——始终传 dict。理由：单点、行为一致；旧的「空 env → None → SDK 默认」与新的「空 env → 白名单」等价安全（白名单是 SDK 默认的超集），非空 env 由泄漏全环境改为仅白名单（修复）。

**D3 覆盖语义。** `{**base, **server.env}` 使 server.env 对同名键覆盖白名单值（如 operator 自定义 PATH）。这是显式转发宿主密钥的受支持方式。

## Risks / Trade-offs

- 行为变化：依赖隐式继承宿主变量（白名单外）的 stdio 服务会失去这些变量 → 改为在 `server.env` 显式声明。这是修复的安全意图，非回归；送审记录。
- 白名单过窄可能漏掉个别服务必需变量 → 选取与 SDK 默认对齐并补常见 locale/temp 项；不足处由 operator 经 `server.env` 补。
- 仅覆盖 stdio；HTTP/OAuth 凭据走 header（不经子进程 env），不受影响。

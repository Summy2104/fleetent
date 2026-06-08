## Context

`agent_app.build_app()` 的 `/ws` 端点（为 TUI 服务）调用 `user_store.authenticate(token)`，
该函数查询 `$FLEETENT_HOME/data/fleetent.db` 的 `users` 表。这张表由
`fleetent-admin create-user` 写入——platform 控制面命令。standalone agent 与 platform
解耦，不应要求用户先操作 platform 才能连接 TUI。

`agent_init.py` 已有 `_referenced_env_names()` 逻辑自动收集 `.env` 变量名。
`agent_app.build_app()` 的 `/ws` 认证逻辑集中在约 15 行代码里，替换代价低。

`FLEETENT_TUI_TOKEN` 的格式沿用 `ma-<64hex>`（与现有 API key 格式一致），
由 `secrets.token_hex(32)` 生成。

## Goals / Non-Goals

**Goals**
- `fleetent agent init <id>` 后立即可用 TUI，无需任何 platform 操作
- standalone agent `/ws` 完全不调用 `user_store`（消除 agent-platform 依赖）
- 已有 agent（无 `FLEETENT_TUI_TOKEN`）重新 init 或手动补 `.env` 后可用

**Non-Goals**
- 多用户 TUI 访问（standalone agent 单人使用，`user_id="local"` 够用）
- platform server 的 `/ws` 认证——不变，继续用 `user_store`
- TUI 的多 session 隔离——不在本 change 范围

## Decisions

**D1 — token 放 `.env`，不放 `agent.yaml`**

`.env` 存 secrets，`agent.yaml` 存配置——与 Slack token 等已有模式完全一致。
`FLEETENT_TUI_TOKEN` 是 secret（拥有它即可访问 agent），应在 `.env`。

**D2 — `agent init` 总是追加 token（若不存在）**

首次 init：`.env` 不存在，生成完整文件含 `FLEETENT_TUI_TOKEN`。
重复 init（无 `--force`）：`agent.yaml` 已存在会 raise `FileExistsError`，
`.env` 只在不存在时写入（现有逻辑）——所以已有 `.env` 的情况下，若无 token 需
用户手动追加或用 `--force`。

**D3 — 未配置 token 时拒绝连接（code 1008）**

不降级为"无认证"——port 若暴露在内网，无认证会有意外访问风险。
拒绝时日志打印明确提示：`add FLEETENT_TUI_TOKEN to .env`。

**D4 — user_id 固定为 "local"**

TUI 是单人本地工具，会话按 `user_id` 隔离。固定 `"local"` 语义清晰，
不影响多 agent 情况（每个 agent 有自己的 token 和自己的会话）。

## Risks / Trade-offs

- **已有 agent 升级**：已部署的 agent `.env` 没有 `FLEETENT_TUI_TOKEN`，TUI 连接
  会失败。用户需手动添加一行。Mitigation：错误日志给出明确提示和示例命令。
- **token 安全性**：`secrets.token_hex(32)` = 256 bits 熵，足够安全。
  `.env` 应设 `chmod 600`（安装文档已注明）。

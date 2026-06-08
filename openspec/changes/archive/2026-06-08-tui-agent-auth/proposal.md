## Why

standalone agent 的 `/ws` 端点（TUI 入口）复用 platform 的 `user_store.authenticate()`，
要求预先执行 `fleetent-admin create-user` 创建用户并获取 `ma-xxxx` token。这对只跑
standalone agent 的开发者是不必要的摩擦——`fleetent-admin` 在概念上属于 platform 控制面，
与 agent 运行时无关。`fleetent agent init` 应能自给自足地产出 TUI 连接所需的全部配置。

## What Changes

- `agent_init.py`：`scaffold_agent_home()` 在 `.env` 中自动生成
  `FLEETENT_TUI_TOKEN=ma-<32字节随机hex>`；已存在 `.env` 时追加此行（不覆盖已有内容）
- `agent_app.build_app()`：`/ws` 端点认证改为读取 `FLEETENT_TUI_TOKEN` env var，
  匹配则以 `user_id="local"` 接入；`user_store.authenticate()` 不再在 standalone
  agent `/ws` 中调用
- 若 `FLEETENT_TUI_TOKEN` 未设置（已有 agent 未经 re-init）→ 拒绝连接并返回
  `1008 Policy Violation`，日志提示用户运行 `fleetent agent init --force` 或手动在
  `.env` 中添加 `FLEETENT_TUI_TOKEN`
- `agents/default/agent.yaml.example` / 文档：无需改动（token 在 `.env`，不在 yaml）

## Capabilities

### New Capabilities

- `tui-agent-token-auth`: standalone agent 通过 `FLEETENT_TUI_TOKEN` env var 完成
  TUI WebSocket 认证，无需 platform user_store

### Modified Capabilities

- `agent-runtime-cli`: `fleetent agent init` 产出包含 TUI token 的完整 `.env`

## Impact

- `src/fleetent/runtime/agent_init.py` — 生成 `FLEETENT_TUI_TOKEN` 到 `.env`
- `src/fleetent/runtime/agent_app.py` — `/ws` 换用 token 认证，移除 `user_store` 依赖
- `tests/unit/test_agent_init.py` — token 生成测试
- `tests/unit/test_agent_app_tui_auth.py` — `/ws` 认证逻辑测试

## 1. agent_config：豁免 im access allowlist 路径的 inline-secret 误报

- [ ] 1.1 写测试（unit，`tests/unit/test_agent_config_mcp_secrets.py`）：构造含 `im.slack.access.allow_users: ["<UUID>"]`（用真实形态 UUID，如 `5f5904ef-efcf-42bb-82fa-ad5a150b078c`）+ `bot_token_env`/`app_token_env` 为合法 env 名的 `AgentFile`，调 `_reject_inline_secrets` **不抛**。先见红（当前 UUID 触发 `_SECRET_RE` 的 `{24,}` 分支被误判）
- [ ] 1.2 写测试（unit，同文件）：`im.telegram.access.allow_groups: ["<UUID>"]` 同样不被标记（覆盖 allow_groups 与 telegram binding）。可与 1.1 合并断言，但须独立覆盖 allow_groups 路径
- [ ] 1.3 写测试（unit，同文件，防回归）：`im.slack.bot_token_env` 直接写明文 token-like 值（如 `xoxb-...` 或高熵串）仍 `raises ValueError(match="inline secret")`——证明豁免未波及真 secret 字段。先确认此断言在改前已绿（防回归基线）
- [ ] 1.4 实现：`agent_config._reject_inline_secrets` 的 skip-segment 集合新增 `.access.allow_users.` 与 `.access.allow_groups.`（抽为模块常量 `_SKIP_SECRET_SCAN_SEGMENTS` 或就地扩列表）；令 1.1–1.2 见绿、1.3 保持绿
- [ ] 1.5 跑受影响层：`uv run pytest tests/unit/test_agent_config_mcp_secrets.py -q`，确认无新增失败

## 2. change 收尾

- [ ] 2.1 `make test-pr` 全绿（unit + 层边界 + 改动文件 ruff）
- [ ] 2.2 `uv run pytest tests/integration -q`（不带 `-x`）对照 main 基线，确认无新增失败

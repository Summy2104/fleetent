## 1. directory 相对 home 解析

- [x] 1.1 Write failing tests for directory resolution: 相对路径解析到 `<home>/data/logs`（与 CWD 无关）、绝对路径原样透传、留空默认 `<home>/data/logs`（现有行为回归钉住）
- [x] 1.2 Implement resolution in `_configure_logging_from_agent` to pass tests: 非绝对路径 `home_dir / directory`，绝对路径与留空分支不变

## 2. 收尾

- [x] 2.1 修正 my-bot 实际配置验证：本地 `~/.fleetent/agents/my-bot/agent.yaml` 保持 `directory: data/logs`，重启后日志落 `~/.fleetent/agents/my-bot/data/logs/`（手动 smoke，不进测试）
- [x] 2.2 跑受影响层收尾：`uv run pytest tests/unit -q` 无新增失败；`make test-pr` 全绿

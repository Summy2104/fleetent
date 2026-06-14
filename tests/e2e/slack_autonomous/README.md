# Slack 自主黑盒 E2E 套件

通过**真实 Slack（Web API）**黑盒测试 fleetent agent：Claude 作为自主大脑，按能力覆盖清单
多轮对话并判定；一个纯收发 helper CLI 做手脚（含文件上传/下载——MCP 做不到）。

取代旧的 `slack-e2e-test-suite`（Claude Slack MCP + 写死 yaml catalog + validator，已随本 change 移除）。

## 组成

- `helper.py` — Slack Web API helper CLI（`send`/`read`/`upload`/`download`/`resolve`），纯机械收发，无 LLM、无判定。
- `_pure.py` — 网络无关的纯逻辑（消息过滤、JSON 契约、resolve 报告、文件名安全），由 unit 覆盖。
- `catalog.py` — 能力覆盖清单 + rubric（A 核心黑盒 / B 需前置 / C 排除），测试目标全集。
- 驱动方法论：skill `slack-e2e-autonomous`（见 `.claude/skills/`）。

## 环境准备（运行时显式提供，缺失则报阻塞、不伪造）

| 变量 | 含义 |
|---|---|
| `SLACK_E2E_TOKEN` | user OAuth token `xoxp-`（以你的身份发消息） |
| `SLACK_E2E_CHANNEL` | 测试频道 id |
| `SLACK_E2E_BOT_USER_ID` | 被测 agent 的 bot user id（用于识别哪些消息是 agent 发的） |

user token 所需 scope：`chat:write`、`files:write`、`channels:history`（+ `groups`/`im`/`mpim:history`）、
`users:read`、`channels:read`。

还需：fleetent server 正跑着被测 agent、bot 已在该频道、token 对应 user 在 agent allowlist 内。
**不提交任何 token/secret——只用环境变量。**

## 运行

**自主套件（推荐）**：在 Claude Code 会话里触发 `slack-e2e-autonomous` skill，Claude 会 `resolve`
前置、按 `catalog.py` 逐项自主对话与判定、产出报告。

**直接用 helper**（调试通路）：

```bash
export SLACK_E2E_TOKEN=xoxp-... SLACK_E2E_CHANNEL=C... SLACK_E2E_BOT_USER_ID=U...
uv run python -m tests.e2e.slack_autonomous.helper resolve
uv run python -m tests.e2e.slack_autonomous.helper send --text "你好"
uv run python -m tests.e2e.slack_autonomous.helper read --thread-ts <ts> --after-ts <ts>
```

**冒烟测试**（pytest，需上述环境，否则 skip）：

```bash
uv run pytest tests/e2e/test_slack_autonomous_smoke.py -q
```

## 不进 CI 门禁

大脑是会话内的 Claude，本套件本地驱动反复跑、出报告；不做无人值守 CI（沿用 e2e 默认不进 PR 门禁）。
helper 的纯函数逻辑由 `tests/unit/test_slack_e2e_*.py` 覆盖，进常规测试套件。

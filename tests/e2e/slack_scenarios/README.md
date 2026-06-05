# Slack agent E2E 用例(LLM 模拟中文用户)

黑盒、真实 Slack 验收测试:一个 LLM 扮演说中文的人类用户,和 fleetent agent 的 Slack bot 多轮
对话,再由 LLM 裁判只凭对话判 pass/fail。

- **设计**:`openspec/changes/.../slack-e2e-test-suite`(归档后在 `openspec/specs/slack-e2e-test-suite`)
- **驱动**:`slack-agent-e2e` Claude Code skill(`.claude/skills/slack-agent-e2e/`)
- **用例**:本目录下的 `*.yaml`(每个一个目标驱动的中文场景)
- **目录校验**:`tests/integration/test_slack_scenarios_catalog.py`(结构 + 覆盖完整性 + 中文,
  随常规 pytest 跑;这是确定性门禁。真实 LLM-as-user 跑测由上面的 skill 单独驱动。)

这些用例**不**由 pytest 执行,而是在**已认证的 Claude Code 会话**里由 `slack-agent-e2e` skill 执行
(Slack MCP 是交互式授权,故不走 headless cron)。

## 运行前置

1. **测试 workspace + bot**:一个 Slack workspace,一个测试 bot(Socket Mode app),其
   `xoxb-`/`xapp-` token 放入 env 变量;以及一个该 bot 所在的测试频道。
2. **测试 agent**:把 `config/agents/e2e-tester/agent.yaml.example` 复制为
   `config/agents/e2e-tester/agent.yaml`,填 `bot_token_env`/`app_token_env`,并确保引用的
   工具 / 技能 / MCP server / sandbox 真实可用。
3. **server 跑着**该测试 agent(`uvicorn fleetent.server:app`),其 per-agent Slack 连接已建立。
4. **Slack MCP 已认证**同一 workspace,能在测试频道收发(`mcp__claude_ai_Slack__*`)。
5. **允许名单**:MCP 认证的 Slack 用户在该 agent 的允许名单内。
6. **频道 id**:把每个用例里的 `REPLACE_WITH_TEST_CHANNEL` 换成真实频道 id。

## 运行

在已认证的 Claude Code 会话里调用 `slack-agent-e2e` skill(例如:「跑 Slack e2e 测试」)。它逐个
用例、各自独占线程地执行,最后打印结果表 + `通过 n/m`。

## 注意

- **非确定性**:两端 + 裁判都是 LLM,flaky 用例可重跑;`success_criteria` 写清楚。
- **图片用例**:`dan-tu-fen-xi` / `tu-wen-hun-he` 需往 Slack 发图——先确认 MCP 能否发图,否则按
  用例 `setup_hint` 回退(预先上传文件 / 贴公开图片 URL)。
- **暂不覆盖(已延后)**:审批流、per-agent 路由、允许名单拒绝。

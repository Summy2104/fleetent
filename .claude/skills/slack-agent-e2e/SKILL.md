---
name: slack-agent-e2e
description: >-
  通过真实 Slack 对 fleetent agent 做黑盒端到端测试:用 LLM 扮演说中文的人类用户,目标驱动
  多轮对话,再以裁判身份只凭对话判分。当被要求“跑 Slack e2e 测试 / 通过 Slack 测试 agent /
  执行 tests/e2e/slack_scenarios 里的用例”时使用。经 Claude Slack MCP 收发,绝不读 fleetent
  内部日志。
---

# Slack agent E2E(LLM 模拟中文用户)

你扮演一个**说中文的人类用户**,在真实 Slack 里和 fleetent agent 的 bot 对话,然后以**裁判**
身份判定每个用例。**纯黑盒**:只凭 Slack 对话判 pass/fail,绝不读 fleetent 内部日志。

## 前置检查(先查;缺则报阻塞并停止)

- Claude Slack MCP 已认证(`mcp__claude_ai_Slack__*` 工具可用)。
- 每个用例的 `channel` 已设为真实频道 id(不是 `REPLACE_WITH_TEST_CHANNEL`)。
- fleetent server 正跑着测试 agent,其 Slack bot 在该频道,且 MCP 认证的用户在 agent 允许名单内。

任一前置不满足:**明确报告缺什么并停止**——不得伪造结果。

## 单用例流程

对 `tests/e2e/slack_scenarios/*.yaml`(或指定子集)中的每个用例:

1. **读用例**:`persona`、`goal`、`success_criteria`、`max_turns`、`channel`、`setup_hint`。
2. **开场**:以人设身份,用中文发第一句朝向 goal 的消息(`mcp__claude_ai_Slack__slack_send_message`
   到 `channel`)。记下返回的消息 `ts`,即线程根。
3. **读回复**:轮询 `mcp__claude_ai_Slack__slack_read_thread` 取该线程里 agent bot 的**新**消息;
   短间隔重试,总超时约 60s。始终无回复 → 记 **fail(无响应)**。
4. **继续**:若 goal 尚未明显达成且还有轮次,以人设用中文发下一句(推进 goal,**不要提示/教 agent,
   也不要暴露这是测试**),回到第 3 步。
5. **停止**:goal 达成,或已发满 `max_turns` 条用户消息。
6. **判分**(见下),记录结果。

**一次只跑一个用例**,每个用例独占一个 Slack 线程,避免 transcript 交叉。`image`/`image-text` 用例
先确认 MCP 能否发图;不能则按用例 `setup_hint` 回退,或以「阻塞:无法发图」跳过。

## 判分准则

读完整线程对话,严格对照该用例的 `success_criteria` 判 **pass/fail**:
- **pass**:对话清楚满足成功标准。
- **fail**:未满足、agent 拒绝/报错、需要具体动作却只给泛泛回答、或无回复。
- 只看 Slack 里可见的内容,不臆测内部行为。**真有歧义就判 fail 并说明**(真人 reviewer 不会让
  含糊的结果过)。

## 报告

跑完所有用例,输出表格 `id | coverage | 结果 | 轮数 | 理由`,末尾一行 `通过 n/m`。每个 fail 附决定性的
对话片段。**没读到 agent 真实回复,不得声称该用例 pass。**

## 诚实铁律

- 绝不编造对话或判定。每个 pass 必须有你从线程里真实读到的 agent 回复支撑。
- MCP / 频道 / server / 允许名单 任一阻塞 → 报告阻塞,**绝不**用模拟 transcript 顶替。

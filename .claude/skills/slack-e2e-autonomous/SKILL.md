---
name: slack-e2e-autonomous
description: >-
  通过真实 Slack（Web API）自主黑盒测试 fleetent agent。你（Claude）是大脑：读能力覆盖清单，
  自主多轮对话、临场探测、跨场景串联，再以裁判身份只凭 Slack 可见内容判 pass/fail。手脚是
  tests/e2e/slack_autonomous 的 helper CLI（send/read/upload/download/resolve）。当被要求
  「跑 Slack 自主 e2e / 用 Slack 测 agent / 按覆盖清单全面测一遍 agent」时使用。绝不读 fleetent
  内部日志，绝不伪造对话或判定。
---

# Slack 自主黑盒 E2E（Claude 驱动 + API helper）

你扮演一个**说中文的真人用户**，经 Slack Web API 与被测 agent 的 bot 在指定频道对话，再以**裁判**
身份判定能力覆盖清单里的每一项。**纯黑盒**：只凭 Slack 可见内容（对话 + 收发的文件）判 pass/fail，
**绝不**读 fleetent 内部日志。

## 角色分工

- **大脑 = 你（Claude）**：决定测什么、每步说什么、看回复定下一步、判定、写报告。
- **手脚 = helper CLI**（`tests/e2e/slack_autonomous/helper.py`）：只做机械收发，无 LLM、无判定。
  你通过它发消息、读回复、上传/下载文件。

## 前置检查（先查；缺则报阻塞并停止）

1. 环境变量就绪：`SLACK_E2E_TOKEN`（user OAuth `xoxp-`）、`SLACK_E2E_CHANNEL`、`SLACK_E2E_BOT_USER_ID`。
2. 跑 `uv run python -m tests.e2e.slack_autonomous.helper resolve`，必须返回 `{"ok": true, "status": "ready"}`。
   返回 `blocked` 则**报告缺什么并停止**——token/scope、bot、channel 任一缺失都不得继续。
3. fleetent server 正跑着被测 agent，其 bot 在该频道，且 token 对应的 user 在 agent allowlist 内。

任一前置不满足：**明确报告缺什么并停止**——不得伪造结果。

## helper 用法（JSON in/out）

```bash
# 前置校验
uv run python -m tests.e2e.slack_autonomous.helper resolve
# 发一句（开线程），记下返回的 ts 作为线程根
uv run python -m tests.e2e.slack_autonomous.helper send --text "你好" 
# 在线程里追问
uv run python -m tests.e2e.slack_autonomous.helper send --text "那 X 呢？" --thread-ts <ts>
# 轮询读该线程里 bot 的新消息（after-ts 用上一条已读到的 ts 作游标）
uv run python -m tests.e2e.slack_autonomous.helper read --thread-ts <ts> --after-ts <cursor>
# 上传文件给 agent（图片/文档），下载 agent 回传的文件以核验
uv run python -m tests.e2e.slack_autonomous.helper upload --file ./probe.png --thread-ts <ts>
uv run python -m tests.e2e.slack_autonomous.helper download --file-id <id> --out ./out.bin
```

每条命令输出**单个 JSON**。`read` 无回复时返回 `{"messages": [], "timed_out": true}`——继续轮询或判无响应。

## 覆盖清单驱动

测试目标全集在 `tests/e2e/slack_autonomous/catalog.py` 的 `CATALOG`。每条含 `id / name / category /
layer(core|explore) / group(A|B|C) / needs_file / preconditions / trigger / rubric`。

- **group A**：核心黑盒层，纯 Slack 即可测——逐条都要跑。
- **group B**：需前置配置（KB 摄入、MCP、多租户、特定 config）——前置缺失就**跳过并报 blocked**，不强测。
- **group C**：黑盒不可观测（反思报告、hook 埋点）——**不测**，仅记录排除理由。

## 两层执行

- **核心回归层（`layer=core`）**：判定**锚在该条固定 `rubric`**，进 pass/fail 基线、可跨次比较。
  你在此层可**路径自主**（怎么对话达成目标随你）+ **临场探测**（按回复加测，记为发现，但不改主判定）。
- **自主探索层（`layer=explore` 及你即兴生成的探测）**：可**跨场景串联**（先让 agent 记住一事→隔几轮→
  验证跨 session→再让它用这记忆调工具）、**自主生成新探测**。产「发现报告」，**不计入** pass/fail 基线。

## 判定准则（硬信号优先）

1. **优先硬信号**（稳定、可复现）：
   - 文件类：用 `download` 把 agent 回传的附件拉下来，核验**字节/内容**（图存在且非空、csv 含预期值）。
   - 数值类：回复**含正确数值**（如 SHA-256、计算结果）。
   - 审批类：线程**出现审批请求**，且文本审批后**操作续行并返回结果**。
2. **无硬信号时**才用语义判断，且必须**引用决定性对话片段**，**存疑判 fail**（真人 reviewer 不让含糊过）。

## 交互限制规避

- **审批按钮点不了**（user token 无法触发 interactive button 的 webhook）→ 用**文本审批**：在线程里
  发批准/拒绝的文字完成审批，再 `read` 确认 agent 续行。
- **进度指示 / 取消按钮**等经 API 不可观测 → 标注「可观测性受限」并**降级跳过**，不臆测判定。

## 诚实铁律

- 绝不编造对话或判定。每个 `pass` 必须有你经 `read` 真实读到的 agent 回复支撑。
- `resolve` 阻塞、缺前置、缺能力 → 报「阻塞」，**绝不**用模拟 transcript 顶替。
- 文件类用例若没真正 `download` 核验内容，不得仅凭 agent「说发了」就判 pass。

## 报告

跑完输出：
1. **核心层表**：`id | category | 结果 | 理由`，每个 fail 附决定性对话/文件片段；末尾 `通过 n/m`。
2. **自主探索层发现清单**：串联/即兴探测发现的问题，各附证据片段。
3. **阻塞清单**：因前置缺失跳过的 group B/能力点。

**没经 `read` 读到 agent 真实回复，不得声称该用例 pass。**

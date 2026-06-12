## 1. 脚手架与依赖

- [ ] 1.1 决定 Slack 客户端（D8：`slack_sdk` vs 复用 `httpx`），若引入 `slack_sdk` 则加入 pyproject dev 依赖并 `uv sync`
- [ ] 1.2 建 `tests/e2e/slack_autonomous/` 包结构：`__init__.py`、CLI 入口、把不依赖网络的纯逻辑抽到独立模块（`_pure.py`）便于 unit 覆盖
- [ ] 1.3 约定 `SLACK_E2E_*` 环境变量（token / bot_user_id / channel）读取入口，确认无任何硬编码凭据

## 2. helper 纯函数（TDD，测试先行）

- [ ] 2.1 [test] `tests/unit/test_slack_e2e_filter.py`：按 `bot_user_id` + cursor 过滤新消息（排除自身消息、排除 ≤cursor、无新消息给 `timed_out`）——先见红
- [ ] 2.2 实现过滤纯函数——同命令见绿
- [ ] 2.3 [test] `tests/unit/test_slack_e2e_io.py`：结果对象 → 单个 JSON；错误 → 含 `error` 字段 JSON + 非零 exit 的契约——见红
- [ ] 2.4 实现 JSON 输出与错误退出约定——见绿
- [ ] 2.5 [test] `tests/unit/test_slack_e2e_resolve.py`：前置校验结果结构（缺 token/bot/channel/scope → `blocked` 命名缺失项、不回退内置凭据，mock SDK 返回）——见红
- [ ] 2.6 实现 `resolve` 结果构造逻辑——见绿

## 3. helper 子命令与 Slack API 绑定

> 真实 API 调用属 e2e（§5 冒烟覆盖），不单测；本组只接线，参数解析与 JSON 契约复用 §2。

- [ ] 3.1 CLI argparse：`send`/`read`/`upload`/`download`/`resolve` 子命令与参数（channel/thread_ts/bot_user_id/token）
- [ ] 3.2 `send`：`chat.postMessage` 发文本，支持 `thread_ts`，返回 `ts`
- [ ] 3.3 `read`：`conversations.replies`/`history` 拉取 + 过滤纯函数 + 轮询超时返回空
- [ ] 3.4 `upload`：`files.getUploadURLExternal` → PUT bytes → `files.completeUploadExternal`，返回 file id
- [ ] 3.5 `download`：用 token 拉 `url_private_download` 写本地，供字节核验
- [ ] 3.6 `resolve`：`auth.test`/`users.info`/`conversations.info` 校验 token/bot/channel/scope，缺失报 `blocked`

## 4. 覆盖清单 + rubric 数据（TDD，校验先行）

- [ ] 4.1 [test] `tests/unit/test_slack_e2e_catalog.py`：清单结构校验（字段完整、id 唯一、`core` 条目有可判定 rubric、分组 A/B/C、文件标志、前置）——见红
- [ ] 4.2 编写覆盖清单数据（A 核心黑盒层约 50 点 + B 需前置配置层 + C 排除项），每条含 rubric / 文件标志 / 层级 / 前置——使校验见绿
- [ ] 4.3 确认 13 个依赖文件收发的功能点均标 file 标志且 rubric 为硬信号（附件存在 + 下载内容核验）

## 5. 真实环境 e2e 冒烟（需 `SLACK_E2E_*` + 真实 server，缺前置则 skip 不 fail）

- [ ] 5.1 `tests/e2e/test_slack_autonomous_smoke.py`：`resolve` 通过 → `send` 一句 → `read` 到 bot 回复的最小往返
- [ ] 5.2 文件往返冒烟：`upload` 一张图触发视觉，或触发 `send_file` 后 `download` 核验字节

## 6. 方法论 skill

- [ ] 6.1 写 `.claude/skills/slack-e2e-autonomous/SKILL.md`：前置检查、覆盖清单驱动、两层执行（核心回归 / 自主探索）、四种自主、判定硬信号优先 + 诚实铁律、text-approve 规避、报告格式、如何用 helper（子命令 + JSON 契约）
- [ ] 6.2 自检：不复用/不依赖旧 `slack-agent-e2e`；skill 与 helper 子命令、清单字段一致

## 7. 移除旧套件（slack-e2e-test-suite）

- [ ] 7.1 删除旧 skill 目录 `.claude/skills/slack-agent-e2e/`
- [ ] 7.2 删除旧场景目录 `tests/e2e/slack_scenarios/`（17 yaml + README + `agent.yaml.example`）
- [ ] 7.3 删除 catalog validator `tests/integration/test_slack_scenarios_catalog.py`
- [ ] 7.4 确认无活跃悬挂引用（仅 `docs/archive/jira-backfill-plan.md` 历史文档提及，保留）；`make test-pr` 与 integration 无新增失败
- [ ] 7.5 archive 阶段经 REMOVED delta 同步移除 `openspec/specs/slack-e2e-test-suite/`

## 8. 文档与收尾

- [ ] 8.1 写 `tests/e2e/slack_autonomous/README.md`：环境准备（token/scope/agent/bot/channel）、运行方式、取代旧 `slack-e2e-test-suite` 的说明
- [ ] 8.2 收尾门禁：`make test-pr` 全绿（含新增 unit 纯函数测试）、改动文件 ruff、无环境时 e2e skip 不 fail

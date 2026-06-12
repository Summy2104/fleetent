## 1. 脚手架与依赖

- [x] 1.1 决定 Slack 客户端（D8：`slack_sdk` 经 slack-bolt 传递依赖已可用，零新增）
- [x] 1.2 建 `tests/e2e/slack_autonomous/` 包结构：`__init__.py`、CLI 入口 `helper.py`、纯逻辑模块 `_pure.py`
- [x] 1.3 约定 `SLACK_E2E_*` 环境变量（token / bot_user_id / channel）读取入口，无硬编码凭据

## 2. helper 纯函数（TDD，测试先行）

- [x] 2.1 [test] `tests/unit/test_slack_e2e_filter.py`：按 `bot_user_id` + cursor 过滤新消息——先见红
- [x] 2.2 实现过滤纯函数——见绿
- [x] 2.3 [test] `tests/unit/test_slack_e2e_io.py`：JSON 输出 / 错误形态 / 退出码契约——见红
- [x] 2.4 实现 JSON 输出与错误退出约定——见绿
- [x] 2.5 [test] `tests/unit/test_slack_e2e_resolve.py`：前置校验结果（缺失 → `blocked` 命名缺失项）——见红
- [x] 2.6 实现 `build_resolve_report`——见绿

## 3. helper 子命令与 Slack API 绑定

- [x] 3.1 CLI argparse：`send`/`read`/`upload`/`download`/`resolve` 子命令与参数
- [x] 3.2 `send`：`chat.postMessage` 发文本，支持 `thread_ts`，返回 `ts`
- [x] 3.3 `read`：`conversations.replies`/`history` + 过滤纯函数 + 轮询超时返回空
- [x] 3.4 `upload`：`files_upload_v2`（封装 external upload flow），返回 file id
- [x] 3.5 `download`：用 token 拉 `url_private_download` 写本地
- [x] 3.6 `resolve`：`auth.test`/`users.info`/`conversations.info` 校验，缺失报 `blocked`

## 4. 覆盖清单 + rubric 数据（TDD，校验先行）

- [x] 4.1 [test] `tests/unit/test_slack_e2e_catalog.py`：清单结构校验——见红
- [x] 4.2 编写覆盖清单数据（A 核心 ~40 + B 需前置 8 + C 排除 2），含 rubric / 文件标志 / 层级 / 前置——见绿
- [x] 4.3 14 个依赖文件收发的功能点均标 `needs_file` 且 rubric 为硬信号（附件存在 + 下载内容核验）

## 5. 真实环境 e2e 冒烟（需 `SLACK_E2E_*` + 真实 server，缺前置则 skip 不 fail）

- [x] 5.1 `tests/e2e/test_slack_autonomous_smoke.py`：`resolve` → `send` → `read` 最小往返（无环境 2 skipped 已验证）
- [x] 5.2 文件往返冒烟：`upload` 一张图 → `read` 到 bot 回复

## 6. 方法论 skill

- [x] 6.1 写 `.claude/skills/slack-e2e-autonomous/SKILL.md`：前置检查、覆盖清单驱动、两层执行、四种自主、判定硬信号优先 + 诚实铁律、text-approve 规避、报告格式、helper 用法
- [x] 6.2 自检：不复用/不依赖旧 `slack-agent-e2e`；skill 与 helper 子命令、清单字段一致

## 7. 移除旧套件（slack-e2e-test-suite）

- [x] 7.1 删除旧 skill 目录 `.claude/skills/slack-agent-e2e/`
- [x] 7.2 删除旧场景目录 `tests/e2e/slack_scenarios/`（17 yaml + README + `agent.yaml.example`）
- [x] 7.3 删除 catalog validator `tests/integration/test_slack_scenarios_catalog.py`
- [x] 7.4 无活跃悬挂引用（仅 `docs/archive/jira-backfill-plan.md` 历史文档提及，保留）；`make test-pr` 2906 passed 无新增失败
- [x] 7.5 REMOVED delta（`specs/slack-e2e-test-suite/spec.md`）就位，archive 时同步移除 `openspec/specs/slack-e2e-test-suite/`

## 8. 文档与收尾

- [x] 8.1 写 `tests/e2e/slack_autonomous/README.md`：环境准备、运行方式、取代旧套件的说明
- [x] 8.2 收尾门禁：`make test-pr` 全绿（2906 passed + 层边界）、改动文件 ruff 通过、无环境时 e2e skip 不 fail

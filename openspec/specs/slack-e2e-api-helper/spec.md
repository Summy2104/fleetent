# slack-e2e-api-helper Specification

## Purpose
TBD - created by archiving change slack-e2e-autonomous-suite. Update Purpose after archive.
## Requirements
### Requirement: JSON 接口的纯收发工具

The helper SHALL be a command-line tool exposing the subcommands `send`, `read`, `upload`, `download`, and `resolve`. Every successful invocation SHALL emit exactly one JSON object to stdout; on error it SHALL emit a JSON object carrying an `error` field and exit non-zero. The helper MUST NOT embed any LLM call or any pass/fail judgement — it performs Slack Web API I/O only. All decision-making lives in the autonomous driver, keeping the helper a pure "hands" layer.

#### Scenario: 每个子命令输出单个结构化 JSON
- **WHEN** any subcommand completes successfully
- **THEN** stdout contains exactly one well-formed JSON object describing the result and nothing else

#### Scenario: helper 不含判定或模型逻辑
- **WHEN** the helper source is inspected
- **THEN** it imports no model/LLM client and produces no `verdict`/`pass`/`fail` field

### Requirement: 以 user 身份发消息

`send` SHALL post a text message to a given channel using a user OAuth token (`xoxp-`), optionally replying into a thread when `thread_ts` is supplied, and SHALL return the posted message `ts`.

#### Scenario: 发消息返回 ts
- **WHEN** `send` is called with a channel and text
- **THEN** the message appears in that channel and the returned JSON includes its `ts`

#### Scenario: 回到指定线程
- **WHEN** `send` is called with a `thread_ts`
- **THEN** the message is posted as a reply within that thread

### Requirement: 按 bot_user_id 过滤读取 agent 回复

`read` SHALL fetch messages from a given thread (or channel) and return only messages authored by the configured `bot_user_id` that are newer than a supplied cursor. It SHALL support polling with a bounded timeout, returning an empty result (not an error) when no new bot message has arrived.

#### Scenario: 只返回 bot 的新消息
- **WHEN** `read` is called after the test user has sent a message and the bot has replied
- **THEN** the result contains the bot's reply and excludes the test user's own messages and any messages at or before the cursor

#### Scenario: 无回复时轮询超时返回空
- **WHEN** `read` polls and the bot has not replied within the timeout
- **THEN** the helper returns an empty message list with a `timed_out` indicator rather than an error

### Requirement: 文件上传给 agent

`upload` SHALL upload a local file as a Slack attachment to the target channel/thread using the Slack external upload flow (`files.getUploadURLExternal` → PUT bytes → `files.completeUploadExternal`), and SHALL return the resulting file id. This is the core capability the MCP channel cannot provide and the reason this suite uses the Web API.

#### Scenario: 上传文件成为线程附件
- **WHEN** `upload` is called with a local image or document and a target thread
- **THEN** the file appears as a downloadable attachment in that thread and the returned JSON includes its file id

### Requirement: 下载 agent 回传文件以核验

`download` SHALL download a file the agent posted (via its `url_private_download`) using the token, writing it to a local path so its bytes/content can be verified.

#### Scenario: 下载 bot 附件并保全字节
- **WHEN** the agent posts a generated file and `download` is given that file reference
- **THEN** the file is written locally with its content intact for verification

### Requirement: 前置校验与缺失即阻塞，参数化不落 secret

`resolve` SHALL validate that the token is usable, the `bot_user_id` exists, and the channel is reachable. Token, `bot_user_id`, and channel SHALL be read from CLI arguments or `SLACK_E2E_*` environment variables and MUST NOT be hardcoded or committed. On any missing or invalid precondition the helper SHALL emit a structured `blocked` result naming the missing item and exit non-zero — never fabricating success nor falling back to a built-in default.

#### Scenario: 前置缺失报 blocked
- **WHEN** the token is invalid or the channel is unreachable
- **THEN** `resolve` returns a `blocked` JSON naming the failing precondition and exits non-zero

#### Scenario: 缺 token 不回退到内置凭据
- **WHEN** no `SLACK_E2E_*` token is present
- **THEN** the helper errors clearly and does not fall back to any embedded credential


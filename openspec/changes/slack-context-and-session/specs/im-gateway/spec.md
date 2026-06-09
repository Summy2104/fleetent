## MODIFIED Requirements

### Requirement: Normalize Slack messages
The system SHALL receive Slack events via Socket Mode and normalize them into a `NormalizedMessage` before routing to the agent pipeline. Session id SHALL be derived **thread-first**: the bot replies inside the thread rooted at the user's message (`thread_root = thread_ts or the message's own ts`), and the session id is keyed by that thread root — `slack:dm:{user_id}:{thread_root}` for DMs and `slack:thread:{channel_id}:{thread_root}` for channels. A top-level message and its follow-ups inside the bot-created thread therefore share one session; each new top-level message (or new assistant-pane conversation) starts a new session.

#### Scenario: Slack DM top-level message
- **WHEN** a Slack DM top-level message arrives from user `U123` with ts `100.1`
- **THEN** the bot replies within a thread rooted at `100.1`
- **AND** the adapter derives `session_id="slack:dm:U123:100.1"`

#### Scenario: Slack DM follow-up in the bot-created thread
- **WHEN** user `U123` replies inside that thread (`thread_ts="100.1"`)
- **THEN** the adapter derives the same `session_id="slack:dm:U123:100.1"` (conversation stays continuous)

#### Scenario: Slack assistant-pane new conversation
- **WHEN** a new assistant-pane conversation starts with assistant `thread_ts="200.2"` for user `U123`
- **THEN** the adapter derives `session_id="slack:dm:U123:200.2"` (a new session distinct from prior conversations)

#### Scenario: Slack channel @mention starts a thread
- **WHEN** a channel `C9` top-level @mention arrives with ts `300.3`
- **THEN** the bot replies in a thread rooted at `300.3`
- **AND** the adapter derives `session_id="slack:thread:C9:300.3"`

#### Scenario: Slack channel thread reply
- **WHEN** a channel `C9` message arrives with `thread_ts="300.3"`
- **THEN** the adapter derives `session_id="slack:thread:C9:300.3"` (shared by all participants in that thread)

#### Scenario: DM and channel do not collide
- **WHEN** user `U123` has both a DM conversation and a channel @mention
- **THEN** their session ids are namespaced distinctly (`slack:dm:...` vs `slack:thread:...`) and never share history

### Requirement: Unified message format
The system SHALL define `NormalizedMessage` as the contract between adapters and the agent pipeline.

#### Scenario: NormalizedMessage fields
- **WHEN** any adapter normalizes a message
- **THEN** the resulting object MUST contain: `platform`, `session_id`, `user_id`, `text`, `attachments` (list, may be empty), `reply_func` (async callable)
- **AND** MAY contain `progress_func` (optional async callable, default `None`); when `None` the pipeline behaves identically to the previous version
- **AND** MAY contain `session_context` (optional, default `None`) carrying sender/channel metadata; when `None` no context is injected

#### Scenario: Adapter without optional fields preserves existing behavior
- **WHEN** an adapter constructs `NormalizedMessage` without `progress_func` or `session_context`
- **THEN** normalizer.route() runs identically to the pre-change version with no side effects

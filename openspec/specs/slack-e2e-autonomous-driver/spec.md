# slack-e2e-autonomous-driver Specification

## Purpose
TBD - created by archiving change slack-e2e-autonomous-suite. Update Purpose after archive.
## Requirements
### Requirement: 覆盖清单驱动与分组门控

The driver SHALL run from a structured capability coverage catalog. Each entry SHALL carry an id, capability name, category, trigger hint, observable success signal (rubric), a file-dependency flag, a layer (`core` or `explore`), and any preconditions. The catalog SHALL be partitioned into group A (core black-box, in baseline), group B (requires-precondition, environment-optional), and group C (black-box-unobservable, excluded). The catalog is the fixed, regressable set of test targets.

#### Scenario: 清单条目结构完整且 core 可判定
- **WHEN** the catalog is loaded
- **THEN** every entry has all required fields with a unique id, and every `core` entry carries a concretely judgeable rubric

#### Scenario: B 层前置缺失则跳过并报阻塞
- **WHEN** a group-B entry's precondition is absent (e.g. a KB connector is not configured)
- **THEN** the driver skips it and reports it as blocked with the missing precondition, and group-C entries are not attempted

### Requirement: 核心回归层与自主探索层分离

The driver SHALL separate a core regression layer (fixed rubric, contributing to a pass/fail baseline comparable across runs) from an autonomous exploration layer (improvised cross-scenario chaining and self-generated probes, producing a findings report that does NOT alter the baseline).

#### Scenario: 探索层不动核心基线
- **WHEN** the exploration layer surfaces an extra finding during a run
- **THEN** the core pass/fail baseline for that run is unchanged and the finding is recorded separately

### Requirement: 四种自主能力

Within the core layer the driver MAY exercise path autonomy (free-form conversation to reach a target) and on-the-fly probing (adding checks based on the agent's actual replies, recorded as findings). Within the exploration layer the driver MAY chain capabilities across scenarios and self-generate new probes. Autonomy SHALL never weaken a core verdict: the rubric remains the sole pass/fail anchor.

#### Scenario: 同一能力点允许不同对话路径
- **WHEN** the same core capability is exercised on different runs via different conversational paths
- **THEN** the verdict is pass whenever the rubric is satisfied, regardless of the path taken

### Requirement: 判定硬信号优先，LLM 裁判兜底

Verdicts SHALL prefer observable hard signals — an attachment appears and its downloaded content contains the expected data, a reply contains the correct numeric value, an approval request appears and the gated action resumes after approval. Only when no hard signal exists SHALL the driver fall back to LLM-as-judge semantic assessment, which MUST cite the decisive transcript fragment and MUST judge fail when genuinely ambiguous.

#### Scenario: 文件类用例用硬信号判定
- **WHEN** a file-dependent capability is judged
- **THEN** the verdict rests on attachment presence plus downloaded-content verification rather than on semantic description alone

### Requirement: 黑盒执行与诚实铁律

The driver SHALL judge solely from Slack-visible content (the conversation plus files sent and received) and MUST NOT read fleetent internal logs. It MUST NOT mark any capability `pass` without having read a real agent reply, and SHALL report blocked — never fabricate — when a precondition or capability is missing.

#### Scenario: 无真实回复不判 pass
- **WHEN** the agent produces no reply within the turn or timeout budget
- **THEN** the capability is recorded as fail or blocked with the reason, and no synthetic transcript is created

### Requirement: 交互限制规避

For actions a user token cannot perform via the API (notably clicking an approval interactive button), the driver SHALL use a message-based path such as text-approve to complete them. For signals unobservable or unreachable via the API (e.g. progress-status indicators, cancel buttons), the driver SHALL annotate the limitation and degrade by skipping rather than guessing a verdict.

#### Scenario: 审批门用文本审批完成
- **WHEN** a capability requires approving a gated tool call
- **THEN** the driver completes the approval through the text-approve path and verifies the gated action then proceeds

### Requirement: 可回归报告

After a run the driver SHALL produce a report containing a core-layer table (id | category | result | reason), a `通过 n/m` line, and an exploration-layer findings list. Every fail and every finding SHALL be backed by a decisive transcript or file excerpt.

#### Scenario: 报告含判定与证据
- **WHEN** a run completes
- **THEN** the report shows each core capability's verdict with a cited evidence excerpt and an overall pass count


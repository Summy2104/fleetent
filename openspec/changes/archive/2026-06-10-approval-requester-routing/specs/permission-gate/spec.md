# permission-gate Delta

## ADDED Requirements

### Requirement: Requester sentinel approval routing

The approval routing configuration SHALL accept the sentinel value `requester` in any
`approvers` list (alongside `platform:target_id` addresses). When resolved for a pending
approval, the gate SHALL deliver the approval prompt back to the current conversation via
the run's `reply_func` (including the approval id and the `approve <id>` / `reject <id>`
instructions) instead of contacting an outbound address. Sentinel and outbound addresses
MAY be mixed in one list; the first decision from any authorized actor wins.

#### Scenario: requester sentinel routes the prompt to the current conversation

- **WHEN** `approval_routing` resolves to `approvers: ["requester"]` for a pending tool call
- **THEN** the approval prompt is sent via `reply_func` to the current conversation and no
  outbound DM is attempted

#### Scenario: requester decides in-conversation

- **WHEN** the requesting user replies `approve <id>` in the same conversation
- **THEN** the gate resolves the approval and the tool call proceeds

#### Scenario: mixed list notifies both channels

- **WHEN** `approvers: ["requester", "slack:U_ADMIN"]` resolves for a pending tool call
- **THEN** the prompt is sent via `reply_func` AND the outbound approver is contacted, and
  the first decision from either authorized actor resolves the request

#### Scenario: unconfigured deployments are unaffected

- **WHEN** no `requester` sentinel appears in any `approvers` list
- **THEN** routing behavior is identical to the pre-change implementation (outbound only,
  default-closed when no approver is reachable)

### Requirement: Approval decision authorization

The gate SHALL record, per pending approval, the set of authorized decision actors:
the requester's user id when the `requester` sentinel routed the prompt, and the target
ids of outbound approvers actually reached. `resolve()` SHALL reject a decision whose
`approver_user_id` is not in the pending approval's authorized set — returning False,
leaving the approval pending, and logging a warning.

#### Scenario: bystander in a channel cannot decide

- **WHEN** an approval prompt was routed to the requester in a channel and a different
  user replies `approve <id>`
- **THEN** `resolve()` returns False, the approval stays pending, and a warning is logged

#### Scenario: notified outbound approver can decide

- **WHEN** an outbound approver who was actually contacted replies `approve <id>`
- **THEN** `resolve()` accepts the decision and execution proceeds

#### Scenario: un-notified address cannot decide

- **WHEN** a user whose address appears in configuration but was NOT reached during
  notification replies `reject <id>`
- **THEN** `resolve()` returns False and the approval stays pending

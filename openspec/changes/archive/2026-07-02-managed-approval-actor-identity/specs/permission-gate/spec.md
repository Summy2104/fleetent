## MODIFIED Requirements

### Requirement: Approval decision authorization

The gate SHALL record, per pending approval, the set of authorized decision actors:
the requester's user id when the `requester` sentinel routed the prompt, and the target
ids of outbound approvers actually reached. `resolve()` SHALL reject a decision whose
`approver_user_id` is not in the pending approval's authorized set — returning False,
leaving the approval pending, and logging a warning.

IM approval decisions (interactive button clicks and text `approve`/`reject` commands)
SHALL identify the acting user in the **same identity space** as the recorded authorized
actors. Because the authorized set holds the run's `principal.user_id` — which under managed
identity resolution is the internal user id, not the raw platform id — the IM edge SHALL
resolve the acting user's platform id through the same identity seam (`resolve_identity`)
used for inbound messages before passing it as `approver_user_id`. Under standalone (no
injected resolver) this resolution returns the raw platform id unchanged, so single-space
deployments are unaffected. A non-real / unresolvable acting id SHALL fail closed (the
decision is rejected, the approval stays pending).

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

#### Scenario: managed requester can decide their own prompt via button/command

- **WHEN** under managed identity resolution (platform id → internal user id) the requester
  clicks the approval button (or sends `approve <id>`) for a prompt routed to them
- **THEN** the IM edge resolves the acting platform id to the same internal user id recorded
  in the authorized set, so `resolve()` accepts the decision and the suspended run resumes
  (no `approval_unauthorized_actor` for the requester's own decision)

#### Scenario: standalone decision identity unchanged

- **WHEN** no identity resolver is injected (standalone) and the acting user decides
- **THEN** the acting platform id is used verbatim (resolution is a no-op) and authorization
  behaves exactly as before this change

#### Scenario: unresolvable acting id fails closed

- **WHEN** the acting user's platform id cannot be resolved (empty / non-real identity)
- **THEN** the decision is rejected and the approval stays pending (no ghost actor authorized)

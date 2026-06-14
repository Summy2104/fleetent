## MODIFIED Requirements

### Requirement: invoke_agent built-in tool
A built-in tool `invoke_agent(agent_name: str, message: str) -> str` SHALL allow a parent agent to dispatch a message to another registered agent and receive its reply. The tool SHALL NOT be approval-gated: `approval_policy.risk_for` SHALL classify it as `none` (dispatching to a sub-agent is not proactive outreach to a recipient outside the current conversation). The sub-agent's own outbound actions remain individually governed by the permission gate when that sub-agent runs, so a parent-level gate would be redundant.

#### Scenario: Successful invocation
- **WHEN** the parent agent calls `invoke_agent(agent_name="analyst", message="summarize Q4")`
- **THEN** the target agent runs with the snapshot of `analyst`'s active version and returns its final reply as the tool result, without an approval prompt for the dispatch itself

#### Scenario: Unknown agent
- **WHEN** `invoke_agent` is called with a name that does not exist (or is soft-deleted)
- **THEN** the tool returns a string `agent {name!r} not found` without raising

#### Scenario: Invocation needs no approval
- **WHEN** `invoke_agent` is called and `reply_func` is set
- **THEN** the dispatch is not gated; `approval_policy.risk_for("invoke_agent", …)` returns `none` and the target agent runs directly

#### Scenario: Sub-agent's own gated actions still apply
- **WHEN** a sub-agent invoked via `invoke_agent` itself attempts a proactive `send_im_message` to a third party
- **THEN** that send is gated by the permission gate within the sub-agent's run, independent of the (ungated) dispatch

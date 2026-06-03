## ADDED Requirements

### Requirement: KB to Agent binding matrix
The system SHALL persist KB↔Agent bindings in an `agent_kbs` table scoped by (tenant_id, kb_id, agent_id), and SHALL expose binding management both from the KB detail view (`/admin/kb/{kb_id}/agents`) and from the agent detail view (`/admin/agents/{agent_id}/kbs`). Bindings SHALL be admin-only to change and viewer-readable.

#### Scenario: Bind a KB to an agent
- **WHEN** an admin binds kb_id "support" to agent "support-bot"
- **THEN** the binding is persisted in `agent_kbs` and an audit entry (`kb_bind_agent`) is written

#### Scenario: View bindings from both sides
- **WHEN** an admin or viewer opens a KB's binding list or an agent's KB list
- **THEN** the consistent set of (kb_id, agent_id) bindings for the current tenant is shown

#### Scenario: Unbind is audited
- **WHEN** an admin removes a KB↔Agent binding
- **THEN** the binding is deleted and an audit entry (`kb_unbind_agent`) is written

#### Scenario: Viewer cannot change bindings
- **WHEN** a viewer attempts to bind or unbind
- **THEN** the request returns 403

### Requirement: Binding relation backs scope limiting and delete protection
The `agent_kbs` binding relation SHALL serve as the authoritative source for long-term-ctx to limit recall to the agent's bound kb_ids, and SHALL back KB archive/delete binding protection. The management plane maintains the bindings only; injection and token-budget semantics belong to long-term-ctx.

#### Scenario: Bound KBs are queryable per agent
- **WHEN** long-term-ctx requests the kb_ids bound to a given agent in a tenant
- **THEN** the binding store returns the agent's bound, non-archived kb_ids

#### Scenario: Bindings drive archive protection
- **WHEN** a KB has at least one row in `agent_kbs`
- **THEN** an archive attempt on that KB is blocked and the binding agents are listed

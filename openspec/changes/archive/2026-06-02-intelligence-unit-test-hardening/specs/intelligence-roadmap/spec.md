## ADDED Requirements

### Requirement: Unit test hardening is tracked after MVP foundation
intelligence-roadmap SHALL track unit test hardening as a post-foundation quality item rather than a new runtime feature.

#### Scenario: Roadmap records unit hardening scope
- **WHEN** `intelligence-unit-test-hardening` is proposed
- **THEN** roadmap docs describe it as quality hardening for observability、memory、long-term context、reflection、vector-store、knowledge-base and deployment/config boundaries
- **AND** roadmap docs state that it does not change runtime behavior or MVP feature scope

#### Scenario: Roadmap records remaining test strategy
- **WHEN** `intelligence-unit-test-hardening` is archived
- **THEN** roadmap docs record the final scoped unit coverage and keep integration / evaluation tests as authoritative for DB runtime, source-of-truth rebuild, connector sync and effect evaluation

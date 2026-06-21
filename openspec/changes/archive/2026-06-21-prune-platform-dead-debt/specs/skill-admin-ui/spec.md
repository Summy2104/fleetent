## MODIFIED Requirements

### Requirement: Skill proposal review
The console SHALL list skill proposals and let an admin view a proposal diff. Approve / reject are not offered from the console: proposal approval is agent-owned and delivered to the approver via DM, with the console acting as a read-only projection.

#### Scenario: List and view a proposal diff
- **WHEN** an admin opens the skill proposals list and selects a proposal
- **THEN** the console lists proposals via `GET /admin/skills/proposals` and renders the diff via `GET /admin/skills/proposals/{id}/diff`, with no approve/reject controls

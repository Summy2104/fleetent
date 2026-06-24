## MODIFIED Requirements

### Requirement: Upload or create with frontmatter validation and audit gating
The system SHALL expose `POST /admin/skills` to upload a `SKILL.md` (or a directory package with scripts/templates) or create one inline. Before publishing, the system SHALL validate the YAML frontmatter and invoke the skill domain's security audit, then gate the outcome by verdict: a `rejected` verdict SHALL NOT publish and SHALL quarantine the skill; a `suspicious` verdict SHALL publish with a list mark; a `pass` verdict SHALL publish. Publishing SHALL trigger a hot reload.

When creating a skill inline (request carries `content`), publishing SHALL persist the content to the skills pool as `<skills_dir>/<name>/SKILL.md` before the hot reload, so the skill is readable back via `GET /admin/skills/{name}/content`, discoverable by the registry rescan, and deliverable to agents by node skill-file sync. The destination directory name SHALL be validated against path traversal; an unsafe skill name SHALL be rejected (422) with nothing persisted. A `rejected` (quarantined) skill SHALL NOT be persisted to disk.

#### Scenario: Valid skill publishes and takes effect immediately
- **WHEN** an admin uploads a skill with valid frontmatter that passes the security audit
- **THEN** the skill is published, a hot reload is triggered, it appears in the list, and it is matchable for subsequent requests without a service restart
- **AND** the upload action is audited

#### Scenario: Inline-created skill content is persisted and readable
- **WHEN** an admin creates a skill inline via `POST /admin/skills` with `content` that passes the audit
- **THEN** the content is written to `<skills_dir>/<name>/SKILL.md`
- **AND** `GET /admin/skills/{name}/content` returns the original content
- **AND** the registry rescan indexes the skill
- **AND** for an agent bound to the skill, the node skill-file bundle (`skill_bundles_for_agent`) includes the skill with its `SKILL.md`

#### Scenario: Unsafe skill name rejected without persisting
- **WHEN** an admin creates a skill inline with an unsafe name (containing `..` or a path separator)
- **THEN** the response is 422 and nothing is written to the skills pool

#### Scenario: Injection-flagged skill is quarantined, not published
- **WHEN** an admin uploads a skill whose content triggers a `rejected`-level audit rule
- **THEN** the skill is not published and enters quarantine, the response lists the matched injection patterns, the skill participates in no matching/injection, and the event is audited
- **AND** the content is NOT written to the skills pool

#### Scenario: Suspicious skill publishes but is marked
- **WHEN** an admin uploads a skill that triggers a `suspicious`-level rule
- **THEN** the skill is published and matchable but marked "suspicious" in the list, and the detail view shows the matched rules for review

#### Scenario: Invalid frontmatter rejected
- **WHEN** the uploaded skill has malformed or incomplete YAML frontmatter
- **THEN** the response is 422 with the validation error, the skill is not published, and nothing is persisted

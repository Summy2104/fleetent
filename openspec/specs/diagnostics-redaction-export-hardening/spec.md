# diagnostics-redaction-export-hardening Specification

## Purpose
TBD - created by archiving change diagnostics-redaction-export-hardening. Update Purpose after archive.
## Requirements
### Requirement: Diagnostics manifest

Diagnostics export SHALL produce a manifest listing exported artifacts, skipped artifacts, redaction status,
creation time and source summary.

#### Scenario: Manifest lists skipped forbidden artifact
- **WHEN** diagnostics export omits a forbidden artifact such as a SQLite main database or secret file
- **THEN** the manifest records the skip reason without including the artifact contents

### Requirement: Default summary-only export

Diagnostics export SHALL NOT include secret payloads, SQLite main database files, backups, full prompt/reply
transcripts or KB document bodies by default.

#### Scenario: Secret file is not exported
- **WHEN** a configured secret file exists under the deployment secrets directory
- **THEN** diagnostics export excludes the file contents
- **AND** the manifest records only a redacted reference summary

### Requirement: Redacted evidence output

Diagnostics export SHALL redact token-like, credential-like and bearer values from config, trace and connector
summaries. Optional payload summary mode SHALL remain truncated and redacted.

#### Scenario: Trace payload summary is redacted
- **WHEN** safe payload summary mode is enabled
- **THEN** exported payload summaries are truncated and redacted
- **AND** raw transcript or KB document body is not exported


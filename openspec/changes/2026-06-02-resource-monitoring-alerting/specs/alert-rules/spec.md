## ADDED Requirements

### Requirement: Threshold plus duration alert rules
An admin SHALL be able to define an alert rule on any metric with a threshold, a duration (must be continuously violated for N minutes before triggering, to avoid flapping), a severity (warning or critical), and an active window. A rule SHALL trigger only when the metric continuously violates the threshold for the configured duration; a momentary spike that does not persist SHALL NOT trigger. Rule create/update/delete SHALL be written to the audit log.

#### Scenario: Threshold with duration triggers, spike does not (场景 89)
- **WHEN** an admin configures "host CPU > 85% for 5 minutes, severity warning, channels = email + in-app" and CPU stays above 85% for 6 minutes
- **THEN** one warning alert is triggered and email and in-app alert center each receive a notification; and a momentary CPU spike that does not persist for the duration does not trigger

#### Scenario: Severity is a closed enumeration
- **WHEN** an admin sets a rule's severity
- **THEN** only warning or critical is accepted and the value is stored as a discrete enum, not a free-form string

#### Scenario: Active window scopes evaluation
- **WHEN** a rule has an active window and the metric violates the threshold outside that window
- **THEN** the rule does not trigger; it triggers only when the violation falls within the active window

### Requirement: Rule enable, disable, and clone
An admin SHALL be able to enable, disable, and clone an alert rule. A disabled rule SHALL NOT be evaluated.

#### Scenario: Disabled rule is not evaluated
- **WHEN** an admin disables a rule and the metric later violates its threshold for the duration
- **THEN** no alert is triggered for that rule until it is re-enabled

#### Scenario: Clone a rule
- **WHEN** an admin clones an existing rule
- **THEN** a new rule with the same threshold/duration/severity/channels is created independently and can be edited without affecting the original

### Requirement: Static threshold and optional rate-of-change rules
A rule SHALL support a static threshold and MAY optionally support a year-over-year / period-over-period surge rule. Surge rules SHALL reuse the same windowed sampling interface as static-threshold evaluation.

#### Scenario: Surge rule triggers on relative increase
- **WHEN** a period-over-period surge rule is configured (e.g. "increase by more than X% vs the previous period") and the metric increases beyond that percentage
- **THEN** the surge rule triggers using the same windowed sampling used by static-threshold rules

### Requirement: Rule management is admin-only
Creating, modifying, deleting, or cloning alert rules SHALL be restricted to admin/built_in_admin. Viewers SHALL NOT modify rules.

#### Scenario: Viewer cannot modify rules (场景 95)
- **WHEN** a viewer attempts to create, modify, or delete an alert rule
- **THEN** the controls are hidden or the request is rejected with 403, and the viewer may only browse the dashboard and alert history

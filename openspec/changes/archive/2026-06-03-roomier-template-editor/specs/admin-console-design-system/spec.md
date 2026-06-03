## ADDED Requirements

### Requirement: Themed, comfortably sized text editors

Multi-line text editors (`textarea`) in the admin console SHALL share the same dark theme styling as text inputs (background, border, color, full width) instead of relying on the browser default. The template editor modal SHALL provide a comfortably sized system-prompt editor so an operator can author a prompt without a cramped field.

#### Scenario: Textarea matches the dark theme

- **WHEN** a modal containing a `textarea` is shown
- **THEN** the textarea uses the console's themed background and border, not the browser default white field

#### Scenario: System-prompt editor is roomy

- **WHEN** the operator opens the template editor modal
- **THEN** the system-prompt editor is tall enough to comfortably write a multi-line prompt

# admin-console-design-system Specification

## Purpose
Define the visual and interaction design system for the self-contained admin console: a left sidebar navigation shell, centralized design tokens, consistent per-module page headers, reusable table presentation, in-app feedback/confirmation, empty/loading states, preserved role gating and secret handling, and basic accessibility.

## Requirements
### Requirement: Sidebar navigation layout
The admin console SHALL present navigation as a fixed left sidebar listing grouped sections (Access / Agents & Skills / Models & Connectors / Ops / Audit) and the modules within each, with the right side reserved for module content. The sidebar SHALL preserve the existing `switchGroup()` / `switchTab()` JavaScript contract and `data-group` / `data-tab` markers so module wiring and behavior are unchanged.

#### Scenario: Operator navigates via sidebar
- **WHEN** an operator clicks a module item in the sidebar
- **THEN** the corresponding module section is shown, its sidebar item is marked active, and the module's loader runs

#### Scenario: Existing modules remain reachable
- **WHEN** the console renders the sidebar
- **THEN** every previously available module (users, im, agents, skills, kb, providers, connectors, oauth, stats, monitoring, sessions, askit, audit) is reachable through it

#### Scenario: Narrow viewport collapses sidebar
- **WHEN** the viewport is narrow
- **THEN** the sidebar collapses to a toggleable form and the content area uses the full width

### Requirement: Design token layer
The console SHALL define a centralized set of design tokens (color scale, spacing, radius, typography, elevation) as CSS custom properties, and component styles SHALL reference those tokens rather than hard-coded values.

#### Scenario: Tokens drive theming
- **WHEN** a token value changes
- **THEN** components referencing that token reflect the new value without per-component edits

### Requirement: Consistent page header per module
Each module SHALL render a page header containing the module title, an actions slot (e.g. create/refresh), and a filter/search slot, so every module presents a consistent operator surface.

#### Scenario: Module shows page header
- **WHEN** a module is opened
- **THEN** its page header shows the title and the module's primary actions

### Requirement: Reusable data table presentation
Tabular data SHALL render through a shared table presentation with a sticky header, row hover, and a horizontal scroll container so wide modules do not break the layout.

#### Scenario: Wide table scrolls without breaking layout
- **WHEN** a module's table has more columns than fit the viewport
- **THEN** the table scrolls horizontally within its container and the surrounding layout is unaffected

### Requirement: In-app feedback and confirmation
The console SHALL surface success/error feedback through in-app toast notifications and SHALL request confirmation for destructive actions through an in-app confirm dialog, replacing native `alert()` and `confirm()`. Destructive actions SHALL remain admin-only and continue to send required confirmation headers to the backend.

#### Scenario: Action shows toast
- **WHEN** an action succeeds or fails
- **THEN** a toast conveys the outcome without a native dialog

#### Scenario: Destructive action asks for confirmation
- **WHEN** an admin triggers a destructive action
- **THEN** an in-app confirm dialog appears and the action proceeds only on confirmation

### Requirement: Empty and loading states
Lists SHALL show a loading indicator while data is being fetched and an empty state when no records exist, instead of a blank table body.

#### Scenario: Empty list shows empty state
- **WHEN** a module's list returns no records
- **THEN** an empty-state message is shown instead of a blank table

#### Scenario: Pending list shows loading
- **WHEN** a module's data is being fetched
- **THEN** a loading indicator is shown until results render

### Requirement: Role gating and secret handling preserved
Under the redesigned components, viewer-role users SHALL NOT see write controls, and credential fields SHALL remain masked password inputs that are never prefilled with stored secrets.

#### Scenario: Viewer sees no write controls
- **WHEN** a viewer-role user opens any module
- **THEN** create/edit/destructive controls are hidden

#### Scenario: Secret field not prefilled
- **WHEN** an admin edits a record with a stored credential
- **THEN** the credential field renders empty as a masked password input and leaving it blank keeps the current value

### Requirement: Basic accessibility
The console SHALL provide visible focus styling, aria labelling on navigation and dialogs, and keyboard dismissal of modals.

#### Scenario: Modal dismissable by keyboard
- **WHEN** a modal or dialog is open and the operator presses Escape
- **THEN** the modal closes


### Requirement: Active tab persists across reload

The admin console SHALL reflect the active tab in the URL (`location.hash`) whenever the tab changes, and SHALL restore that tab on load. When the URL carries no tab or an unknown tab, the console SHALL fall back to the default `users` tab.

#### Scenario: Reload stays on the current tab

- **WHEN** the user is on the Agents tab and reloads the page
- **THEN** the console reads the tab from `location.hash` and restores the Agents tab instead of jumping to Users

#### Scenario: Missing or unknown tab falls back to default

- **WHEN** the page loads with no hash or a hash that is not a known tab
- **THEN** the console shows the default `users` tab


### Requirement: System-generated resource ids

Admin create forms that require a unique resource `id` SHALL generate that id automatically and present it read-only; the user SHALL NOT type or edit the id. This applies to the create forms for agent templates, knowledge bases, model providers, and OAuth connectors. Edit forms SHALL continue to show the existing id read-only. The generated id SHALL be sent through the existing create endpoints unchanged.

#### Scenario: Create form auto-fills a read-only id

- **WHEN** the operator opens a create form for a template, knowledge base, provider, or connector
- **THEN** the id field is pre-filled with a generated value and is read-only, so the operator cannot type or change it

#### Scenario: Generated id is submitted on create

- **WHEN** the operator saves a newly created resource
- **THEN** the console submits the generated id through the existing create endpoint


### Requirement: Themed, comfortably sized text editors

Multi-line text editors (`textarea`) in the admin console SHALL share the same dark theme styling as text inputs (background, border, color, full width) instead of relying on the browser default. The template editor modal SHALL provide a comfortably sized system-prompt editor so an operator can author a prompt without a cramped field.

#### Scenario: Textarea matches the dark theme

- **WHEN** a modal containing a `textarea` is shown
- **THEN** the textarea uses the console's themed background and border, not the browser default white field

#### Scenario: System-prompt editor is roomy

- **WHEN** the operator opens the template editor modal
- **THEN** the system-prompt editor is tall enough to comfortably write a multi-line prompt

### Requirement: List modules expose a working row search
Every module that renders a list/table of rows SHALL populate the page header's filter/search slot with a search input that filters the already-rendered rows client-side, matching the operator surface of the card-based modules. The legacy table modules — Knowledge Base, Sessions, Monitoring, and Statistics — SHALL conform: each shows a search input (not an empty filter slot) that narrows visible rows by that module's natural identifying fields (Knowledge Base by kb_id/description, Sessions by session id/agent/origin, Monitoring by metric/target across rules and alerts, Statistics by user). When a search matches nothing, the module SHALL show its empty state rather than a blank table.

#### Scenario: Legacy list module shows a search box
- **WHEN** an operator opens Knowledge Base, Sessions, Monitoring, or Statistics
- **THEN** the page header's filter slot contains a search input (no longer empty)

#### Scenario: Search narrows the visible rows
- **WHEN** the operator types a term that matches some rows
- **THEN** only rows matching the term (by the module's identifying fields) remain visible, and clearing the term restores all rows

#### Scenario: No-match shows the empty state
- **WHEN** the operator types a term that matches no rows
- **THEN** the module shows its empty state instead of a blank table

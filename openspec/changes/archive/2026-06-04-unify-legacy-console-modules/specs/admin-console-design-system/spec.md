## ADDED Requirements

### Requirement: List modules expose a working row search
Every module that renders a list/table of rows SHALL populate the page header's filter/search slot with a search input that filters the already-rendered rows client-side, matching the operator surface of the card-based modules. The legacy table modules — Knowledge Base, Sessions, Monitoring, and Statistics — SHALL conform: each shows a search input (not an empty filter slot) that narrows visible rows by that module's natural identifying fields (Knowledge Base by kb_id/description, Sessions by session id/user/agent, Monitoring by alert/metric name, Statistics by user). When a search matches nothing, the module SHALL show its empty state rather than a blank table.

#### Scenario: Legacy list module shows a search box
- **WHEN** an operator opens Knowledge Base, Sessions, Monitoring, or Statistics
- **THEN** the page header's filter slot contains a search input (no longer empty)

#### Scenario: Search narrows the visible rows
- **WHEN** the operator types a term that matches some rows
- **THEN** only rows matching the term (by the module's identifying fields) remain visible, and clearing the term restores all rows

#### Scenario: No-match shows the empty state
- **WHEN** the operator types a term that matches no rows
- **THEN** the module shows its empty state instead of a blank table

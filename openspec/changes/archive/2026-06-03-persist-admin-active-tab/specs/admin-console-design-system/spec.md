## ADDED Requirements

### Requirement: Active tab persists across reload

The admin console SHALL reflect the active tab in the URL (`location.hash`) whenever the tab changes, and SHALL restore that tab on load. When the URL carries no tab or an unknown tab, the console SHALL fall back to the default `users` tab.

#### Scenario: Reload stays on the current tab

- **WHEN** the user is on the Agents tab and reloads the page
- **THEN** the console reads the tab from `location.hash` and restores the Agents tab instead of jumping to Users

#### Scenario: Missing or unknown tab falls back to default

- **WHEN** the page loads with no hash or a hash that is not a known tab
- **THEN** the console shows the default `users` tab

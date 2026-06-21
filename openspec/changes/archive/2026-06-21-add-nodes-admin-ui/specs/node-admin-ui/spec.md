## ADDED Requirements

### Requirement: Nodes managed natively in the React SPA

The React admin SPA SHALL provide a native Nodes domain backed by the existing `/admin/nodes` API: list nodes (identity, labels, last-seen / registration info), register a node, delete a node, and pin / unpin an agent to a node. Deleting a node affects agent placement and SHALL require a second confirmation.

#### Scenario: List and register nodes

- **WHEN** an admin opens the Nodes view and registers a node
- **THEN** nodes are listed via `GET /admin/nodes` and registration calls `POST /admin/nodes`, refreshing the list

#### Scenario: Pin and unpin an agent

- **WHEN** an admin pins an agent to a node, or unpins it
- **THEN** the SPA calls `POST /admin/nodes/{id}/pin` (resp. `DELETE /admin/nodes/{id}/pin`) and the placement reflects the change

#### Scenario: Delete a node requires confirmation

- **WHEN** an admin deletes a node
- **THEN** a second confirmation is required, then the SPA calls `DELETE /admin/nodes/{id}` and the node leaves the list

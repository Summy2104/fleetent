## ADDED Requirements

### Requirement: Agent creation requires an existing template

`POST /admin/agents` SHALL require a `template_id` naming an existing agent template.
A request missing `template_id` SHALL be rejected with 422; a request naming a template
that does not exist SHALL be rejected with 404. On success the created agent's version
snapshot SHALL persist the `template_id`, and `GET /admin/agents/{name}` SHALL include
`template_id` in its response. Editing an agent (`PATCH /admin/agents/{name}`) SHALL NOT
require `template_id`.

#### Scenario: Create without template_id rejected

- **WHEN** an admin sends `POST /admin/agents` with a body omitting `template_id`
- **THEN** the response is 422 and no agent is created

#### Scenario: Create with unknown template_id rejected

- **WHEN** an admin sends `POST /admin/agents` with `template_id` that matches no existing template
- **THEN** the response is 404 and no agent is created

#### Scenario: Create with valid template persists the link

- **WHEN** an admin sends `POST /admin/agents` with a `template_id` of an existing template
- **THEN** the response is 201
- **AND** `GET /admin/agents/{name}` returns `template_id` equal to that template

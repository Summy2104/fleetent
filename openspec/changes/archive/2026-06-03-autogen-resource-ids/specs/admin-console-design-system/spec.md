## ADDED Requirements

### Requirement: System-generated resource ids

Admin create forms that require a unique resource `id` SHALL generate that id automatically and present it read-only; the user SHALL NOT type or edit the id. This applies to the create forms for agent templates, knowledge bases, model providers, and OAuth connectors. Edit forms SHALL continue to show the existing id read-only. The generated id SHALL be sent through the existing create endpoints unchanged.

#### Scenario: Create form auto-fills a read-only id

- **WHEN** the operator opens a create form for a template, knowledge base, provider, or connector
- **THEN** the id field is pre-filled with a generated value and is read-only, so the operator cannot type or change it

#### Scenario: Generated id is submitted on create

- **WHEN** the operator saves a newly created resource
- **THEN** the console submits the generated id through the existing create endpoint

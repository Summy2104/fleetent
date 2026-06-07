## ADDED Requirements

### Requirement: Aggregate all content blocks

The MCP client SHALL include every content block of a tool result, not only the first, when constructing the text returned to the agent. Text blocks SHALL be concatenated in order and separated by newlines. This SHALL apply to both the stdio (typed SDK objects) and http (JSON dict) result shapes.

#### Scenario: Multiple text blocks aggregated
- **WHEN** an MCP tool returns a result whose content is two text blocks `"alpha"` then `"beta"`
- **THEN** the returned text contains both `"alpha"` and `"beta"` in that order

#### Scenario: Single text block unchanged
- **WHEN** an MCP tool returns a result with a single text block `"ok"`
- **THEN** the returned text is `"ok"`

### Requirement: Represent non-text content without failure

The MCP client SHALL represent non-text content blocks (image, audio, binary/blob resource) as a concise textual marker and SHALL NOT raise, for either the stdio or http result shape. An embedded resource block that carries text SHALL have that text inlined. Binary payloads SHALL NOT be emitted as raw base64 into the returned text.

#### Scenario: Image-first result on stdio path does not crash
- **WHEN** a stdio MCP tool returns a result whose first content block is an image block (no `text` attribute)
- **THEN** the returned text contains a marker describing the image (including its mime type)
- **AND** no exception is raised

#### Scenario: Embedded text resource inlined
- **WHEN** an MCP tool returns an embedded resource content block carrying text `"file body"`
- **THEN** the returned text inlines `"file body"`

#### Scenario: Binary content is not dumped as base64
- **WHEN** an MCP tool returns an image content block with a base64 data payload
- **THEN** the returned text contains a short marker and does not contain the raw base64 payload

### Requirement: Surface tool-reported errors

When a tool result indicates an error (its `isError` flag is true), the MCP client SHALL return a string that is clearly marked as an error and that includes the result's error content text, and SHALL NOT raise an exception. This lets the agent read the error and recover rather than receiving the error as an apparently-successful result.

#### Scenario: isError result surfaced, not raised
- **WHEN** an MCP tool returns a result with `isError` true and content text `"bad arg: limit"`
- **THEN** the returned string is marked as an error and contains `"bad arg: limit"`
- **AND** no exception is raised

#### Scenario: Successful result not marked as error
- **WHEN** an MCP tool returns a result with `isError` false (or absent) and content text `"done"`
- **THEN** the returned string is `"done"` and is not marked as an error

### Requirement: Include structured content when no content blocks

When a tool result has no content blocks but provides `structuredContent`, the MCP client SHALL serialize the structured content as JSON text so it is not silently dropped. When content blocks are present, the content blocks SHALL take precedence for the returned text.

#### Scenario: Structured-only result serialized
- **WHEN** an MCP tool returns a result with empty content and `structuredContent` `{"count": 3}`
- **THEN** the returned text is a JSON serialization containing `"count"` and `3`

#### Scenario: Content blocks take precedence over structured content
- **WHEN** an MCP tool returns both a text content block `"hello"` and a `structuredContent` object
- **THEN** the returned text includes the content block text `"hello"`

# permission-gate Delta

## MODIFIED Requirements

### Requirement: Risk-level declaration

Tools SHALL declare their risk level at registration time via `@tool(risk_level=...)`, as either a string constant (`"none"`/`"low"`/`"medium"`/`"high"`, existing semantics unchanged) or a callable `(tool_args, tool_context) -> "low" | "medium" | "high"` evaluated at dispatch time. A callable MUST be a pure function of its inputs (no I/O side effects beyond reads), MUST be evaluated once per call before the action-mode decision, and its returned level MUST drive the same gate behavior as the equivalent string constant. If the callable raises, the gate MUST fail closed by treating the call as `"medium"`.

#### Scenario: Tool with no risk

- **WHEN** a tool is registered with `risk_level="none"` (or no risk_level specified)
- **THEN** it executes immediately after access control passes

#### Scenario: Tool with medium risk

- **WHEN** a tool is registered with `risk_level="medium"`
- **THEN** a confirmation request is sent to the requester via IM DM before execution

#### Scenario: Tool with high risk

- **WHEN** a tool is registered with `risk_level="high"`
- **THEN** an approval request is sent to the pre-configured approver, and the requester is notified "waiting for admin approval"

#### Scenario: Callable risk evaluates low

- **WHEN** a tool registered with a callable risk_level is dispatched and the callable returns `"low"` for the given args and context
- **THEN** the tool executes without an approval prompt

#### Scenario: Callable risk evaluates medium

- **WHEN** the same tool is dispatched with args for which the callable returns `"medium"`
- **THEN** the call passes the medium approval flow identical to a static `risk_level="medium"` tool

#### Scenario: Callable failure fails closed

- **WHEN** the risk callable raises an exception during evaluation
- **THEN** the call is treated as `"medium"` (approval required), never as free

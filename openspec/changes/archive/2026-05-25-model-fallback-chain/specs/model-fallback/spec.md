## ADDED Requirements

### Requirement: Fallback chain configuration
`RouteConfig` SHALL accept an optional ordered list of fallback model names (`fallbacks: tuple[str, ...]`). When omitted, the fallback chain is empty and behavior is identical to the current implementation.

#### Scenario: Default empty fallback
- **WHEN** a `RouteConfig` is created without specifying `fallbacks`
- **THEN** `fallbacks` is an empty tuple and no fallback occurs on error

#### Scenario: Explicit fallback chain
- **WHEN** a `RouteConfig` is created with `fallbacks=("claude-haiku-4-5", "gpt-4o-mini")`
- **THEN** the fallback sequence is `[primary_model, "claude-haiku-4-5", "gpt-4o-mini"]`

### Requirement: Automatic retry on rate limit (429)
When a LLM call returns HTTP 429, `agent_loop` SHALL automatically retry with the next model in the fallback chain without propagating the error to the caller.

#### Scenario: 429 triggers first fallback
- **WHEN** the primary model returns a rate limit error
- **AND** at least one fallback model is configured
- **THEN** the agent loop retries the same request using the first fallback model

#### Scenario: 429 with no fallbacks configured
- **WHEN** the primary model returns a rate limit error
- **AND** no fallback models are configured
- **THEN** the rate limit error is propagated to the caller

### Requirement: Automatic retry on service unavailable (503)
When a LLM call returns HTTP 503, `agent_loop` SHALL automatically retry with the next model in the fallback chain.

#### Scenario: 503 triggers fallback
- **WHEN** the primary model returns a 503 APIStatusError
- **AND** at least one fallback model is configured
- **THEN** the agent loop retries using the next fallback model

### Requirement: Fallback exhaustion propagates last error
When all models in the fallback chain (primary + all fallbacks) have been tried and all failed, `agent_loop` SHALL raise the last exception received.

#### Scenario: All fallbacks exhausted
- **WHEN** primary model and all fallback models all return 429 or 503
- **THEN** the exception from the last attempted model is raised

### Requirement: Non-retriable errors bypass fallback
Errors other than 429 and 503 (e.g., 400 bad request, 401 unauthorized, connection errors) SHALL NOT trigger fallback and MUST be propagated immediately.

#### Scenario: 401 does not trigger fallback
- **WHEN** the primary model returns a 401 unauthorized error
- **THEN** the error is immediately propagated without trying any fallback

### Requirement: Actual model usage is recorded in eval trace
`eval_logger` SHALL record the model name that successfully handled the request. When a fallback was used, the trace MUST reflect the fallback model, not the primary.

#### Scenario: Fallback model recorded in trace
- **WHEN** the primary model fails with 429 and the first fallback model succeeds
- **THEN** the eval trace contains the fallback model name as `model_used`

#### Scenario: Primary model recorded when no fallback needed
- **WHEN** the primary model succeeds without any fallback
- **THEN** the eval trace contains the primary model name as `model_used`

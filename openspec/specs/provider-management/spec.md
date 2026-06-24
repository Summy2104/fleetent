# provider-management Specification

## Purpose
Unified model provider management system that enables dynamic configuration, routing, fallback chains, health monitoring, and cost tracking for multiple LLM providers without service restarts. Provides both API and UI interfaces for administrators to manage provider configurations, set up intelligent routing rules, monitor provider health, and track usage costs across the platform.

## Requirements

### Requirement: Provider Registry Pattern
The system SHALL maintain a centralized provider registry with support for multiple provider types (OpenAI, Anthropic, Azure, Custom), each with standardized configuration schemas and provider-specific extensions.

#### Scenario: Register OpenAI-compatible provider
- **GIVEN** an admin wants to add an OpenAI provider
- **WHEN** they provide base_url="https://api.openai.com/v1", model="gpt-4o", api_key, and OpenAI-specific params
- **THEN** the provider is registered with type="openai" and available for routing

#### Scenario: Register custom provider with extensions
- **GIVEN** an admin wants to add a custom provider with specific parameters
- **WHEN** they provide base_url, model, api_key, and custom `extra_params` JSON
- **THEN** the provider is registered with all parameters preserved and passed through on calls

### Requirement: Dynamic Provider Configuration
Providers SHALL be configurable at runtime without service restarts, with changes taking effect immediately for new requests while preserving in-flight request handling.

#### Scenario: Add provider without restart
- **GIVEN** the service is running with 2 configured providers
- **WHEN** an admin adds a third provider via API
- **THEN** new requests can immediately use the third provider without service restart

#### Scenario: Edit provider preserves connections
- **GIVEN** a provider is actively handling requests
- **WHEN** an admin edits its temperature setting
- **THEN** in-flight requests complete with old settings, new requests use updated settings

### Requirement: Intelligent Task-Type Routing
The system SHALL support task-type based routing where different types of requests (chat, summarization, extraction, embedding) can be routed to optimal providers with configurable fallback chains.

#### Scenario: Route by task type
- **GIVEN** providers A (fast/cheap) and B (powerful/expensive) are configured
- **WHEN** routing rules send "chat" to A and "analysis" to B
- **THEN** chat requests use provider A, analysis requests use provider B

#### Scenario: Fallback chain execution
- **GIVEN** task_type="chat" has fallback chain [provider_A, provider_B, provider_C]
- **WHEN** provider_A returns 429 rate limit
- **THEN** the request automatically retries with provider_B without error to caller

### Requirement: Provider Health Monitoring
The system SHALL continuously monitor provider health through passive observation and active health checks, maintaining availability scores and automatic circuit breaking.

#### Scenario: Passive health tracking
- **GIVEN** a provider is handling requests
- **WHEN** it has 3 consecutive 503 errors
- **THEN** its health score degrades and it's temporarily deprioritized in routing

#### Scenario: Active health check
- **GIVEN** health checks are configured to run every 60 seconds
- **WHEN** the check executes
- **THEN** a lightweight test request validates connectivity and updates health status

#### Scenario: Circuit breaker activation
- **GIVEN** a provider has health score below threshold (e.g., 30%)
- **WHEN** new requests arrive
- **THEN** the provider is skipped in routing until health recovers

### Requirement: Cost and Usage Tracking
The system SHALL track token usage and costs per provider, model, task_type, and agent, with configurable pricing tables and budget alerts.

#### Scenario: Calculate usage costs
- **GIVEN** provider has input_price=$0.01/1k and output_price=$0.03/1k tokens
- **WHEN** a request uses 500 input + 1500 output tokens
- **THEN** cost is calculated as $0.005 + $0.045 = $0.05 and recorded

#### Scenario: Budget alert trigger
- **GIVEN** a monthly budget of $1000 is configured
- **WHEN** cumulative usage reaches $900 (90% threshold)
- **THEN** an alert is triggered to configured notification channels

### Requirement: Provider Credential Security
Provider API keys SHALL be encrypted at rest, masked in all UI/API responses, and never logged in plaintext. Key rotation SHALL be supported without service interruption.

#### Scenario: Encrypted storage
- **GIVEN** an API key "sk-abc123..." is configured
- **WHEN** it's stored in the database
- **THEN** it's encrypted using platform KMS and only decrypted for actual API calls

#### Scenario: Masked display
- **GIVEN** a provider with API key is configured
- **WHEN** fetched via API or displayed in UI
- **THEN** the key appears as "sk-abc***" or fully masked "***"

#### Scenario: Zero-downtime key rotation
- **GIVEN** a provider with active key is handling requests
- **WHEN** admin initiates key rotation with new_key
- **THEN** new requests use new_key while in-flight requests complete with old key

### Requirement: Provider-Specific Features
The system SHALL support provider-specific features like streaming, function calling, vision, embeddings through capability detection and routing.

#### Scenario: Route vision requests to capable provider
- **GIVEN** providers A (text-only) and B (multimodal) are configured
- **WHEN** a request includes image input
- **THEN** it's automatically routed to provider B regardless of task_type

#### Scenario: Streaming capability detection
- **GIVEN** a provider configuration includes `supports_streaming: true`
- **WHEN** a streaming request arrives
- **THEN** the provider is eligible for selection, non-streaming providers are filtered out

### Requirement: Load Balancing Strategies
The system SHALL support multiple load balancing strategies including round-robin, weighted, least-latency, and cost-optimized routing.

#### Scenario: Weighted load balancing
- **GIVEN** providers A and B with weights 70:30
- **WHEN** 100 requests arrive
- **THEN** approximately 70 go to A and 30 go to B

#### Scenario: Least-latency routing
- **GIVEN** strategy="least_latency" and providers with p50 latencies A=200ms, B=150ms
- **WHEN** a new request arrives
- **THEN** provider B is selected based on better historical latency

### Requirement: Provider Comparison and Testing
The system SHALL provide tools to compare providers on the same prompts for quality, latency, and cost evaluation.

#### Scenario: A/B test providers
- **GIVEN** an admin wants to compare two providers
- **WHEN** they submit a test prompt to both
- **THEN** results show side-by-side output, latency, tokens used, and cost

#### Scenario: Batch evaluation
- **GIVEN** a saved test suite of 10 prompts
- **WHEN** admin runs evaluation against 3 providers
- **THEN** a comparison matrix shows quality scores, average latency, and total cost

### Requirement: Import/Export Configuration
Provider configurations SHALL be exportable and importable as YAML/JSON for version control, backup, and environment promotion.

#### Scenario: Export configuration
- **GIVEN** 5 providers configured with routing rules
- **WHEN** admin exports configuration
- **THEN** a YAML file is generated with all settings except decrypted API keys

#### Scenario: Import configuration with environment variables
- **GIVEN** a YAML config with `api_key: ${OPENAI_API_KEY}`
- **WHEN** imported to a new environment
- **THEN** the key is resolved from environment variable during import

### Requirement: Audit Logging
All provider management operations SHALL be audit logged with user, timestamp, operation, before/after states, and outcome.

#### Scenario: Track configuration changes
- **GIVEN** an admin modifies provider max_tokens from 2048 to 4096
- **WHEN** the change is saved
- **THEN** audit log records: who, when, what changed, old value, new value

#### Scenario: Track deletion with dependencies
- **GIVEN** a provider is used in 3 routing rules
- **WHEN** admin deletes the provider
- **THEN** audit log records the deletion and automatic removal from routing rules

### Requirement: CLI Management Interface
A CLI interface SHALL provide all provider management capabilities for automation and scripting.

#### Scenario: List providers via CLI
- **GIVEN** 3 providers are configured
- **WHEN** running `fleetent platform provider list`
- **THEN** a table shows id, name, type, model, status for each provider

#### Scenario: Add provider via CLI
- **GIVEN** admin wants to add a provider programmatically
- **WHEN** running `fleetent platform provider add --id gpt4 --base-url https://... --model gpt-4`
- **THEN** the provider is added and confirmation with masked key is shown

### Requirement: Provider Groups and Pools
Providers SHALL be groupable into logical pools for simplified routing and management.

#### Scenario: Create provider pool
- **GIVEN** 3 OpenAI-compatible providers from different vendors
- **WHEN** admin creates pool "openai_compatible" with all three
- **THEN** routing rules can reference the pool instead of individual providers

#### Scenario: Pool-level fallback
- **GIVEN** a pool with 3 providers and pool-level fallback to another pool
- **WHEN** all providers in first pool are unavailable
- **THEN** requests fall back to the second pool automatically

### Requirement: Rate Limit Management
The system SHALL track and respect provider rate limits with configurable throttling and queuing strategies.

#### Scenario: Respect rate limits
- **GIVEN** provider configured with max_rpm=60 (requests per minute)
- **WHEN** request rate exceeds 60/min
- **THEN** excess requests are queued or routed to fallback providers

#### Scenario: Adaptive rate limiting
- **GIVEN** a provider returns 429 with Retry-After header
- **WHEN** the system receives this response
- **THEN** it automatically adjusts rate limiting for that provider

### Requirement: Provider Metadata and Tags
Providers SHALL support arbitrary metadata and tagging for organization, filtering, and custom routing logic.

#### Scenario: Tag-based routing
- **GIVEN** providers tagged with region=us-east, region=eu-west
- **WHEN** a request includes preferred_region=eu-west
- **THEN** EU providers are prioritized in routing selection

#### Scenario: Metadata filtering
- **GIVEN** providers with metadata like compliance=HIPAA, data_residency=US
- **WHEN** filtering providers for HIPAA-compliant US-based options
- **THEN** only matching providers are shown/selected

### Requirement: Multi-tenant Provider Isolation
In multi-tenant deployments, providers SHALL be isolatable per tenant with optional shared provider pools.

#### Scenario: Tenant-specific providers
- **GIVEN** tenant A with their own API keys for providers
- **WHEN** tenant A makes requests
- **THEN** only tenant A's providers are used, not visible to tenant B

#### Scenario: Shared provider pool with quotas
- **GIVEN** a shared provider pool with per-tenant quotas
- **WHEN** tenant A exhausts their quota
- **THEN** their requests fail/queue while tenant B continues normally

## API Specification

### Provider Management Endpoints

```yaml
endpoints:
  /admin/api/providers:
    GET:
      description: List all configured providers
      response:
        - id: string
        - name: string
        - type: enum[openai, anthropic, azure, custom]
        - base_url: string
        - model: string
        - api_key: string (masked)
        - status: enum[active, inactive, error]
        - health_score: number (0-100)
        - capabilities: string[]
        - metadata: object
    
    POST:
      description: Add a new provider
      body:
        - id: string (required)
        - name: string
        - type: enum (required)
        - base_url: string (required)
        - model: string (required)
        - api_key: string (required)
        - max_tokens: integer
        - temperature: number
        - extra_params: object
        - capabilities: string[]
        - metadata: object
  
  /admin/api/providers/{id}:
    GET:
      description: Get provider details
    
    PUT:
      description: Update provider
      body: (same as POST, api_key optional)
    
    DELETE:
      description: Remove provider
  
  /admin/api/providers/{id}/health:
    GET:
      description: Get provider health status
      response:
        - status: enum[healthy, degraded, unhealthy]
        - score: number (0-100)
        - last_check: timestamp
        - recent_errors: object[]
    
    POST:
      description: Trigger health check
  
  /admin/api/providers/{id}/test:
    POST:
      description: Test provider with sample request
      body:
        - prompt: string
        - options: object
      response:
        - success: boolean
        - latency_ms: number
        - tokens_used: object
        - response: string
        - error: string
  
  /admin/api/routing:
    GET:
      description: Get routing configuration
      response:
        - task_types: object<string, RoutingRule>
    
    PUT:
      description: Update routing configuration
      body:
        - task_type: string
        - providers: string[]
        - strategy: enum[priority, round_robin, weighted, least_latency]
        - weights: object<string, number>
  
  /admin/api/providers/usage:
    GET:
      description: Get usage statistics
      query:
        - start_date: date
        - end_date: date
        - group_by: enum[provider, model, task_type, agent]
      response:
        - period: object
        - usage: UsageStats[]
  
  /admin/api/providers/export:
    GET:
      description: Export configuration as YAML
      response: YAML configuration
  
  /admin/api/providers/import:
    POST:
      description: Import configuration from YAML
      body: YAML configuration
```

## Data Model

```sql
-- Provider configuration
CREATE TABLE model_providers (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL, -- openai, anthropic, azure, custom
    base_url TEXT NOT NULL,
    model TEXT NOT NULL,
    api_key_encrypted TEXT, -- Encrypted with KMS
    max_tokens INTEGER,
    temperature REAL,
    extra_params JSON,
    capabilities JSON, -- ["streaming", "functions", "vision"]
    metadata JSON,
    status TEXT DEFAULT 'active', -- active, inactive, error
    health_score INTEGER DEFAULT 100,
    last_health_check TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by TEXT,
    updated_by TEXT
);

-- Provider health history
CREATE TABLE provider_health_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider_id TEXT NOT NULL,
    event_type TEXT NOT NULL, -- success, error, timeout, rate_limit
    status_code INTEGER,
    latency_ms INTEGER,
    error_message TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (provider_id) REFERENCES model_providers(id) ON DELETE CASCADE
);

-- Provider usage tracking
CREATE TABLE provider_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider_id TEXT NOT NULL,
    task_type TEXT,
    agent_name TEXT,
    user_id TEXT,
    input_tokens INTEGER,
    output_tokens INTEGER,
    total_tokens INTEGER,
    cost_amount REAL,
    cost_currency TEXT DEFAULT 'USD',
    latency_ms INTEGER,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (provider_id) REFERENCES model_providers(id)
);

-- Provider groups/pools
CREATE TABLE provider_pools (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    strategy TEXT DEFAULT 'priority', -- priority, round_robin, weighted, least_latency
    metadata JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE provider_pool_members (
    pool_id TEXT NOT NULL,
    provider_id TEXT NOT NULL,
    priority INTEGER DEFAULT 0,
    weight INTEGER DEFAULT 100,
    PRIMARY KEY (pool_id, provider_id),
    FOREIGN KEY (pool_id) REFERENCES provider_pools(id) ON DELETE CASCADE,
    FOREIGN KEY (provider_id) REFERENCES model_providers(id) ON DELETE CASCADE
);

-- Pricing configuration
CREATE TABLE provider_pricing (
    provider_id TEXT NOT NULL,
    model TEXT NOT NULL,
    input_price_per_1k REAL,
    output_price_per_1k REAL,
    currency TEXT DEFAULT 'USD',
    effective_date DATE,
    PRIMARY KEY (provider_id, model, effective_date),
    FOREIGN KEY (provider_id) REFERENCES model_providers(id) ON DELETE CASCADE
);

-- Provider test suites
CREATE TABLE provider_test_suites (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    prompts JSON, -- Array of test prompts
    expected_capabilities JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by TEXT
);

CREATE TABLE provider_test_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    suite_id TEXT NOT NULL,
    provider_id TEXT NOT NULL,
    results JSON, -- Detailed test results
    summary JSON, -- Aggregated scores
    run_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    run_by TEXT,
    FOREIGN KEY (suite_id) REFERENCES provider_test_suites(id),
    FOREIGN KEY (provider_id) REFERENCES model_providers(id)
);
```

## Implementation Notes

### Provider Registry Pattern
```python
class ProviderRegistry:
    """Central registry for all provider types."""
    
    def __init__(self):
        self._providers: dict[str, Provider] = {}
        self._pools: dict[str, ProviderPool] = {}
        self._health_monitor = HealthMonitor()
        self._rate_limiter = RateLimiter()
    
    def register(self, provider: Provider) -> None:
        """Register a new provider with health monitoring."""
        self._providers[provider.id] = provider
        self._health_monitor.track(provider)
        self._rate_limiter.configure(provider)
    
    def get_provider(self, task_type: str) -> Provider:
        """Get best provider for task type with fallback."""
        candidates = self._get_candidates(task_type)
        candidates = self._filter_healthy(candidates)
        candidates = self._filter_rate_limited(candidates)
        return self._select_by_strategy(candidates, task_type)
```

### Health Monitoring
```python
class HealthMonitor:
    """Continuous provider health monitoring."""
    
    async def passive_monitor(self, provider_id: str, result: CallResult) -> None:
        """Update health based on actual call results."""
        if result.error:
            await self._degrade_health(provider_id, result.error)
        else:
            await self._improve_health(provider_id, result.latency)
    
    async def active_check(self, provider: Provider) -> HealthStatus:
        """Proactive health check with minimal request."""
        try:
            response = await provider.complete(
                messages=[{"role": "user", "content": "Hi"}],
                max_tokens=1
            )
            return HealthStatus.HEALTHY
        except Exception as e:
            return HealthStatus.UNHEALTHY
```

### Cost Tracking
```python
class CostTracker:
    """Track and calculate usage costs."""
    
    def calculate_cost(
        self, 
        provider_id: str, 
        input_tokens: int, 
        output_tokens: int
    ) -> float:
        """Calculate cost based on current pricing."""
        pricing = self._get_pricing(provider_id)
        input_cost = (input_tokens / 1000) * pricing.input_price_per_1k
        output_cost = (output_tokens / 1000) * pricing.output_price_per_1k
        return input_cost + output_cost
    
    async def check_budget(self, user_id: str, estimated_cost: float) -> bool:
        """Check if request would exceed budget."""
        current_usage = await self._get_current_usage(user_id)
        budget = await self._get_budget(user_id)
        return (current_usage + estimated_cost) <= budget
```

### Security Considerations
- API keys encrypted at rest using platform KMS
- Keys masked in all API responses and logs
- Audit logging for all configuration changes
- Role-based access control for management operations
- Secure key rotation without service interruption

### Migration Path
1. Export existing `ROUTES` from model_router.py
2. Transform to new provider configuration format
3. Import via admin API
4. Verify routing behavior matches
5. Switch model_router to use registry
6. Remove hardcoded ROUTES

This design provides a comprehensive, secure, and scalable provider management system that supports dynamic configuration, intelligent routing, health monitoring, and cost optimization while maintaining simplicity and ease of use.

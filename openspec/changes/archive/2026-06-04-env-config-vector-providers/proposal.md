## Why

Real embedding and rerank smoke validation needs operator-supplied endpoint, model, dimensions, and API key values without committing provider details or secrets to `settings.yaml`.
The current config supports `api_key_env` but requires endpoint/model/dimensions literals, which makes pilot validation configuration awkward and inconsistent with the recently env-flattened KB connector configuration.

## What Changes

- Add env reference fields for embedding provider endpoint, model, and dimensions.
- Add env reference fields for rerank provider endpoint and model.
- Resolve those env references when creating HTTP embedding/rerank providers, while preserving direct literal fields for compatibility.
- Update safe templates and docs/tests so operators see the intended env variable names.

## Impact

- Owning package: `intelligence` / `configuration`.
- Public API surface: `EmbeddingSettings`, `RerankSettings`, `create_embedding_provider`, `create_rerank_provider`.
- Owned tables: none.
- Config namespace: `embedding`, `rerank`.
- Cross-module dependencies: vector provider runtime reads `Settings` values and environment variables only.
- Migration / shim plan: direct `endpoint`, `model`, `dimensions`, and `api_key_env` fields remain compatible.

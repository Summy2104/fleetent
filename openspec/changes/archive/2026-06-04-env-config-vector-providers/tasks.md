## 1. Embedding env references

- [x] 1.1 Write failing tests: `EmbeddingSettings` accepts `endpoint_env`, `model_env`, and `dimensions_env`.
- [x] 1.2 Write failing tests: HTTP embedding provider creation resolves env references and preserves direct field compatibility.
- [x] 1.3 Implement embedding env reference resolution.
- [x] 1.4 Verify green: run `uv run pytest tests/unit/test_config.py tests/unit/test_vector_provider_boundaries.py -x -q`.

## 2. Rerank env references

- [x] 2.1 Write failing tests: `RerankSettings` accepts `endpoint_env` and `model_env`.
- [x] 2.2 Write failing tests: HTTP rerank provider creation resolves env references and preserves direct field compatibility.
- [x] 2.3 Implement rerank env reference resolution.
- [x] 2.4 Verify green: run `uv run pytest tests/unit/test_config.py tests/unit/test_vector_provider_boundaries.py -x -q`.

## 3. Templates and validation

- [x] 3.1 Write failing tests: `.env.example` and `config/settings.yaml.example` expose real smoke env placeholders without secret values.
- [x] 3.2 Implement template updates and local untracked `config/settings.yaml` pilot settings.
- [x] 3.3 Verify green: run `uv run pytest tests/integration/test_deployment_docs.py tests/unit/test_config.py tests/unit/test_vector_provider_boundaries.py -x -q`.
- [x] 3.4 Run strict OpenSpec validation.

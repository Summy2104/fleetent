## 1. provider.py：ABC + 共用工具

- [x] 1.1 Write failing tests for ImageGenProvider ABC and ImageGenError in tests/unit/test_image_gen.py: 验证 ABC 不可直接实例化、ImageGenError 是 Exception 子类、_fetch_url 在 URL 返回非 200 时抛 ImageGenError
- [x] 1.2 Create src/fleetent/tools/image_gen/provider.py with ImageGenProvider ABC, ImageGenError, and _fetch_url async helper

## 2. registry.py：provider 注册与分发

- [x] 2.1 Write failing tests for registry: test_register_and_dispatch_by_protocol（注册后可分发）、test_dispatch_unknown_protocol_raises_ImageGenError（未知协议报错含协议名）
- [x] 2.2 Create src/fleetent/tools/image_gen/registry.py with _PROVIDERS dict, register(), and dispatch()

## 3. openai.py：迁移现有 openai_image_generation 逻辑

- [x] 3.1 Write failing tests for OpenAIImagesProvider: 迁移 test_generate_decodes_b64_json、test_generate_uses_image_generation_route、test_generate_endpoint_error_raises_imagegenerror、test_generate_empty_data_raises、test_generate_fetches_url_when_no_b64（调整 mock 路径指向新 provider）
- [x] 3.2 Create src/fleetent/tools/image_gen/openai.py with OpenAIImagesProvider and register() call

## 4. chat.py：新 openai_image_chat 协议

- [x] 4.1 Write failing tests for ChatImageProvider: test_chat_provider_extracts_data_uri_jpeg、test_chat_provider_extracts_data_uri_png、test_chat_provider_fetches_bare_url_fallback、test_chat_provider_empty_response_raises、test_chat_provider_no_image_in_text_raises
- [x] 4.2 Create src/fleetent/tools/image_gen/chat.py with ChatImageProvider and register() call

## 5. __init__.py：分发入口

- [x] 5.1 Write failing test for image_gen.generate() dispatch: mock provider registry，验证 generate() 路由到正确 provider 并返回 bytes
- [x] 5.2 Create src/fleetent/tools/image_gen/__init__.py exporting generate() and ImageGenError, importing openai/chat providers

## 6. image_gen_client.py：shim

- [x] 6.1 Write failing tests for shim: test_shim_generate_is_same_object、test_shim_ImageGenError_is_same_class（用 is 检查）
- [x] 6.2 Replace src/fleetent/tools/image_gen_client.py with 1-line re-export shim

## 7. agent_config.py：openai_image_chat 协议校验

- [x] 7.1 Write failing tests for openai_image_chat validation: test_openai_image_chat_valid_passes、test_openai_image_chat_missing_base_url_raises、test_openai_image_chat_missing_model_raises
- [x] 7.2 Add openai_image_chat protocol validation to ModelTarget._validate_protocol_requirements in agent_config.py

## 8. 集成收尾与全量测试

- [x] 8.1 Run uv run pytest tests/unit/test_image_gen.py -x -q and fix any remaining failures
- [x] 8.2 Run uv run pytest -x -q to verify no regressions
- [x] 8.3 Run uv run python scripts/check_test_layers.py to verify test layer boundaries
- [x] 8.4 Run uv run ruff format src tests && uv run ruff check src tests
- [x] 8.5 Run uv run mypy src

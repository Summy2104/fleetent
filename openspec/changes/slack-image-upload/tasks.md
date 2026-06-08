## 1. normalizer.py：路径提取辅助函数

- [ ] 1.1 Write failing tests for _extract_generated_image_paths: test_finds_path_in_tool_message（含 "image generated: <path>"，文件存在 → 返回路径）、test_skips_missing_file（路径不存在 → 空列表）、test_ignores_non_tool_messages（assistant/user 消息中的路径不提取）、test_only_scans_provided_messages（只扫传入的 messages，不访问全局 history）
- [ ] 1.2 Implement _extract_generated_image_paths(messages: list[dict]) -> list[str] in normalizer.py

## 2. normalizer.py：route() 调用 upload_func

- [ ] 2.1 Write failing tests for route() upload_func integration: test_route_calls_upload_func_with_generated_image（mock loop 在 history 追加 tool 结果，upload_func 被调用并传入路径）、test_route_skips_upload_when_upload_func_none（upload_func=None 时 route 正常完成，不报错）、test_route_only_uploads_current_turn_images（历史 turn 中有旧图片路径，本轮未生成 → upload_func 传入空列表，不被调用）
- [ ] 2.2 Add upload_func field to NormalizedMessage and call it in route() after reply_func

## 3. slack.py：upload_func 实现

- [ ] 3.1 Write failing test for Slack upload_func: test_slack_upload_func_calls_files_upload_v2（mock client.files_upload_v2，upload_func([path]) → 被调用，参数正确）、test_slack_upload_func_skips_on_exception（files_upload_v2 抛异常 → log warning，不 re-raise）
- [ ] 3.2 Implement upload_func in slack.py _handle() using client.files_upload_v2, pass to NormalizedMessage

## 4. 收尾

- [ ] 4.1 Run uv run pytest tests/unit/test_normalizer.py tests/unit/test_slack_image_upload.py -x -q（或相关测试文件）
- [ ] 4.2 Run uv run pytest -x -q to verify no regressions
- [ ] 4.3 Run uv run python scripts/check_test_layers.py
- [ ] 4.4 Run uv run ruff format src tests && uv run ruff check src tests
- [ ] 4.5 Run uv run mypy src

## 1. 删除全局 .example 模板

- [x] 1.1 Write failing test：`tests/integration/test_deployment_docs.py`(或新增) —— 断言 `config/settings.yaml.example`/`mcp.yaml.example`/`mcp.servers.yaml.example` **不存在**，且 `config/agent.yaml.example` 存在
- [x] 1.2 Implement：`git rm` 三个全局 `.example`；同步修正/删除 `test_deployment_docs.py` 中读取 `config/settings.yaml.example` 内容的断言，使测试转绿

## 2. init_config 不再 seed 全局文件

- [x] 2.1 Write failing tests：`tests/unit/test_admin_init_config.py` —— `plan_init_config`/`apply_init_config` 的产物**不含** `config/settings.yaml`、`config/mcp.servers.yaml`（仍含 `.env` 与 data 目录）
- [x] 2.2 Implement：`admin_cli/init_config.py` 从 `_GENERATED_FILES` 移除两项全局文件 + 更新 print 文案，使测试转绿

## 3. Dockerfile COPY 显式化

- [x] 3.1 Implement：`Dockerfile` `COPY config/*.yaml.example ./config/` → `COPY config/agent.yaml.example ./config/`；`hadolint`（若可用）/`docker build` dry-check 不强制，至少 `grep` 校验改动正确

## 4. 缺失即默认 契约回归

- [x] 4.1 Write failing/确认 tests：`Settings` 在 `SETTINGS_YAML_PATH` 指向不存在文件时用默认值（已有 `test_settings_missing_yaml_file_uses_typed_defaults` → 复核仍通过）；新增/确认 mcp 全局缺失不报错
- [x] 4.2 Implement：无需改加载器（已容忍）；如契约测试缺口则补测试

## 5. 收尾

- [x] 5.1 全量 `ANTHROPIC_API_KEY=sk-test-dummy uv run pytest -x -q` 通过；`uv run ruff format && uv run ruff check`；`uv run mypy src` 不新增；`bash -n` 无关
- [x] 5.2 更新设计文档决策日志（本 change 完成 + 明确「删加载器+收缩 Settings」deferred 的范围与触发条件：随 sandbox/intelligence→agent.yaml 迁移）；写 3-change 最终审核汇总段

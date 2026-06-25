# Tasks

## 1. 确认 ground truth（无代码改动）

- [x] 1.1 确认 `scripts/install.sh` / `scripts/install-platform.sh` 不 seed 默认 Agent home（打印 `fleetent agent init` 教程），且只 seed Platform home（`.env` + `platform.yaml`）。
- [x] 1.2 确认 `tests/integration/test_install_script.py` 已断言 `agents/default/` 不被创建，且当前绿（无需改测试）。

## 2. spec 收窄

- [x] 2.1 MODIFY `install-bootstrap` 的 "Configuration templates" requirement：删除默认 Agent home seeding 描述与 scenario，收窄为 Platform-home-only（delta 已在 `specs/install-bootstrap/spec.md`）。

## 3. 收尾验证

- [x] 3.1 `make test-pr` 全绿 + `uv run pytest tests/integration/test_install_script.py tests/integration/test_deployment_docs.py -q` 绿（对照 main 基线无新增失败）。
- [x] 3.2 spec delta 由 `opsx:archive` 应用进 `openspec/specs/install-bootstrap/spec.md`，不手改 live spec。

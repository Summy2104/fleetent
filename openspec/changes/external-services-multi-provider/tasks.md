# Tasks — external-services-multi-provider（P6）

> 依赖 P0、P2。TDD：测试任务前置。外部 HTTP 用 respx。

## 1. provider 适配接口

- [ ] 1.1 写测试（unit）：`ServiceProvider` 适配接口的契约——授权 URL 构造 / token 交换字段 / client 构造 / scope 规范化，用 stub 适配验证工厂按 kind 选型。
- [ ] 1.2 实现：`ServiceProvider` 接口 + 工厂（按 `external_services.kind` 选型）。运行 1.1 见绿。

## 2. ≥2 真实服务适配

- [ ] 2.1 写测试（integration）：google-drive 与 github 两服务各自经其适配完成 consent + token 交换 + 解析（respx mock 各自 endpoint），互不影响。
- [ ] 2.2 实现：google-drive、github 两个适配。运行 2.1 见绿。

## 3. 新增服务不改核心

- [ ] 3.1 写测试（integration）：注册一个仅靠「external_services 一行 + 新适配」的服务即可授权解析，无需改 dispatch / consent 核心。
- [ ] 3.2 实现：确保 consent / Vault provider 全程经适配层，无服务专属硬编码。运行 3.1 见绿。

## 4. 收尾

- [ ] 4.1 `make test-pr` 全绿；`uv run pytest tests/integration -q` 无新增失败。

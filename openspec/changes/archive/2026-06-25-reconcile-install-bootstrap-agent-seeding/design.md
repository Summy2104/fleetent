## Context

`install-bootstrap` spec 两个 requirement 对"install 是否 seed 默认 Agent home"给出相反规定。
本 change 让 spec 单一化,对齐已实现且已被测试覆盖的行为(install 只 seed Platform home)。

## Decisions

### 选择保留哪一侧
Ground truth = "不 seed 默认 Agent home":`scripts/install.sh`(`no default agent seeded` +
`fleetent agent init` 教程)、`scripts/install-platform.sh`(`Does NOT create any agent home`)、
`tests/integration/test_install_script.py`(断言 `agents/default/` 不存在)三方一致。故保留
"Install bootstrap seeds explicit Platform and Agent homes" requirement,收窄矛盾的
"Configuration templates" requirement。

### 收窄而非删除 "Configuration templates"
该 requirement 仍承载有用信息——Platform home 的模板来源(`.env.example` / `platform.yaml.example`
→ `.env` / `platform.yaml`)。故 MODIFY 为 Platform-only,而非整体 REMOVE,避免丢失这层映射细节。
收窄后两 requirement 互补:本条讲 Platform 模板 seeding 细节,另一条讲"显式 home、不 seed agent"原则。

### 纯 spec 改动
实现与测试已正确,本 change 不碰代码/测试;spec delta 在 archive 时应用进 `openspec/specs/`。

## Risks / Trade-offs

- 风险极低:不改运行时行为,仅消除文档级矛盾。验证 = `make test-pr` + install 相关测试仍绿(基线无新增失败)。

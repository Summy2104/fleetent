## Why

`install-bootstrap` spec 存在自相矛盾:requirement "Configuration templates" 声称安装脚本
SHALL seed 默认 Agent home(`agents/default/agent.yaml` 等),而 requirement "Install bootstrap
seeds explicit Platform and Agent homes" 声称 SHALL NOT seed 默认 Agent home。实测 ground truth
站在后者一边——`scripts/install.sh`(及 `install-platform.sh`)**不创建任何 agent home**(install.sh
明确打印 "no default agent seeded",引导 `fleetent agent init`),且 `tests/integration/test_install_script.py`
已断言 `agents/default/` 不被创建。故 "Configuration templates" 的 agent-home seeding 部分是过时描述。

## What Changes

- 收窄 `install-bootstrap` 的 "Configuration templates" requirement:**只保留 Platform home 模板
  seeding**(从 `.env.example` 生成 `.env`、从 `platform.yaml.example` 生成 `platform.yaml`),
  **删除全部默认 Agent home seeding** 的描述与 scenario,消除与 "Install bootstrap seeds explicit
  Platform and Agent homes" requirement 的冲突。
- 纯 spec 对齐:实现(install 脚本)与测试早已正确,本 change **不改任何代码或测试**。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `install-bootstrap`: MODIFY "Configuration templates" requirement —— 去掉默认 Agent home
  seeding(`agents/default/*` 创建)的全部内容,使其仅覆盖 Platform home 模板 seeding;与
  "Install bootstrap seeds explicit Platform and Agent homes" 协同不冲突。

## Impact

- specs:`install-bootstrap` 一个 capability 的 delta。
- 代码/测试:无改动(install.sh / install-platform.sh / test_install_script.py 已与目标态一致)。
- 模块边界:无新 package、无 public API / 表 / config namespace 变化、无跨模块依赖变化、无 shim。

## Why

各服务的 init-config(`platform init-config`、`node init-config`)从 **`Path.cwd()`** 读 example 模板(`platform_cli/init_config.py:56`、`node/init_config.py:43`)——这是**真 correctness bug**:`uv tool install` 装好后无仓库 `examples/`/根模板,init-config 直接 `missing template` 失败。同时 `configuration` spec 的 "Canonical templates" 还写着"**exactly these 4**"(`.env` / `platform.yaml` / `agent.yaml` / `agent.env`),但现实根目录早已有 `node.env.example`(并由 align-kb 加 `kb-service.*.example`),spec 过时。

本 change 把"模板寻址"修正为**打包资源读取**(不依赖 cwd),并更新 spec 反映真实 canonical 集合。**保持已定的 flat-at-root 标准不变**(decision:platform 扁平、examples 平铺在根)。

## What Changes

- **修 cwd 模板 bug(全部 init-config)**:`platform init-config` / `node init-config` 改从**打包进 wheel 的 package data**(`importlib.resources`)读根 canonical example,不依赖 cwd。(`kb-service init-config` 在 align-kb 已这么做;本 change 把 platform/node 也对齐到同一打包读取机制。)
- **根 example 纳入 wheel package data**:`.env.example` / `platform.yaml.example` / `agent.yaml.example` / `agent.env.example` / `node.env.example`(+ align-kb 的 `kb-service.*.example`)纳入 hatch wheel artifacts,使装好的环境 init-config 可读。
- **更新 `configuration` spec**:"Canonical templates" 的集合从"exactly these 4"修正为真实集合(加 `node.env.example`、`kb-service.yaml.example`/`kb-service.env.example`),**维持 flat-at-root**;"Local configuration initialization" 明确 init-config 从打包资源读模板、不依赖 cwd。

不改变:**flat-at-root 标准**(examples 仍平铺在仓库根,不进子目录/`config/`);platform 生成布局(仍 `$HOME/platform.yaml` + `.env` 扁平,management.db 在根);生成的运行时子目录(`$HOME/node/`、`$HOME/kb-service/` 不受 examples spec 管);根 `.env` grab-bag 拆分(单独 backlog,本 change 不碰)。

## Capabilities

### New Capabilities
<!-- 无 -->

### Modified Capabilities
- `configuration`: "Local configuration initialization" 明确模板从打包资源读取(不依赖 cwd);"Canonical templates avoid ambiguous agent paths" 的 canonical 集合修正为真实集合(含 node / kb-service),维持 flat-at-root。

## Impact

- **owning area**:`src/fleetent/platform/platform_cli/init_config.py` + `src/fleetent/node/init_config.py`(改 cwd→打包读取)+ `pyproject.toml`(wheel package data 纳入根 `*.example`)+ `configuration` spec + docs。
- **public API surface**:init-config 行为不变(命令/产物路径不变),仅模板**来源**从 cwd 改为打包资源。
- **owned tables**:无。
- **config namespace**:无变更(flat-at-root 维持)。
- **cross-module 依赖**:无。
- **correctness**:修复装好环境(`uv tool install`)下 init-config `missing template` 失败。
- **测试**:unit/integration(在**非仓库 cwd** 下跑 `platform init-config` / `node init-config` 仍生成正确文件——证明不依赖 cwd)。
- **时序**:与 `align-kb-tooling-to-standalone` 都碰 init-config / pyproject / examples,**须在其后执行**(align-kb 先立打包读取机制 + 把 kb-service example 搬到根)。

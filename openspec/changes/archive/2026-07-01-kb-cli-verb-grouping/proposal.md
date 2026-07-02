## Why

fleetent CLI 的既定约定是"**每个可运行组件是一个顶层名词，下挂 `<verb>` 子命令**"——`agent`（init/run/restart/stop）、`platform`（serve/maintenance/…）、`node`（start/init-config）无一例外。**KB 是唯一异类**：把"名词-动词"压成扁平连字符 `kb-serve`/`kb-worker`/`kb-ingest`/`kb-extract`，``kb-service` `init-config`` 更是"连字符名词 + 子命令"的四不像；且 `__main__.py` 用一串 `if argv[0]=="kb-*"` 硬匹配分发，而非像 `platform`/`node` 那样的子命令路由。

本 change 把 KB 命令归一到 `kb <verb>`，与 `agent`/`platform`/`node` 对齐。这是 consistency 修正，不是新发明。项目未上线，一刀切、不留连字符别名。

## What Changes

- **命令改名**（一刀切，无兼容别名）：
  - ``fleetent` `kb-serve`` → `fleetent kb serve`
  - ``fleetent` `kb-worker`` → `fleetent kb worker`
  - ``fleetent` `kb-ingest`` → `fleetent kb ingest`
  - ``fleetent` `kb-extract`` → `fleetent kb extract`
  - `fleetent `kb-service` `init-config`` → `fleetent kb init-config`
- **分发重构**：`__main__.py` 里 KB 的 5 处 `if argv[0]=="kb-*"` 硬匹配，收敛为单一 `kb` 顶层 + 子命令路由（对齐 `node` 的 `argv[1:2]` 分派风格）。
- **全量引用同步**：Makefile 目标命令行、docs 调用示例、tests 中 subprocess 调用、spec 场景里的命令串，全部改到 `kb <verb>`。

**不改**（明确边界）：
- **配置文件名不动**：`kb-service.yaml` / `kb-service.env.example` 保留（那是配置文件名，非命令；`kb` 命令去操作 `kb-service.yaml`，概念自洽）。
- 不新增命令（缺口 `kb create` / `kb reindex` 另立 change）。
- 不碰平台侧 `platform maintenance kb sync` / `vector reindex`（空壳退役/接线另议）。
- 不动 `env-init-commands` spec 里描述的 ``fleetent` `kb-worker` init-config`——那是已退役命令的既有 drift，属另一清理项。

## Capabilities

### New Capabilities
（无）

### Modified Capabilities
- `agent-runtime-cli`: 把"``fleetent` `kb-worker`` 子命令"要求改名为 `fleetent kb worker`，并归入 `kb` 顶层子命令组（懒加载、不被 `agent run` 触发的约束不变）。
- 以下 capability 的**场景中出现 KB 命令调用串**，随本 change 机械同步到 `kb <verb>`（无行为变更，仅调用串）：`kb-standalone-ingest`、`kb-ingest-worker`、`knowledge-base`、`deployment`、`container-deployment`。

## Impact

- **代码**：`src/fleetent/__main__.py`（分发重构）；KB CLI 实现模块（serve/worker/ingest_cli/extract_cli/service_init_config）的 `prog=` 用法名对齐；其余 KB 引用点。
- **构建/运维**：`Makefile`（`kb-worker`/`kb-serve` 目标命令行、`dev-bootstrap` 的 ``kb-service` `init-config``、提示文案）。
- **文档**：~11 个 docs 文件的调用示例（operations/pilot-*、deployment/compose、capabilities/knowledge-base、architecture/* 等）。
- **测试**：入口冒烟/e2e 里以 subprocess 调 `kb-serve`/`kb-worker` 的用例（直接 `import <mod>.main` 的单测不受命令名影响）。
- **spec**：`agent-runtime-cli` delta（命名要求改名）+ 其余命令承载 spec 的场景串机械同步。
- **无迁移、无 DB/schema 变更、无 HTTP/wire 契约变更、无 `kb-service.yaml` 文件名变更**。收尾门禁含 `grep -rn 'kb-serve\|kb-worker\|kb-ingest\|kb-extract\|kb-service init'` 零残留（`kb-service.yaml`/`.env.example` 文件名除外）。

## Context

fleetent CLI 里 `agent`/`platform`/`node` 都是"顶层名词 + `<verb>` 子命令"，只有 KB 用扁平连字符（`kb-serve`/`kb-worker`/`kb-ingest`/`kb-extract`）+ 四不像 `kb-service init-config`，且 `__main__.py` 用 `if argv[0]=="kb-*"` 硬匹配分发。本 change 把 KB 归一到 `kb <verb>`。纯命令表面重命名，无行为变更。项目未上线，一刀切、不留别名。

## Goals / Non-Goals

**Goals**
- KB 命令统一为 `kb serve|worker|ingest|extract|init-config`，与 agent/platform/node 一致。
- `__main__.py` 的 KB 分发收敛为单一 `kb` 子命令路由（学 `node`）。
- 全量同步 Makefile / docs / tests / spec 场景里的调用串。

**Non-Goals**
- 不改配置文件名 `kb-service.yaml` / `kb-service.env.example`。
- 不新增 `kb create` / `kb reindex`（缺口，另立）。
- 不碰平台 `maintenance kb/vector` 空壳、不碰 `env-init-commands` 里已退役的 `kb-worker init-config`（既有 drift）。

## Decisions

**D1：动词用 `serve`，不用 `server`。** `kb serve` 与 `platform serve` 一致（动词）；`kb-serve`→`kb serve`。

**D2：`kb-service init-config` → `kb init-config`。** 消灭 `kb-service` 这个"连字符名词"层，`init-config` 直接挂 `kb`（与 `platform init-config`/`node init-config` 一致）。

**D3：分发用 `node` 风格的手动子命令路由，不引入 argparse 全家桶。**
`__main__.py` 加单一 `if argv[0]=="kb":` 块，按 `argv[1:2]` 分派到 serve/worker/ingest/extract/init-config 各自 `main(argv[2:])`（各模块已自带 argparse，不动其内部）。删掉原 5 处 `if argv[0]=="kb-*"`。与 `node start|init-config` 的现有写法同构，最小侵入。缺子命令/未知子命令 → 打印 usage 退 1。

**D4：spec 策略——只为"命名要求"写 delta，其余场景串机械同步。**
KB 命令在 spec 里唯一作为**命名 requirement** 出现的是 `agent-runtime-cli` 的"`fleetent kb-worker` 子命令"——为它写正式 MODIFIED delta（改名 + 归入 `kb` 组）。其余 spec（`kb-standalone-ingest`/`kb-ingest-worker`/`knowledge-base`/`deployment`/`container-deployment`）里命令只是**场景内的调用示例串**（requirement 行为不变），apply 时直接机械改这些串、由收尾的 grep 零残留门禁把关。对纯改名硬写 6 份全 requirement-block delta 不成比例。

**D5：配置文件名保留。** `kb-service.yaml`/`kb-service.env.example` 是配置文件名不是命令；只改命令、不改文件名，爆炸半径最小。收尾 grep 明确豁免这两个文件名。

## Risks / Trade-offs

- **漏改某处调用串** → 收尾门禁 `grep -rn 'fleetent kb-serve|fleetent kb-worker|fleetent kb-ingest|fleetent kb-extract|kb-service init'` 必须零命中（`kb-service.yaml`/`.env.example` 文件名除外）；覆盖 src/tests/docs/Makefile/openspec。
- **误改文件名** → 只替换命令调用串（`fleetent kb-serve` 这种前缀），不替换裸 `kb-service`（可能是文件名）；apply 逐处确认。
- **entrypoint 冒烟测试以 subprocess 调旧名** → 这些测试会先红（命令没了），改到新名后转绿——正是 TDD 想要的信号。
- **docs 面广（~11 文件）** → 属非结构不变量的普通文档编辑；机械替换 + 人工过一遍即可。

## Migration Plan

无数据迁移。部署方若脚本调 `fleetent kb-serve`/`kb-worker` 等，改用 `fleetent kb serve`/`kb worker`（本仓库 Makefile/docs 一并改）。回滚 = revert。

## Open Questions

无。

## Context

`configuration` spec 早已定 examples **flat-at-root**(不进 `config/` 子目录);现实根目录有 `.env.example`/`platform.yaml.example`/`agent.yaml.example`/`agent.env.example`/`node.env.example`,加 align-kb 移来的 `kb-service.*.example`。但:
- 所有 init-config(`platform_cli/init_config.py:56`、`node/init_config.py:43`)从 `Path.cwd()` 读模板 → 装好环境失败(真 bug)。
- spec "Canonical templates" 写"exactly these 4",与现实(node/kb example 已在)不符。

pyproject 用 hatch(`[tool.hatch.build.targets.wheel] packages=["src/fleetent"]`)——根 `*.example` 不在 `src/`,默认不进 wheel,这正是 cwd 依赖的根源。

## Goals / Non-Goals

**Goals:**
- 全 init-config 从打包资源读模板(不依赖 cwd),修装好环境失败。
- 根 `*.example` 纳入 wheel package data。
- spec canonical 集合修正为真实集合,维持 flat-at-root。

**Non-Goals:**
- 不动 flat-at-root 标准、不引入 `examples/<role>/`/`config/`。
- 不改 platform 生成布局(扁平,management.db 在根)。
- 不拆根 `.env` grab-bag(单独 backlog)。
- 不改 KB(align-kb 已处理 `kb-service` `init-config` + example 搬根)。

## Decisions

### 决策:打包根 example 进 wheel,init-config 经 importlib.resources 读
- hatch wheel 纳入根 `*.example`(`[tool.hatch.build.targets.wheel.force-include]` 或等价,把根模板映射进包内资源路径,如 `fleetent/_templates/`)。init-config 用 `importlib.resources.files("fleetent")...` 读,替代 `Path.cwd()/模板`。
- **为什么**:wheel `packages=["src/fleetent"]` 只打 src;根模板需显式 force-include 才进 wheel。读取统一走包资源,装好/源码两种环境都成立。

### 决策:与 align-kb 共用同一打包读取机制
- align-kb 已为 ``kb-service` `init-config`` 建打包读取 + 把 kb-service example 搬根。本 change **复用同一机制**,把 `platform`/`node` init-config 也切过去,并把其余根 `*.example` 一并纳入 package data。故**须在 align-kb 之后执行**。

### 决策:spec canonical 集合修正,维持 flat-at-root
- "exactly these 4" → 真实集合(+node/kb,全平铺在根)。明确"不存在 `examples/kb-service/`""不用 `config/`/`examples/<role>/` namespace""example 纳入 package data"。

## Risks / Trade-offs

- **[force-include 路径/资源读取不匹配]** 打包路径与 `importlib.resources` 读取路径要一致。**Mitigation**:测试在非仓库 cwd（甚至装好的临时 venv 风格）下跑 init-config，断言生成成功。
- **[与 align-kb 重叠 pyproject/init-config]** **Mitigation**:本 change 在 align-kb 之后,从其建立的机制扩展;merge 时 pyproject artifacts 列表叠加,小冲突好解。
- **[遗漏某个 init-config]** agent init / 其它。**Mitigation**:`git grep "Path.cwd()" src/**/init*` 列全所有 init-config 的 cwd 读取点,逐一切换。

## Migration Plan

- 把根 `*.example` 纳入 wheel package data;platform/node init_config 改打包读取;更新 spec。无运行时数据迁移。
- 回滚:还原代码;模板仍在根,源码环境不受影响(只是装好环境回到旧 bug)。

## Open Questions

- 模板在包内的资源路径命名(`fleetent/_templates/<name>` vs 直接 force-include 根名):实现时与 align-kb 的 kb-service 模板资源路径保持一致。

## 1. 根 example 纳入 wheel package data

- [ ] 1.1 写测试:从打包资源能读到全部 canonical example(`.env.example`/`platform.yaml.example`/`agent.yaml.example`/`agent.env.example`/`node.env.example`/`kb-service.*.example`)(见红)
- [ ] 1.2 pyproject:hatch wheel force-include 根 `*.example`(与 align-kb 的 kb-service 模板资源路径一致);跑 1.1 见绿

## 2. init-config 改打包读取(修 cwd bug)

- [ ] 2.1 `git grep "Path.cwd()" src/fleetent/**/init*` 列全所有 init-config 的 cwd 读取点
- [ ] 2.2 写 integration 测试:在**非仓库 cwd**(无根 `*.example`)下跑 `fleetent platform init-config` / `fleetent node init-config`,正确生成 `.env`/`platform.yaml` / `node/.env`(见红)
- [ ] 2.3 改 `platform_cli/init_config.py` 与 `node/init_config.py`:模板从 `importlib.resources`(包资源)读,替换 `Path.cwd()`;复用 align-kb 建立的读取机制;跑 2.2 见绿
- [ ] 2.4 确认 init-config 命令/产物路径/幂等/`--force`/`--dry-run` 行为不变(只换模板来源)

## 3. spec + 收尾

- [ ] 3.1 确认 `configuration` spec delta 与实现一致(canonical 集合含 node/kb、flat-at-root、打包读取);`openspec validate normalize-service-config-layout` 通过
- [ ] 3.2 跑 `make test-pr` + `make test-unit-ci`(含 76% 覆盖率关)+ `make test-integration-ci`,判"对照 main 基线无新增失败、覆盖率不破 76"(并行 flaky 先 `-p no:randomly` 串行复核)
- [ ] 3.3 ruff format/check;module-boundaries 护栏过
- [ ] 3.4 更新 docs:init-config 模板来自打包资源(装好环境也能跑);canonical example 平铺在根的清单(非代码产物,人工确认后再 commit)

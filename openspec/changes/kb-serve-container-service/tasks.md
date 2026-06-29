## 1. compose 加 kb-serve 服务

- [ ] 1.1 在 `docker-compose.yml` 加 `kb-serve` 服务:同镜像 + `command: ["kb-serve","--config","${FLEETENT_HOME:?set FLEETENT_HOME}/kb-service.yaml"]` + env_file `.env` + `FLEETENT_HOME` env + `volumes: *fleetent-home-volume`(与 kb-worker 共享)+ `networks: [fleetent]` + `restart: unless-stopped`;**不挂 docker socket**
- [ ] 1.2 确认 kb-serve 不 publish 宿主端口(仅网络内服务名可达);如需外部访问再加 ports（默认不加）
- [ ] 1.3 `docker compose config` 校验通过(yaml 合法、引用解析);四服务(platform/node/kb-worker/kb-serve)都在

## 2. spec 对齐

- [ ] 2.1 确认 `container-deployment` spec delta 三条 MODIFY(多角色 +kb-serve、compose 四服务、socket 排除 +kb-serve)与 compose 一致;`openspec validate kb-serve-container-service` 通过

## 3. 网络可达 + provider 接线

- [ ] 3.1 确认 agent 兄弟容器与 kb-serve 同网络可解析服务名(沿用 agent↔node 同网络接线);若 agent 不在 fleetent 网络,补网络接线
- [ ] 3.2 确认 agent 的 `knowledge.provider.url` 接线:materialize 是否写 `http://kb-serve:<port>`;若缺,补 materialize 写入 provider.url（或记为紧邻待办并在 docs 注明手动配）

## 4. 烟测 + 文档 + 收尾

- [ ] 4.1 managed-stack 烟测(沿用现有 e2e harness):compose 栈 boot、kb-serve 在网络内可达、agent(http provider)经 kb-serve 读到 kb/ chunks（端到端）
- [ ] 4.2 跑 `make test-pr` + `make test-unit-ci`(含 76% 覆盖率关)+ `make test-integration-ci`,判"对照 main 基线无新增失败、覆盖率不破 76"(integration 并行 flaky 先 `-p no:randomly` 串行复核)
- [ ] 4.3 更新部署文档:kb-serve 角色、agent→kb-serve 寻址、kb-service.yaml/.env provisioning、单/多租户 kb-serve 编排说明(非代码产物,人工确认后再 commit)

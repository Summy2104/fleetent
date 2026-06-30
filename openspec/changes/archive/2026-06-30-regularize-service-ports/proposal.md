## Why

各服务默认端口是历史上随手定的,没有可记忆的规律:`8765`(platform)、`8766`(dev agent)挨着,然后跳到 `8786`(node forwarder)/`8787`(kb-serve),中间一大段空号;agent 内部容器口又是孤立的 `18765`;embedding 默认端点还自相矛盾(`agent_config.py` 用 `:11434`,`kb-service.yaml.example` 用 `:9000`)。

更重要的是上轮 review 厘清了一个**架构事实**:多实例(多 node / 多租户 KB / 多 agent)在容器路径下靠 **IP / 容器服务名** 扩展,**不靠端口号段**——容器后端每个 agent 用同一固定内部口(`agent_internal_port`)靠容器名区分(`node/backend.py`),node 每机一个 forwarder 同口不同 host(`forwarder_contract.py`),多租户 kb-serve 在容器里同口不同服务名。端口号段**只**在"裸机/进程后端、多服务共享一台机网络栈"这个回退场景才需要。所以正确的规律是**每角色一个固定端口**,而非给不存在的扩展预留号段。

## What Changes

**每角色一个固定端口,连续、可记忆;扩展靠 IP/服务名,不靠号段:**

```
8765  platform        — 1/部署（不变）
8766  agent           — agent 的 /chat+/ws 服务口（不变）
                        dev/standalone 发布到宿主；node-managed 容器内部绑同口、由 node forwarder 代理；
                        node-managed 进程后端因共享宿主网络栈而动态分配（回退）
8767  node forwarder  — 1/机器；多机同口不同 host                （8786→8767）
8768  kb-serve        — 1/租户；容器同口不同服务名；裸机多租户 8768,8769… 回退  （8787→8768）
```

- **node forwarder `8786 → 8767`**:改 `DEFAULT_FORWARDER_PORT` 常量(node 寻址、forwarder bind、reconcile loopback 全走此常量,改一处生效)+ compose 端口映射。
- **kb-serve `8787 → 8768`**:改 `serve.py` 默认 + `service_config.py` `KBServiceSection.port` 默认 + `kb-service.yaml.example`。
- **agent 内部容器口 `18765 → 8766`**:改 `node/config.py` `agent_internal_port` 默认 + `FLEETENT_NODE_AGENT_INTERNAL_PORT` env 默认。让"agent 永远在 8766 服务"成为单一事实(暴露与否由部署模式决定),干掉孤立魔数 `18765`。
- **embedding 默认收口**:`kb-service.yaml.example` 的 `:9000` 统一为 `:11434`,与 `agent_config.py` 现有默认一致。
- **顺带修复 spec drift**:`container-deployment` spec line 24 仍写 Design I 前的 `kb-service/kb-service.yaml` 与 `tenants/<tenant>/kb/`(`tidy-kb-service-layout-and-env` 漏同步);因本 change 必须重写该 requirement 改端口,顺手把路径同步为 `kb-service/<tenant>/kb-service.yaml` 与扁平 `data/`,不留已知错误文本。

**不变**:platform `8765`、agent serve `8766`(dev)、agent 托管动态/容器机制、`FLEETENT_HOME` 等;所有端口仍可经 env/CLI 覆盖,只动默认。

## Capabilities

### Modified Capabilities
- `container-deployment`:node forwarder 暴露端口 `8786 → 8767`;新增"规范服务端口"约定(端口表 + 多实例靠 IP/服务名而非号段的原则);顺带同步 kb-service 路径到 Design I。

## Impact

- **owning packages**:`node/`(forwarder_contract、config)、`knowledge_base/`(serve、service_config、模板)+ `docker-compose.yml` + `Makefile` + docs(compose.md / AGENTS.md gotcha / architecture)。
- **public surface**:默认端口变更(node forwarder 8767、kb-serve 8768、agent 内部 8766);**env/CLI 覆盖不变**,固定端口的运维者不受影响,仅依赖默认者随之变。
- **owned tables / config namespace / cross-module 依赖**:无新增表;`FLEETENT_NODE_AGENT_INTERNAL_PORT` 默认值变;不新增跨模块依赖。
- **migration / shim**:纯默认值变更,无 schema 迁移。compose 同步更新;裸机/dev 用默认者新端口即时生效;memory/docs 里旧端口记述同步。
- **解耦基线**:不影响;不碰 platform↔node 依赖方向。
- **测试**:`make test-pr` + `make test-integration-ci` 全绿;更新断言旧端口的测试(forwarder/kb-serve/agent-internal/makefile 默认)。

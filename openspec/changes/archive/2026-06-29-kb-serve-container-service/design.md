## Context

KB 独立部署线代码已全落地(serve.py / worker.py standalone / standalone_sweep / kb-service.yaml 契约)。`__main__.py:153` 已有 `kb-serve` 角色;`docker-compose.yml` 已有 platform/node/kb-worker,kb-worker 用 `["kb-worker","--config","$FLEETENT_HOME/kb-service.yaml"]`。本 change 只补 kb-serve 服务 + spec + docs,不碰 src。

## Goals / Non-Goals

**Goals:**
- compose 加 kb-serve 长驻服务(读 API),接入 fleetent 网络、共享 kb/ 卷、不挂 socket。
- managed 栈端到端:agent(http provider)→ kb-serve → kb/。

**Non-Goals:**
- 不改 KB 业务代码(serve/worker/ingest 已落地)。
- 不改 platform/node/kb-worker 既有服务、path-parity、forwarder。
- 不做多租户多 kb-serve 的自动编排(本 change 默认单租户;多租户加服务为后续/手动)。

## Decisions

### 决策:kb-serve 服务镜像 kb-worker 块,加读端口
- 同镜像、`command: ["kb-serve","--config","$FLEETENT_HOME/kb-service.yaml"]`、env_file `.env`、`FLEETENT_HOME`、`restart: unless-stopped`、`networks: [fleetent]`、`volumes: *fleetent-home-volume`。
- kb-serve 监听端口由 kb-service.yaml 的 `service.port` 决定;**compose 内不必 publish 到宿主**(只供网络内 agent 经服务名 `kb-serve:<port>` 访问);如需外部访问再 ports 映射。

### 决策:kb-serve 与 kb-worker 共享 FLEETENT_HOME 卷
- 二者挂同一 `*fleetent-home-volume`(path-parity);worker 写 `tenants/<t>/kb/`,serve 读同一 kb/。同主机真进程 + WAL 一写多读,无 RO 挂载 WAL 隐患(那是 agent 容器文件挂载的问题,这里是服务进程直接访问)。

### 决策:agent 经服务名寻址 kb-serve
- agent 兄弟容器(node 拉起,已与 node 同网络)需与 kb-serve 同网络;agent 的 `knowledge.provider.url` 指 `http://kb-serve:<port>`(node materialize 写入 agent home / 配置)。本 change 保证网络可达 + 文档说明 url 接线;具体 materialize 写 provider.url 若未就位,记为接线待办(provider 配置字段由 kb-http-provider 定义)。

### 决策:per-tenant 单服务默认
- compose 默认 `kb-serve --tenant default`(配置文件指定 tenant_id)。多租户为每租户加一个 kb-serve(不同端口/服务名),本 change 不自动展开。

## Risks / Trade-offs

- **[agent→kb-serve 网络可达]** agent 是 node 动态拉起的兄弟容器,需与 kb-serve 同网络。**Mitigation**:沿用 agent↔node 同网络的既有接线;烟测验证 agent 容器能解析 kb-serve 服务名。
- **[provider.url 接线缺口]** agent 的 knowledge.provider.url 指向 kb-serve 需 node materialize 写入。**Mitigation**:本 change 聚焦 compose 服务 + 网络 + 卷;若 materialize 尚未写 provider.url,记为明确待办(可在本 change 或 kb-http-provider 的 materialize 接线补)。
- **[共享卷一致性]** worker 写 / serve 读同一 kb.db。**Mitigation**:同主机 WAL 一写多读成立;非 agent 的 RO 文件挂载,无 A2 隐患。

## Migration Plan

- 纯 compose + spec + docs 加法。compose up 多起一个 kb-serve;不影响既有服务。回滚删 kb-serve 服务块即可。

## Open Questions

- agent provider.url 的 materialize 接线是否已就位(kb-http-provider 落地时是否写了 provider.url):实现时确认,缺则在本 change 补 materialize 写 `knowledge.provider.url=http://kb-serve:<port>`,或记为紧邻待办。

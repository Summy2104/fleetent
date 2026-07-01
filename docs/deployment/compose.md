# Docker Compose 推荐生产路径

本 runbook 覆盖单机 on-prem 部署：同一个镜像通过 entrypoint 运行
`platform / node / kb-worker / kb-serve` 四个长驻角色，node 使用 `node.backend=container`
经宿主 Docker socket 拉起 agent 兄弟容器。裸机 `uv tool install` 与
`node.backend=process` 仍可用于开发、调试或回滚。

## 前置条件

- Docker Engine 与 Docker Compose plugin 可用。
- 部署用户能访问 `/var/run/docker.sock`。
- 准备一个宿主上的持久目录，例如 `/srv/fleetent`。
- 复制 `.env.example` 到 `.env`，填入平台、node、模型与 IM 所需变量，不提交真实 secret。

`DEPLOY_FLEETENT_HOME` 是 Makefile 的生产数据目录，默认 `/srv/fleetent`。Compose
会把它作为 `FLEETENT_HOME` 注入容器，并用完全相同的宿主路径挂载到容器内，这就是
path-parity：node 写入的 agent home、agent 读取的文件、sandbox bind mount 的 source
都由宿主 dockerd 解释为同一条真实路径。

## 启动

```bash
make up DEPLOY_FLEETENT_HOME=/srv/fleetent
curl -fsS http://127.0.0.1:8765/health
```

Compose 会启动：

- `platform`：监听 `8765`，唯一可设置 `FLEETENT_AUTO_UPGRADE` 的服务。
- `node`：监听 forwarder `8767`，挂载 `/var/run/docker.sock`，设置
  `FLEETENT_NODE_BACKEND=container`。
- `kb-worker`：消费 KB ingest 队列，读取 `${FLEETENT_HOME}/tenants/default/kb/kb-service.yaml`
  与 `${FLEETENT_HOME}/tenants/default/kb/.env`。
- `kb-serve`：提供 KB 读 API，读取同一份 `${FLEETENT_HOME}/tenants/default/kb/kb-service.yaml`
  与 `${FLEETENT_HOME}/tenants/default/kb/.env`，以及同一棵
  `FLEETENT_HOME` 数据卷。

agent 不在 compose 中静态声明。node 根据 desired state 拉起 agent 兄弟容器，并把
agent 接入 `fleetent` compose 网络；agent 内部端口由 container backend 管理，不对宿主发布。
`kb-serve` 默认也**不对宿主发布端口**；agent 在 compose 网络内用服务名
`http://kb-serve:<service.port>/search` 访问即可。只有需要宿主外部直接访问 KB 服务时，才额外给
`kb-serve` 配置 `ports:`。

## 版本与陈旧检测

镜像构建时注入 build commit，运行时可查：

```bash
docker compose run --rm platform fleetent version
make deploy-status
```

`make deploy-status` 对比运行镜像的 build commit 和当前源码 `HEAD`。二者不一致时会报告部署
陈旧，并同时输出 deployed commit 与 head commit，用于发现“git pull 了但没重建/重启”的状态。

## 重部署

```bash
make redeploy DEPLOY_FLEETENT_HOME=/srv/fleetent
make deploy-status DEPLOY_FLEETENT_HOME=/srv/fleetent
```

`make redeploy` 先执行 `docker compose build --build-arg GIT_COMMIT=<HEAD>`，构建成功后才
`docker compose up -d`。构建失败时不会重启正在运行的服务。没有 Compose 的裸机环境会降级为
`uv tool install --force .`，并提示 operator 手动重启裸机 fleetent 服务。

## 升级

```bash
make upgrade DEPLOY_FLEETENT_HOME=/srv/fleetent
```

管理库 Alembic 升级只由 platform 跑。node、kb-worker、agent 不设置
`FLEETENT_AUTO_UPGRADE`，避免多服务并发抢跑管理库迁移。agent 侧数据库仍走各自的嵌入式
forward-only migration。

## KB 服务接线

默认单租户 compose 把 tenant 固定为 `default`：`kb-worker` 写
`${FLEETENT_HOME}/tenants/default/kb/data/`，`kb-serve` 从同一挂载卷读取；该目录下固定有
`kb.db`、`kb_vectors.db`、`kb_ingest_queue.db` 三个文件，而 `kb-service.yaml` 与 `.env` 留在
`${FLEETENT_HOME}/tenants/default/kb/` 根。这条路径是同主机 WAL 一写多读，
 不是 agent 的只读文件挂载场景。

若宿主上还留有旧布局 `$FLEETENT_HOME/kb-worker/.env`，先执行
`fleetent kb init-config --tenant default`，再把旧文件里的 secret 迁到
`$FLEETENT_HOME/tenants/default/kb/.env`，把 connector / service 配置迁到
`$FLEETENT_HOME/tenants/default/kb/kb-service.yaml`，随后停用旧 `kb-worker/.env`。若开发机已经按旧
standalone 布局写入过 KB 文件，需要一次性手动把
旧的 `kb-service/<tenant>/data/tenants/<tenant>/{kb.db,kb_vectors.db}` 或旧根队列文件
迁到 `$FLEETENT_HOME/tenants/<tenant>/kb/data/{kb.db,kb_vectors.db,kb_ingest_queue.db}`。

当前 platform materialize **不会自动**把 managed agent 改成 `knowledge.provider.type=http`。
如果要让 compose 栈里的 agent 经 `kb-serve` 远程读 KB，需要在 agent authoring 的
`config_overrides` 中显式写入 provider，例如：

```yaml
knowledge:
  provider:
    type: http
    url: http://kb-serve:8768/search
    auth_ref: env:FLEETENT_KB_SERVICE_KEY
```

同时让 `${FLEETENT_HOME}/tenants/default/kb/kb-service.yaml` 的 `service.service_key_ref` 指向
`${FLEETENT_HOME}/tenants/default/kb/.env` 中的同一个变量：

```yaml
service:
  tenant_id: default
  service_key_ref: env:FLEETENT_KB_SERVICE_KEY
  host: 0.0.0.0
  port: 8768
```

```dotenv
FLEETENT_KB_SERVICE_KEY=replace-me
```

`url` 里的端口取 `tenants/default/kb/kb-service.yaml` 的 `service.port`；compose 默认单租户起一个
`kb-serve`。
如果要做多租户，需要为每个租户额外起一个 `kb-serve` 服务，使用不同服务名/端口，并把对应 agent
的 `knowledge.provider.url` 指到那个服务。

## 数据布局

`FLEETENT_HOME` 下保持现有物理布局：

```text
management.db
tenants/<tenant>/kb/kb-service.yaml
tenants/<tenant>/kb/.env
tenants/<tenant>/kb/data/kb.db
tenants/<tenant>/kb/data/kb_vectors.db
tenants/<tenant>/kb/data/kb_ingest_queue.db
tenants/<tenant>/agents/<agent_id>/data/
```

长驻服务挂载整棵 `FLEETENT_HOME`。agent 容器由 node 的 container backend 精确挂载自身
`tenants/<tenant>/agents/<agent_id>/` 为读写，并通过 HTTP provider 访问对应 tenant 的
`kb-serve`；不再假设 agent 直接只读挂载 standalone 的 `kb.db` / `kb_vectors.db`；
不得挂载 `management.db` 或其它 agent 子树。旧
`FLEETENT_KB_WORKER_EMBEDDING_*` 环境变量已退役，embedding / extraction 统一从
`kb-service.yaml` 的 `embedding` / `extraction` section 读取。

## 日志与停止

```bash
make logs DEPLOY_FLEETENT_HOME=/srv/fleetent
make down DEPLOY_FLEETENT_HOME=/srv/fleetent
```

`make down` 不带 -v，且不会删除 bind mount 数据目录。需要清理数据时由 operator 显式处理
`DEPLOY_FLEETENT_HOME`，不要把数据删除绑定到停止服务。

## 回滚

两种回滚方式：

1. 指定上一个 commit 重新构建并 `make redeploy`。
2. `make down` 后重启原裸机服务路径（`uv tool install` + `node.backend=process`）。

回滚前先备份 `management.db` 与对应 tenant/agent 数据目录。

## docker.sock 信任边界

node 服务挂载 `/var/run/docker.sock`，等价于让 node 拥有宿主 Docker 管理权限。这是单机
on-prem 信任边界内的显式取舍，用于拉起 agent 兄弟容器和支持 sandbox Docker 后端。
`platform`、`kb-worker`、`kb-serve` 都不挂这个 socket。
rootless Docker / 多主机 / Kubernetes 不在本 runbook 范围内；如需 rootless Docker，需要单独验证
socket 权限、bind mount path-parity 和 sandbox 能力矩阵。

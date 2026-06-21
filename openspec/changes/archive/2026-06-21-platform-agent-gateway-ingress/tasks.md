> TDD 硬门禁:每个实现 task 先写测试见红 → 实现见绿。最窄命令 `uv run pytest <file>::<test> -x -q`。测试任务先于实现,不可跳步。

## 1. B2 · materialize 供给 FLEETENT_TUI_TOKEN(materialize.py)

- [x] 1.1 写测试:materialize 托管 agent 时,`.env` 无 token 则生成 `ma-<64hex>`、有则保留;且该 token **不进** desired-state 明文 config(复用 A 的剥离断言风格)。先见红。
- [x] 1.2 实现:在 `materialize._seed_env`(或相邻供给点)为托管 agent 供给 `FLEETENT_TUI_TOKEN`,经既有 secret 路径下发。跑 1.1 见绿。

## 2. Agent gateway 坐实(agent_app)

- [x] 2.1 写测试:agent 以 `--port` 起时 `/chat`·`/ws` 可用且 `/ws` 经 `FLEETENT_TUI_TOKEN` 认证(沿用既有);无 token / 错 token 拒绝。先见红(若已覆盖则补缺口)。
- [x] 2.2 实现/坐实 gateway + auth 的任何缺口(大概率已具备,仅补齐)。跑 2.1 见绿。

## 3. B3 + Node forwarder(node/)

- [x] 3.1 写测试:node 拉起 agent 时带 **loopback `--port`** 并登记 agent→port 映射。先见红。
- [x] 3.2 实现:`node/backend.py` Popen 带内网 `--port` + 端口分配/登记(进程内映射或 node_agent_status,无 schema 优先)。跑 3.1 见绿。
- [x] 3.3 写测试:node forwarder——**node key** 认证通过则把请求转给目标 agent 的 loopback 端口并注入该 agent 的 `FLEETENT_TUI_TOKEN`;无效 key 拒绝;流式响应原样回传;仅绑内网。先见红。
- [x] 3.4 实现 node forwarder(新建,仅内网监听)。跑 3.3 见绿。

## 4. 平台门面 + 路由 + AgentTransport(server.py / platform)

- [x] 4.1 写测试:`AgentTransport` 接口 + `DirectHttp` 实现——拨 node forwarder(带 node key)、relay 流式响应;契约支持流式(分块,不缓冲成单块)。先见红。
- [x] 4.2 实现 `AgentTransport` + `DirectHttp`。跑 4.1 见绿。
- [x] 4.3 写测试:平台 ingress `POST /admin/agents/{name}/chat` 与 `/ws`——admin 认证;按 placement 路由到目标 node;未 placement/未知 agent 返回明确不可用(非 hang);非 admin 401/403 不转发。先见红。
- [x] 4.4 实现平台 ingress + placement 路由(复用 `placement_store`)→ AgentTransport。跑 4.3 见绿。

## 5. 端到端(integration)

- [x] 5.1 写集成测试:运维(admin)经平台 ingress → node forwarder → loopback agent,拿到 agent 的(流式)回复;认证链每跳都被校验。先见红 → 全链路实现后见绿。

## 6. Change 收尾验证

- [ ] 6.1 `make test-pr` + `make test-unit-ci`(76% 覆盖)全绿,对照 main 基线无新增失败。
- [ ] 6.2 本 change 跨切面(改 server.py + node + agent_app + materialize)→ 跑**全量**集成:`uv run pytest tests/integration -q`(对照 main 基线无新增失败)。
- [ ] 6.3 `PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py` 通过;确认未引入 agent→platform / node→platform 反向 import 依赖。
- [ ] 6.4 基线冒烟:无 platform/node 时 `fleetent agent run`(直跑)仍能对话——gateway 是既有 `--port` 能力,未被破坏。

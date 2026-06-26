## Context

agent 的两个示例模板（`agent.yaml.example` / `.env.example`）当前埋在 `agents/default/` 下，
与其它组件模板（platform/node/kb-worker 均平铺在根目录）不一致；且 `agents/default/` 演示的
agent home 布局缺了真实的 `tenants/` 层。本 change 把模板平铺到根并对齐命名，顺带修正无歧义处的
tenant-layer 表述。

## Goals / Non-Goals

- Goals：模板平铺根目录 + 命名对齐 + 同步全部引用（含 live specs）+ 保守修正 tenant drift。
- Non-Goals：不解决 `install-bootstrap` spec 内部 "是否 seed 默认 Agent" 的预存矛盾；不改
  `docker-compose.yml` 的 `./agents` 运行时挂载语义；不动 `archive/` 历史记录。

## Decisions

### 命名：`agent.yaml.example` + `agent.env.example`
根目录 `.env.example` 已被 platform 占用（无前缀=主部署 env，对应 docker-compose `env_file: .env`），
故 agent env 必须带前缀，取 `agent.env.example`，与 `node.env.example` / `kb-worker.env.example` 的
`<component>.env.example` 惯例一致；`agent.yaml.example` 对齐 `platform.yaml.example`。

### 运行时零影响
`fleetent agent init` 用 `runtime/agent_init.py` 的**内嵌**模板（`_template_agent()`），不读这些
`.example` 文件；容器跑 `platform serve`，`docker_entrypoint.sh` 不消费 `agents/default/`。故迁移无需
任何 re-export shim 或运行时兼容层。Dockerfile 删除 `COPY agents/default/` 与 `mkdir agents/default`，
改为把两个根模板加入既有 `COPY ... ./`。

### 唯一代码硬依赖 = 两个测试断言
`tests/unit/test_agent_config.py`（parse-guard）与 `tests/integration/test_deployment_docs.py`
（多条路径/ Dockerfile 文本断言）硬编码旧路径，必须同步——这是本 change 的 TDD 红/绿锚点。

### tenant drift 保守范围
只改无歧义处：README 134/206、`file-agent-runtime` spec、`configuration` spec 的 Agent home 路径；
`install-bootstrap` 仅 re-path 模板来源。`agent-runtime-cli` spec 已是正确的 tenant-aware 路径，不动。

## Risks / Trade-offs

- 风险：遗漏某处旧路径引用 → 用全仓 grep（排除 `archive/` 与 `/admin/agents/default` API 路由）兜底。
- Trade-off：`install-bootstrap` spec 留预存矛盾未解 → 已在 proposal/spec 注记，单开 change 处理。

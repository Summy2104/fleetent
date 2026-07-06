# kb-agent-binding — Delta

## ADDED Requirements

### Requirement: 绑定物化产出可用的 http provider
当 agent 存在至少一条 KB 绑定，且平台已配置 `Settings().kb_serve`（`url` 与 `service_key_ref` 均非空）时，agent 物化（materialize）SHALL 在 agent.yaml 的 `knowledge` 段产出 `provider: {type: "http", url: <kb_serve.url>, auth_ref: "env:FLEETENT_KB_SERVICE_KEY"}`。平台未配置 kb_serve（任一字段为空）时，物化 SHALL 保持既有行为（provider 缺省 local），且 MUST NOT 因此失败。agent 无任何 KB 绑定时，`knowledge` 段行为不变（不启用、不写 provider）。

#### Scenario: 绑定且 kb_serve 已配置时物化 http provider
- **WHEN** agent 在 `agent_kbs` 有绑定，且平台 `Settings().kb_serve.url` 与 `service_key_ref` 均已配置，触发物化
- **THEN** 物化产物 agent.yaml 的 `knowledge.provider` 为 `type: http`、`url` 等于 `kb_serve.url`、`auth_ref` 为 `env:FLEETENT_KB_SERVICE_KEY`，且 `enabled: true`、bindings 与绑定表一致

#### Scenario: kb_serve 未配置时保持 local 且不失败
- **WHEN** agent 在 `agent_kbs` 有绑定，但平台未配置 `kb_serve.url`（或 `service_key_ref` 为空），触发物化
- **THEN** 物化成功完成，`knowledge.provider` 保持缺省（local），与本变更之前的行为一致

#### Scenario: 无绑定时 knowledge 段不启用
- **WHEN** agent 在 `agent_kbs` 无任何绑定，触发物化
- **THEN** `knowledge` 段保持不启用，不含 provider 接线（与既有行为一致）

### Requirement: KB service key 经 desired-state secrets 下发
node desired-state 的 per-agent secrets 装配 SHALL 为被 agent.yaml 引用（经 `collect_env_var_names` 收集，含 `auth_ref: env:` 形式）的 `FLEETENT_KB_SERVICE_KEY` 回填平台解析 `kb_serve.service_key_ref` 所得的 key 值；per-agent 显式 secret（`agent_secrets`）SHALL 优先于平台回填。平台解析 ref 失败（如 env 缺值）时 SHALL 跳过回填并记录 warning，MUST NOT 使该 agent 的 desired-state 组装整体失败。不引入 `referenced_env_names` 之外的第二种 secret 判定口径。

#### Scenario: 绑定 agent 的 desired-state 携带 KB key
- **WHEN** 某 managed agent 物化出 `auth_ref: env:FLEETENT_KB_SERVICE_KEY`，node 拉取 desired-state
- **THEN** 该 agent 的 `secrets` 载荷含 `FLEETENT_KB_SERVICE_KEY`，值为平台解析 `kb_serve.service_key_ref` 的结果；node 依既有流程落盘 `.env`，自愈门禁判定满足，不产生自愈循环

#### Scenario: per-agent 显式 secret 优先
- **WHEN** 管理员已通过 agent secrets 通道为该 agent 显式设置 `FLEETENT_KB_SERVICE_KEY`
- **THEN** desired-state 下发的是显式设置的值，平台回填不覆盖它

#### Scenario: 平台解析 ref 失败时舱壁化降级
- **WHEN** `kb_serve.service_key_ref` 指向的 env 在平台进程缺值
- **THEN** 该 env 名的回填被跳过并记录 warning，desired-state 响应正常返回其余 secrets

#### Scenario: agent 侧检索经下发的 key 认证成功
- **WHEN** agent 以物化的 http provider 配置启动，`.env` 含下发的 `FLEETENT_KB_SERVICE_KEY`，对绑定 KB 发起检索
- **THEN** `HttpKnowledgeProvider` 以 `Bearer <key>` + ingress principal 调 kb serve `/search` 并获得本租户结果

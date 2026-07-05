# kb-binding-provider-materialize — Tasks

> 每个实现 task 严格 TDD：先写测试（最窄命令见红）→ 实现（同命令见绿）。测试任务在对应实现任务之前。

## 1. auth_ref 解析 helper 提升

- [x] 1.1 测试：`_resolve_auth_ref` 提升为 platform 内共享 helper 后，`env:` / `file://` 两种形式解析行为不变、env 缺值抛 ValueError（unit，先红）
- [x] 1.2 实现：把 `kb_serve_client._resolve_auth_ref` 提升为 `platform/knowledge_base_management` 内可复用函数（如 `resolve_service_key_ref`），`KBServeClient` 改为调用它；跑同一测试见绿

## 2. 物化写入 http provider

- [x] 2.1 测试：`_knowledge_for_agent`（或其新签名）在"有绑定 + kb_serve 已配置"时返回 `provider: {type: http, url, auth_ref: env:FLEETENT_KB_SERVICE_KEY}`；"kb_serve 未配置"时保持缺省 local 且不抛错；"无绑定"时 knowledge 不启用（unit，mock `Settings().kb_serve` 与 `agent_kbs_store`，先红）
- [x] 2.2 实现：materialize 在绑定物化时按 D1/D2 写 provider 段（canonical env 名常量化，如 `KB_SERVICE_KEY_ENV = "FLEETENT_KB_SERVICE_KEY"`）；见绿
- [x] 2.3 测试：物化出的 agent.yaml 经 `agent_config` 加载校验通过（http provider 的 url/auth_ref 必填校验满足），且 `collect_env_var_names` 结果包含 `FLEETENT_KB_SERVICE_KEY`（unit，先红——若 2.2 已使其直接绿，确认测试确实覆盖新行为后可接受）
- [x] 2.4 实现/修正：如 2.3 暴露 scaffold 排除逻辑（`_knowledge_env_var_names`）误伤 canonical env 名，修正之；见绿

## 3. desired-state secret 回填

- [x] 3.1 测试：`_agent_secrets` 对 referenced 的 `FLEETENT_KB_SERVICE_KEY` 回填平台解析值；per-agent 显式 secret 优先；kb_serve 未配置时不回填；平台 ref 解析失败时跳过回填、记 warning、不抛（unit，mock `Settings().kb_serve` / `secret_store` / helper，先红）
- [x] 3.2 实现：`node_desired_state_api._agent_secrets` 增加 KB key 回填段（复刻 provider_key_for_env 模式 + try/except 舱壁）；见绿

## 4. 集成验证（integration 层）

- [x] 4.1 测试：端到端物化链路——建 agent + 绑定 + 配置 kb_serve → materialize → 断言 agent home 的 agent.yaml 含 http provider、`.env` scaffold 含 `FLEETENT_KB_SERVICE_KEY` 空槽；desired-state 响应 secrets 含回填值（integration，`tmp_path` + monkeypatch FLEETENT_HOME，先红）
- [x] 4.2 实现/修缝：打通 4.1 暴露的接线缝隙（如有）；见绿
- [x] 4.3 测试 + 验证：无 platform 环境下 `fleetent agent run` 基线不回归——手工 agent.yaml（local 与 http 两种 provider）加载与运行不受影响（跑既有相关 unit/integration 确认无新增失败）

## 5. 文档与收尾

- [ ] 5.1 docs：`docs/capabilities/knowledge-base.md` 补"平台绑定使用 KB 的部署前提"一段（kb_serve.url 必须 agent 网络可达、禁 loopback（单机除外）、embedding 为 KB 服务启动硬前提）；人工确认后提交
- [ ] 5.2 change/PR 收尾：`make test-pr` + `make test-integration-ci` 全绿（无新增失败）

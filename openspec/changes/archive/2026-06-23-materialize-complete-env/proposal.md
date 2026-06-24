## Why

agent 物化出的 `.env` 现在是个**不完整、不透明、双标准**的文件，难读难维护：

- **双标准**：node 侧用 `agent_init.referenced_env_names`（手枚举，漏 `embedding`/`rerank`/`telegram`/各种 `*_env`），平台侧用 `materialize._env_var_names`（`flatten` 全字段）。同一个 agent 在两条路径下 scaffold 出的 `.env` 不一致。
- **不透明**：node scaffold 只写部分 env 名占位（空值）+ TUI token；真实密钥既不在 `.env` 也不一定在注入的 `secrets` map（`_agent_secrets` 只含 vault inject 槽位），其余靠**宿主进程 env 静默兜底**——dev 里"碰巧能跑"，干净 prod 宿主上会静默缺失。看文件无法判断"这个 agent 要哪些 env、值从哪来、缺没缺"。
- **二元性**：managed 经"进程 env 注入"、standalone 经"`.env` 真值"，agent 侧要兼容两种来源，心智负担与代码分支都翻倍。

目标：物化时把每个 agent 的 `.env` 写成**完整、透明、自文档的单一真相**——列出 agent.yaml 引用到的全部 `*_env` 名 + 真实值，managed 与 standalone 统一为"agent 只读一个完整 `.env`"。

## What Changes

- **env-only（核心）**：node 把 desired-state 收到的真实密钥值**写进 `<home>/agents/<name>/.env`（`0600`）**，**删除 spawn 时的进程 env 注入**（`Popen(env=secrets)`）。agent 仍经 `load_dotenv` 读取，零改动。**BREAKING（运行时契约）**：secret 由"仅存于 node 内存 + 子进程 env（临时）"改为"agent home `.env` 明文落盘（持久，`0600`）"。
- **统一 env 名收集器**：node 与平台共用一个 `flatten` 口径（`*_env` 全字段），废弃 `agent_init.referenced_env_names` 的手枚举。`.env` 永远列出**全部**被引用的 `*_env` 名。
- **生命周期擦除**：agent `disable` / `unpin` / 删除时，node SHALL 擦除其 home 的 `.env`（不留停用 agent 的明文密钥）。
- **暴露面加固**：diagnostics 导出与备份 SHALL 排除 agent home 的 `.env`；日志 redaction 兜底覆盖 `.env` 形态的值。
- **platform-down 韧性顺带改善**：`.env` 持久化后，platform 短时不可达时 agent 可从盘上 `.env` 重启（不再受"缺 secret 不强启"限制）。
- **不变**：secret 仍经 `GET /nodes/{id}/desired-state` 的独立 `secrets` 字段下发（现状）；desired-state 磁盘缓存仍 strip secret（缓存 ≠ `.env`）；`config`/`agent.yaml` 本轮不动（已是 `exclude_defaults=False` 全字段 dump）。

## Capabilities

### New Capabilities
<!-- 无新增 capability -->

### Modified Capabilities
- `node-secret-injection`: 把"注入子进程 env、secret 不落盘"改为"写 agent `.env`（`0600`）、env-only"；磁盘暴露/降级要求相应更新（缓存仍 strip，但 `.env` 持久化承担 platform-down 韧性 + 停用即擦）。
- `node-supervisor`: 物化 `.env` 由"仅 TUI token + 部分名占位、真实 secret 不落"改为"统一 flatten 口径列全部 `*_env` 名 + 写入真实值 + `0600`"；新增 disable/unpin/删除时擦除 `.env`。
- `diagnostics-redaction-export-hardening`: 显式把 agent home 的 `.env` 纳入导出/备份排除与 redaction 范围（B 后 `.env` 含明文 secret）。

## Impact

- **owning packages**：`node/`（`reconcile.py` 写 `.env`、生命周期擦除；删 `backend.spawn` 的 secret 注入）、`runtime/`（`agent_init` env 收集器统一为 flatten；`agent_app` 不再依赖注入 env、纯 `.env` 读取）、`platform/agent_lifecycle/materialize.py`（`_seed_env`/`_env_var_names` 收敛为唯一口径，node 复用）、`observability/`（diagnostics 排除 `.env`）。
- **public API surface**：`runtime/agent_init` 暴露统一的 env-name 收集器（取代 `referenced_env_names`）；`ensure_env_scaffold` 演进为"写完整 `.env`（名+值）"。node → runtime / node → platform-secret 下发均为既有合法方向。
- **owned tables**：无（仅文件落盘行为变化；secret 权威仍在 vault `secret_store`）。
- **config namespace**：无新增；沿用现有 `*_env` 字段与 `credential_slots`。
- **cross-module dependencies**：不新增反向依赖；node 仍经 desired-state HTTP 取 secret（不直连 vault）。
- **migration / shim plan**：行为迁移而非 schema 迁移。存量在跑 agent：下一轮 reconcile 重写其 `.env`（含真值）→ 下次重启即走 env-only；过渡期可短暂保留注入以防回滚（设计中定）。`ensure_env_scaffold` 的旧"仅占位"语义被新语义取代，调用方同步。
- **安全权衡（写入 design）**：secret 由进程内存（临时）→ 磁盘明文（`0600`，持久）。git 不受影响（运行时 home 在 gitignore / prod 不入库）；`/proc/<pid>/environ` 本就暴露进程 env，故相对主机级攻击面的安全损失有限；prod 要求 `.env` `0600` + home `0700` + platform↔node TLS。收益：统一 managed/standalone、删注入二元性、抗 platform 短时不可用更强。
- **范围外**：`agent.yaml`/config 的可读性重构；secret 轮换的端到端编排（本轮只保证"重物化即覆盖 `.env`"）；KB 等独立组件的 env。

## Context

agent 的 `.env` 由两条物化路径写出，且现在故意"不完整"：

- **node 侧**（`node/reconcile.py::_write_home` → `runtime/agent_init.ensure_env_scaffold`，刚由 change `node-scaffold-agent-env` 引入）：只写 `FLEETENT_TUI_TOKEN` + `referenced_env_names`（**手枚举**：model targets `api_key_env` + mcp + slack；漏 `embedding`/`rerank`/`telegram`/各 `*_env`）的**空占位**。真实 secret 不落 `.env`。
- **平台侧**（`platform/agent_lifecycle/materialize.py::write_home` → `_seed_env`，`_env_var_names` 用 `flatten` 抓全部 `*_env`）：会从 vault / provider / shared 回填真值，名口径更全。

真实 secret 当前经 `GET /nodes/{id}/desired-state` 的独立 `secrets` 字段（`_agent_secrets`，仅 vault `inject` 槽位）下发到 node，node 经 `backend.spawn(env=secrets)` **注入进程环境**，不写盘（`node-secret-injection` 现有契约：「secret 永不落盘」）。agent 经 `load_dotenv(override=False)` 读取，注入的 env 不被空占位覆盖。

后果：`.env` 看不出 agent 要哪些 env、值从哪来、缺没缺；dev 里真实 key 常靠**宿主进程 env 静默兜底**（继承自启动 shell），干净 prod 宿主上会静默缺失。managed（注入）与 standalone（`.env` 真值）两种来源使 agent 侧存在二元性。

约束：node SHALL NOT 直连 vault（vault 在 platform 主机；node 只能经 desired-state HTTP 拿解密值——现状）。node → runtime、node → platform-secret-下发 均为既有合法方向；不得新增 agent→platform 反向依赖。

## Goals / Non-Goals

**Goals:**
- `.env` 成为**完整、透明、自文档**的单一真相：列出 `agent.yaml` 引用到的全部 `*_env` 名 + 真实值。
- **env-only**：secret 唯一落地点是 `.env`（`0600`），删除进程 env 注入；统一 managed/standalone 为"agent 只读一个完整 `.env`"。
- 单一 env-name 收集口径（`flatten`），node 与平台共用。
- 配套：停用擦除 + diagnostics/备份排除 + redaction 兜底。

**Non-Goals:**
- 不动 `agent.yaml`/config（已是 `exclude_defaults=False` 全字段 dump）。
- 不做 secret 轮换的端到端编排（本轮只保证"重物化即覆盖 `.env`"）。
- 不改 desired-state 仍以独立 `secrets` 字段下发、缓存仍 strip secret 这两条（保留）。
- 不动 KB 等独立组件的 env。

## Decisions

### D1 — env-only：`.env`（0600）是 secret 唯一落地点，删注入

node 收到 desired-state.`secrets` 后写入 `<home>/agents/<name>/.env`（`0600`），不再 `backend.spawn(env=secrets)`。agent 零改动（`load_dotenv` 已覆盖）。
**为何**：消除"注入 vs 文件"二元性；managed/standalone 同一模型；`.env` 自文档完整；`.env` 持久化使 platform 短时不可用时 agent 可从盘重启。
**取舍**：secret 由进程内存（临时）→ 磁盘明文（`0600`，持久）。见「Risks」。
**Alt（弃）**：双写（注入 + `.env`）——更保守但保留二元性、违背"单一真相"，仅作过渡期回滚手段（D5）。

### D2 — 单一 env-name 收集器：flatten 全字段

把 `materialize._env_var_names` 的 `flatten`（抓所有非空 `*_env`）提为共享 public 函数，`node`（取代 `agent_init.referenced_env_names`）与平台 `_seed_env` 共用。`agent_init.referenced_env_names` 废弃 / 改为薄 re-export。
**为何**：根除两套口径漂移；`.env` 永远列全。
**Alt（弃）**：在手枚举里补 `embedding`/`rerank`/`telegram`——治标，下次加字段又漏。

### D3 — 值来源：managed 用下发 secrets，standalone 用 operator 值；缺值写空占位 + 记录

每个 `*_env` 名：managed 取本轮 desired-state.`secrets` 的值；standalone 取既有 `.env` / operator 值；都无 → 写空占位（仍可见可补）并 log "referenced-but-unset"。
**为何**：透明（缺什么一眼看到），不静默靠宿主 env 兜底。
**注**：`_agent_secrets` 现仅含 vault `inject` 槽位——本轮沿用其口径（哪些进 `secrets` 由凭据槽位决定），不扩大 secret 暴露面；"完整"指**名完整 + 凡下发即落值**，不是"凭空补值"。

### D4 — 生命周期：停用即擦 `.env`

agent `unpin`/`disable`/删除被停进程后，擦除其 home `.env`。舱壁化（失败只 log）。
**为何**：不为停用 agent 在盘上留明文密钥。

### D5 — 迁移：reconcile 重写 + 过渡期可双写回滚

存量在跑 agent：下一轮 reconcile 重写其 `.env`（含真值），下次重启走 env-only（运行中进程的旧注入 env 仍有效，不强杀）。实现可用一个内部开关短期保留"注入 + 写盘"双写以便回滚，灰度确认后删注入。
**Alt（弃）**：一刀切删注入——回滚成本高。

### D6 — 暴露面（与本 change 一起做）

diagnostics 导出 / 备份排除 `<home>/agents/*/.env`（复用既有 secret 文件 / SQLite 排除机制）；redaction 兜底覆盖 `.env` 形态 `KEY=value`。
**为何**：`.env` 一旦含明文 secret，导出/备份不排除就等于上线即漏。

## Risks / Trade-offs

- **[明文 secret 持久落盘]** → `.env` `0600` + home `0700`；git 不受影响（运行时 home 在 gitignore / prod 不入库）；`/proc/<pid>/environ` 本就对 root/同用户暴露进程 env，故相对主机级攻击面，"0600 文件 vs 进程 env"安全损失有限。prod 要求 `.env`/home 权限 + platform↔node TLS（部署前提，写文档/可加启动校验）。
- **[轮换后 `.env` 陈旧]** → 权威仍是 vault；重物化（下一轮 reconcile 收到新 secrets）覆盖 `.env`。本轮不做主动轮换推送，但保证"重物化即覆盖"。
- **[擦除时序竞争]** → 擦除在停进程之后；舱壁化，失败只 log 不影响其它 agent。
- **[过渡期双写期间值不一致]** → D5 双写以 `.env` 为准；灰度后删注入即收敛。
- **[diagnostics 遗漏新路径]** → D6 复用递归全树排除 + 加针对 `agents/*/.env` 的用例守护。

## Migration Plan

1. 上线后下一轮 reconcile：node 为每个期望 agent 重写完整 `.env`（名全 + 真值 + `0600`）。
2. 过渡期（可选开关）：注入 + 写盘双写；观察无回归后关闭注入（D5）。
3. 运行中老进程不强杀，自然重启即走 env-only。
4. 回滚：重新打开注入开关 / 恢复 `ensure_env_scaffold` 旧"仅占位"语义即可；盘上 `.env` 残留由 `0600` + 停用擦除兜底。
5. 部署校验：检查 agent home `.env`/目录权限；多机 prod 校验 platform↔node TLS。

## Open Questions

- D5 的双写过渡开关是否值得做，还是直接 env-only（取决于现网是否已有依赖注入 env 的消费者）——倾向直接 env-only，若 apply 时发现有隐式依赖再加开关。
- 停用擦除是否也擦 `agent.yaml`/整个 home？本轮只擦 `.env`（最小、安全相关）；整 home GC 归 `node-supervisor` 既有"停掉不再期望 agent"范畴，不在本 change 扩。

## Context

node 的 reconcile（`src/fleetent/node/reconcile.py`）把 platform 下发的期望态调谐成本地真实 agent 进程。materialize 一步由 `_write_home(agent_name, config)` 完成，它当前只做一件事：把 desired `config` 序列化成 `<home>/agents/<name>/agent.yaml`。

agent 进程（`fleetent agent run`）boot 时 `load_dotenv(<home>/.env, override=False)` 读取 `FLEETENT_TUI_TOKEN`，并以它校验入站 `/chat` 的 Bearer（`runtime/agent_app.py::_validate_tui_token`）。managed 模式下，forwarder（`node/forwarder.py::_agent_tui_token`）与 IM-edge（`node/im_edge.py::_agent_tui_token`）都读同一个 `<home>/.env` 取该 token 注入 loopback `/chat`。

`.env`/token 的生成逻辑已存在于 agent runtime 侧：`runtime/agent_init.py::scaffold_agent_home`（即 `fleetent agent init`）在 home 无 `.env` 时生成 `FLEETENT_TUI_TOKEN=ma-<token_hex(32)>` 并保留已存在的 `.env`。但 node reconcile 从不调用它（node 的 `agent.yaml` 来自 desired config，不是 init 模板），于是 materialize 出的 home 永远缺 `.env` → forwarder 取不到 token → 503。

约束：node SHALL NOT `import fleetent.platform.*`；node → agent runtime（`fleetent.runtime.*`）是契约允许的单向依赖（node 拉起/读取 agent）。

## Goals / Non-Goals

**Goals:**
- materialize agent home 时幂等地确保 `.env` 含有效 `FLEETENT_TUI_TOKEN`，已存在的不动。
- token 生成逻辑单一来源，node 与 `fleetent agent init` 共用，不重复实现。
- 新 pin 的 managed agent 开箱即可经 forwarder/IM-edge 对话。

**Non-Goals:**
- 不改 forwarder/IM-edge 的 `_agent_tui_token` 读取逻辑（仍读 `.env`）。
- 不把真实 secret（model key、IM token）写进 `.env`——它们继续走 node secret 注入的进程环境。
- 不轮换已有 token，不做 token 生命周期管理（撤销/过期）。
- 不修我手工 `pkill` 子进程后观察到的 reconcile loop 停摆问题（独立、范围外）。

## Decisions

### 决策 1：在 `runtime/agent_init.py` 抽出可复用的 `.env` scaffold 入口，node 调用它

把 `scaffold_agent_home` 里写 `.env` 的那段抽成独立 public 函数，签名近似：

```python
def ensure_env_scaffold(home_dir: Path, *, referenced_env_names: Iterable[str] = ()) -> None:
    """Idempotently ensure <home>/.env exists with a FLEETENT_TUI_TOKEN.
    Existing .env is preserved as-is (no overwrite, no token rotation)."""
```

- 幂等口径取「`.env` 不存在 **或** 缺 `FLEETENT_TUI_TOKEN`」才写；已含则原样保留。比 `scaffold_agent_home` 现有的「文件存在即整体跳过」更稳健（覆盖手工删 token 但留文件的边角情形），并让 `scaffold_agent_home` 复用同一函数、行为对齐。
- `scaffold_agent_home` 改为调用 `ensure_env_scaffold(home_dir, referenced_env_names=_referenced_env_names(agent))`，消除重复。

**Why over alternatives**：
- *node 内联自己写 token*：会出现两处 token 生成逻辑，且 `ma-<hex>` 形态/长度要手动对齐，违反单一来源。
- *node 直接调 `scaffold_agent_home`*：它会用 **模板** 覆写 `agent.yaml`，破坏 node 从 desired config materialize 的 `agent.yaml`，不可接受。
- 故抽出仅管 `.env` 的细粒度入口最干净。

### 决策 2：在 `_write_home` 内、写完 `agent.yaml` 后调用 scaffold

reconcile 已有的两个 spawn 路径（缺失拉起 line 49、config 漂移重拉 line 64）都经 `_write_home`，在此处统一补 `.env` 最省、不漏路径。referenced_env_names 可由 desired `config` dict 解析（解析成 `AgentFile` 后复用 `_referenced_env_names`），或最小化只保证 TUI_TOKEN——实现时按 spec「仅 token + 引用变量名占位空值」取前者，保持与 `agent init` 产物一致。

### 决策 3：保留 forwarder/IM-edge 的 503 兜底

`_agent_tui_token` 的 `has no env scaffold` / `no TUI token` 错误分支保留——它现在是「scaffold 尚未跑到（如 agent 刚 pin、reconcile 未到周期）」的诚实瞬态信号，而非永久死局。不改其行为。

## Risks / Trade-offs

- **[已在跑 agent 被 config 漂移重拉时，`.env` 已存在]** → `ensure_env_scaffold` 幂等保留既有 token，agent 重 boot 后 token 不变，forwarder 缓存的 token 仍有效，无 401。
- **[node 与 agent 进程对 `.env` 的读写竞争]** → reconcile 在 spawn agent **之前** 于 `_write_home` 内写 `.env`（顺序：写 agent.yaml → ensure .env → spawn），agent boot 时 `.env` 已就位；同一 home 的 `.env` 只由 node reconcile 串行写，不并发。
- **[referenced_env_names 解析 desired config 失败]** → scaffold 至少写 `FLEETENT_TUI_TOKEN`；占位变量名缺失不影响 forwarder 取 token（占位值本就为空、靠 secret 注入填充）。解析异常需 log 不吞。

## Migration Plan

- 纯增量、无 schema/迁移。
- 已存在 `.env` 的 home（如手工搭过的 demobot）完全兼容：scaffold 保留其 token，行为不变。
- 上线后下一轮 reconcile 自动为存量缺 `.env` 的 managed agent 补 token，无需运维介入。
- 回滚：恢复 `_write_home` 旧实现即可（移除 scaffold 调用）；已生成的 `.env` 残留无害。

## Open Questions

- 无阻塞性未决项。`ensure_env_scaffold` 的「缺 token 即补」幂等口径是否要回灌覆盖 `scaffold_agent_home` 的旧「文件存在即跳过」语义——倾向统一为前者（更稳），实现时一并改并加测试。

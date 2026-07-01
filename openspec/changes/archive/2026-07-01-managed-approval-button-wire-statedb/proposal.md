# 变更:托管模式下审批按钮可用(node 进程接通 state_db 或转发给 agent)

母文档:`docs/records/aaa-8204-recovery.md`(问题 ②)

## 为什么

Slack 审批按钮(✅批准 / ❌拒绝 / ✅始终允许)在托管模式下点了即崩、run 不 resume:

- 按钮点击由 **node 进程**就地处理:`slack.py:559 → handle_approval_action(...)`。
- `handle_approval_action`(`slack.py:222`)调 `approval_store.get_approval()` → `approval_store.database()`(`governance/approval_store.py:25-31`)。
- 但 `approval_store.set_state_db()` **只在 agent 进程 boot 接线**(`runtime/agent_app.py:391`),**node 进程从没接过** → `_state_db is None` → 抛 `RuntimeError: approval_store: state_db not initialized`。
- `await ack()`(`:209`)在抛错前已发,Slack 看着像"点到了",实则 handler 抛、`chat_update`/resume 都没执行,buttons 残留,run 永卡 pending。

## 改动(二选一,推荐 A)

**方案 A(推荐):按钮点击 → 合成一条 `approve/reject <id>` 指令,走与文字命令同一条 `/im/route` 转发链交给 agent 进程处理。**
- agent 进程里 `approval_store`/`session_mgr`/normalizer resume 全都接好,天然可用;node 不必复刻 agent 运行时。
- 复用变更 ③ 修好的命令路径(及其 session-from-row 解析),一处修两处受益。
- node 已有 `self._agent_db_paths[agent_name]` 与 `agent_name` 透传,具备落地条件。

**方案 B(备选):给 node 的 slack app builder 注入 `state_db_resolver(agent_name)`,`handle_approval_action` resolve 后 `set_state_db` 再 `get_approval`/resume。**
- 缺点:还要一并接 `session_mgr`(per-agent `SESSIONS_DIR` 同样是未接线的全局),改面更大;且 `im_gateway` 不可 import `node`(须用注入回调),约束更紧。

## 模块边界影响

- **owning package**:`node/`(`im_edge.py`)+ `im_gateway/`(edge,经注入)。
- **关键约束**:`im_gateway` MUST NOT import `node`/`platform`;node 经回调/注入向 edge 提供能力(沿用既有 resolver/dispatcher 注入范式)。
- **public API surface**:`handle_approval_action` 可能新增一个可选注入参数(转发器或 state_db resolver);默认不破坏 standalone(agent 自托管)路径。
- **owned tables**:无。
- **config namespace**:无。
- **migration / shim**:无。

## 分工

- **本地(你)**:实现(推荐 A)+ 单测(覆盖按钮 → 转发 → resume;standalone 路径回归)。
- **服务器(我)**:真实 Slack 点三种按钮验收;清理历史卡住的 pending(00b0691a / f758a7a7 / 8eafa231 / 305c9a87,走平台 API)。

## 验收

托管模式下点 ✅批准 / ❌拒绝 / ✅始终允许,均能 resolve + run resume + 消息送达,无 `state_db not initialized`;standalone(`agent run` 自托管)审批路径不回归。

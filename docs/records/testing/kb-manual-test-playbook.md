# KB 手动测试指引（dev 栈）

> 适用：`make platform` / `make node` / `make kb-serve` / `make kb-worker` 四服务已起的本机 dev 栈。
> 目标：从用户视角验证 2026-07-05 落地的三条链路——绑定物化 http provider、平台上传入库、admin UI 管理面。
> 原则：只看用户可见面（UI / CLI / 对话 / 日志），不改代码。

---

## 0. 起点自检（2 分钟，全过再往下）

| # | 动作 | 期望 |
|---|------|------|
| 0.1 | `curl -s http://127.0.0.1:8768/healthz` | `{"status":"ok","tenant_id":""}`（host 多租户模式） |
| 0.2 | 浏览器开 `http://127.0.0.1:8765`，admin 登录 | 能进控制台（密码是首次 bootstrap 打印的临时密码，忘了可重置） |
| 0.3 | `curl -s http://127.0.0.1:11434/api/tags \| head -c 200` | ollama 在跑，且列表里有 `.fleetent-dev/kb-service.yaml` `embedding.model` 写的那个模型 |
| 0.4 | 看 kb-worker 终端 | 无报错、周期性轮询日志 |

> ⚠️ 0.3 是实测最大坑：scaffold 默认的 `bge-small` **不是 ollama 真实 tag**，必须在**首次 ingest 之前**把 `embedding.model`/`dimensions` 改成本机实际有的（如 `bge-m3:latest`/1024）。晚了改 = 已入库 KB 的 embedding 身份还是旧模型，检索被 mismatch 守卫拦（表现为 playground 500），要跑 `fleetent kb reindex` 迁移。
> ⚠️ 顺序纪律：先 `make dev-reset`（或 dev-bootstrap）**再**起四个服务。Makefile 已加 `dev-kb-key` 前置防空 key，但配置 scaffold 本身仍依赖 bootstrap 先行。

---

## 1. KB 生命周期（UI 为主）

1. UI → Knowledge Base 页 → **创建** KB `demo`（或 `make kb-create KB=demo`）。
2. 列表出现 `demo`；**编辑描述**后刷新仍在。
3. 再建一个 `scratch` 留给后面删除测试。

✅ 通过标准：创建/编辑/列表往返一致；CLI 建的库 UI 能看到（说明走的同一个 kb-serve）。

---

## 2. 上传 → 异步入库（change 2 主链路）

准备 2-3 个内容你熟悉的测试文件（md/txt/pdf，其中一个 >1MB 更好）。

1. UI → `demo` 详情 → **上传文档**。期望：成功提示带 **job id**（"已入队"字样）。
2. **切到 kb-worker 终端**：几秒内应出现消费该 job 的日志（切块/embedding）。
3. 回 UI 刷新文档列表：文档出现，chunk 数 > 0。
4. 点开 **chunk 预览**：分块内容和 section 上下文合理（没有乱码、没有整篇挤在一个 chunk）。
5. **负例**：上传一个超过 50MB 的文件 → 期望 UI 明确报错（413），不误报成功。
6. **文件落点抽查**：`ls .fleetent-dev/tenants/default/kb/uploads/demo/` → 有 uuid 前缀的暂存文件。
7. **向量落盘核查**（重要，job=done 不足为凭）：
   ```bash
   sqlite3 .fleetent-dev/tenants/default/kb/data/kb_vectors.db "SELECT count(*) FROM vector_items;"
   # 期望 > 0；文件不存在或 0 = 向量静默丢失（已知开放 bug：ingest 对 embedding 故障 fail-open）
   ```

✅ 通过标准：上传→worker 消费→列表出现→chunk 可读→**向量落盘**，全程不需要碰 CLI。
⚠️ 已知设计：上传后列表不会自动刷新（不做轮询），手动刷新是预期行为。
⚠️ 已知开放 bug（2026-07-06）：embedding 不可用时 ingest 照样报 done、文档看似导入成功，实为 keyword-only 残缺态——所以第 7 步必查。

---

## 3. Playground 检索质量

在 `demo` 详情的 Playground 里做三类查询：

| 查询类型 | 例子 | 期望 |
|---|---|---|
| 精确事实 | 文档里明确写过的数字/名词 | 命中对应 chunk，得分靠前 |
| 模糊改述 | 换个说法问同一件事 | 仍能命中（考验 embedding 质量） |
| 无关问题 | 文档完全没有的主题 | 低分或空结果，**不硬凑** |

✅ 通过标准：三类行为符合预期；来源文档名、得分展示正常。
⚠️ playground 直接 500 的两种根因（实测均遇到）：embedding 模型名在 ollama 不存在（404）→ 改 kb-service.yaml + 重启 serve/worker；换过 embedding 模型 → identity mismatch 守卫 → `fleetent kb reindex --config .fleetent-dev/kb-service.yaml --tenant default --kb demo --wait`（reindex 成功会同步迁移 KB 身份记录）。

---

## 4. 绑定 agent → 物化验证（change 1 关键观察点）

前提：平台里已有一个能正常对话的 managed agent。测试 agent 的建法与选型（实测教训）：
- **对话模型选小的非 thinking 模型**（如 `llama3.2:latest`）。thinking 模型（qwen3/deepseek-r1）有两个问题：生成极慢；重型生成独占 ollama 时，检索的查询向量化会排队超过 5s 预算 → **KB 上下文静默注入失败**，agent 表现为"用训练知识瞎答"。
- **`allowed_tools` 不要留空列表**——空列表 = allow-all，小模型会拿问题去乱调计算器等内置工具（触发循环护栏）。纯 QA 测试 agent 给一个匹配不到的显式模式（如 `["__no_tools__"]`）关掉工具面。
- embedding 路由与 KB 服务侧同一模型（bge-m3/1024），注册表 model 建好后 routes 用 `{"model_id": ...}` 引用。

1. UI → `demo` 详情 → Agents 区 → **绑定**一个 agent。
2. 等 node reconcile（看 node 终端日志，或重启该 agent 加速）。
3. **物化产物检查**（这是 change 1 的验收核心）：
   ```bash
   grep -A10 "knowledge" .fleetent-dev/tenants/default/agents/<name>/agent.yaml
   # 期望: enabled: true / bindings 含 demo /
   #       provider: type: http, url: http://127.0.0.1:8768/search（注意必须带 /search 端点后缀）,
   #       auth_ref: env:FLEETENT_KB_SERVICE_KEY
   grep -c "FLEETENT_KB_SERVICE_KEY=" .fleetent-dev/tenants/default/agents/<name>/.env
   # 期望: 1（且值 = cat .fleetent-dev/.dev_kb_service_key）
   ```
4. **解绑**再看一次 agent.yaml → knowledge 段应回到不启用。测完重新绑上。

✅ 通过标准：绑定/解绑纯 UI 操作即可让 agent 配置收敛，全程不手编 agent.yaml。
⚠️ 若 provider 还是 local：确认 platform 终端是经 `make platform` 起的（`KB_SERVE__*` 靠 make 注入，裸起 uvicorn 没有）。

---

## 5. Agent 对话验证端到端 recall（最终价值）

对绑定了 `demo` 的 agent 发起对话（UI chat 或 TUI）：

1. 问**文档里才有**的内容 → 回答应引用到文档知识（对得上第 3 步 playground 能搜到的东西）。
2. 问无关问题 → 回答不应被无关 KB 内容污染。
3. **负例**：拿一个**未绑定**的 agent 问同样的问题 → 不应答出文档内容。

✅ 通过标准：绑定的 agent 答得出、未绑定的答不出——KB 权限边界成立。
⚠️ agent 侧检索走 kb-serve HTTP（可在 kb-serve 终端看到对话触发的 `/search` 请求日志——这是确认走了 http provider 而非本地直读的直接证据）。
⚠️ **判卷前先看 agent 日志**（`<agent home>/data/logs/<date>.log`）：出现 `ltc_retrieval_timeout path=knowledge` = 检索超时被静默丢弃，此时"答非文档内容"不是 recall 失败而是资源竞争（见第 4 节模型选型）；出现 `http_knowledge_provider_failed` = provider 接线问题（看 url/key）。
⚠️ 出好题的技巧：**陷阱题**（文档纠正了大众错误认知的点）区分度最高——模型训练知识答不对、只有真读了 KB 才能答对；纯事实题小模型可能碰巧靠训练数据蒙对。

---

## 6. 删除与收尾一致性

1. UI 删除 `demo` 里的一个文档 → playground 再搜其内容 → 不再命中。
2. 删除 `scratch` KB（无绑定，应可归档）；尝试删除**有绑定**的 `demo` → 应被拦截并列出绑定 agent。
3. UI → KB observation / 观测入口（若有暴露）与 `GET /admin/kb/demo/agents` 数据一致。

---

## 故障速查

| 症状 | 先看哪里 | 常见原因 |
|---|---|---|
| 上传后文档一直不出现 | kb-worker 终端 | embedding 连不上（ollama 没跑/模型名不对）；job 失败会留在日志里 |
| 文档"导入成功"但向量为 0 | `kb_vectors.db` 行数（§2 第 7 步） | 已知开放 bug：ingest 对 embedding 故障 fail-open，job 照报 done |
| UI KB 页全部报错 | platform 终端 | `KB_SERVE__*` 未注入/为空 → 503（"key cannot be resolved" = 服务先于 bootstrap 启动，重启即可）；key 不匹配 → 401 |
| playground 500 | kb-serve 终端 traceback | embedding 模型名不存在（404）；或换模型后 identity mismatch → reindex |
| 绑定后 agent.yaml 没变化 | node 终端 | reconcile 未触发（重启 agent）；platform 未配 kb_serve 则物化保持 local（设计如此）；改了物化代码要先重启 platform |
| agent 循环重启（node 每 10s 一条 spawn） | node 终端 traceback | 子进程继承了空 env key 压住 .env 好值（dev-kb-key 前置已防；症状再现先查 node 进程 env） |
| agent 对话不引用文档 | agent 日志 + kb-serve 终端 | `ltc_retrieval_timeout` = 检索超时（ollama 被生成独占，换小模型）；无 `/search` 请求 = provider 没接上（url 须带 /search）；有请求但空结果 = 回到第 3 步 |
| agent 回复"重复调用同一个工具…" | — | 小模型乱调内置工具触发循环护栏 → `allowed_tools` 给显式不匹配模式关掉工具面（空列表=全放开） |
| 检索质量差 | — | embedding 模型与建库时不一致 → reindex；或回到 playground 复核 |

---

## 结果记录建议

每节记 ✅/❌ + 一句备注即可；❌ 的项把对应终端日志片段一起存下来。测完把结论回给 Claude 会话，能直接定位到是哪条 change 的问题。

# 本地 managed 栈 runbook：从全新 home 到 admin UI 能 chat

把一个**全新 `FLEETENT_HOME`** 起成完整 managed 栈（platform + node + 一个能在 admin UI 对话的 agent）的最小步骤。基于 tenant-first 布局 + platform CLI（`fleetent platform …`）实测（2026-06-24）。

> 关键认知：**admin UI 的 chat 是 managed 路径**（platform → node forwarder → agent 进程）。它只对**经平台建并 pin 到 node 的 agent**生效。`fleetent agent init` 出来的是 standalone home（不进管理库），admin UI 看不到、聊不了。

## 前置

- `FLEETENT_MODEL_PRIMARY_API_KEY` 在当前 shell 环境（agent 对话要用；node spawn 的 agent 进程继承它）。
- 端口：platform 默认 **8765**；`make agent` 直跑单 agent 时默认 **8766**，避免和 platform 冲突。
- 所有 dev 数据落 gitignored 的 `.fleetent-dev/`（`make` 的 `DEV_TARGETS` 已统一 export `FLEETENT_HOME` / `DATABASE_URL` / `FLEETENT_SECRET_KEY` / `FORWARDER_HOST_OVERRIDE`）。

## 步骤

### 1. 初始化 home（控制面）

```bash
make dev-clean                       # 清掉旧 home（验证全新流程时用）
make dev-bootstrap                   # 生成 dev secret key + alembic upgrade head + seed 内置 admin
```

产物：`.fleetent-dev/{.dev_secret_key, .env, management.db, node/.env, tenants/default/kb/{kb-service.yaml,.env}}`
（management.db 独占根，tenant-first 决策 B）。seed 出的内置 admin：`admin` / `admin`（首登 must_reset）。

### 2. 起 platform

```bash
make platform                        # 前台长驻，建议单开终端；后台跑则重定向日志
```

就绪判据：`curl -sf http://127.0.0.1:8765/admin/ui` 返回 200。

### 3. 注册 node

```bash
make node-provision                  # 写 .fleetent-dev/node/.env + 注册 node 到平台
```

### 4. 改 admin 初始密码（清 must_reset）

```bash
TOK=$(curl -s -X POST http://127.0.0.1:8765/admin/login \
  -H 'content-type: application/json' -d '{"email":"admin","password":"admin"}' \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
curl -s -X POST http://127.0.0.1:8765/admin/change-password \
  -H "Authorization: Session $TOK" -H 'content-type: application/json' \
  -d '{"new_password":"fleetent-dev"}'
```

之后登录用 `admin` / `fleetent-dev`。

### 5. 建一个 managed agent（顺序：建 → pin → enable）

> 用 admin Session token。建 agent 后默认 **disabled**，且 **enable 要求先 pin**——顺序不能错。

```bash
TOK=$(curl -s -X POST http://127.0.0.1:8765/admin/login \
  -H 'content-type: application/json' -d '{"email":"admin","password":"fleetent-dev"}' \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")

# 5a. 建 agent —— model_overrides 只配 chat 路由（default + memory_extraction）
#     ⚠️ 不要配 embedding/vision 路由：embedding provider 不吃 openai_chat protocol，
#        boot 会崩（ModelConfigError: embedding target uses unsupported protocol 'openai_chat'）。
#        缺 embedding 路由会自动回落 deterministic（KB/向量质量降级，对话不受影响）。
cat > /tmp/create_chatbot.py <<'PY'
import json, urllib.request
BASE = "http://127.0.0.1:8765"; TOK = __import__("sys").argv[1]
def post(path, body):
    r = urllib.request.Request(BASE+path, data=json.dumps(body).encode(), method="POST")
    r.add_header("content-type","application/json"); r.add_header("Authorization","Session "+TOK)
    return urllib.request.urlopen(r).status
anthropic = {"provider":"anthropic","model":"claude-sonnet-4-6",
    "base_url":"https://api.anthropic.com/v1/","api_key_env":"FLEETENT_MODEL_PRIMARY_API_KEY",
    "protocol":"openai_chat","max_tokens":4096}
mo = {"routes": {"default":[anthropic], "memory_extraction":[anthropic]}}
print("create:", post("/admin/agents", {
    "name":"chatbot",
    "system_prompt":"You are chatbot, a friendly assistant. Answer concisely in the user's language.",
    "allowed_tools":["get_current_time","calculate","whoami"],
    "model_overrides":mo}))
PY
python3 /tmp/create_chatbot.py "$TOK"

# 5b. pin 到 node（agent_id 从管理库查）
AID=$(sqlite3 .fleetent-dev/management.db "select id from agents where name='chatbot';")
curl -s -X POST http://127.0.0.1:8765/admin/nodes/local-node/pin \
  -H "Authorization: Session $TOK" -H 'content-type: application/json' \
  -d "{\"agent_id\":$AID,\"pinned_by\":\"admin\"}"

# 5c. enable（已 pin 后才能 enable；否则 409 "agent not bound to a node"）
curl -s -X POST http://127.0.0.1:8765/admin/agents/chatbot/enable -H "Authorization: Session $TOK"
```

> 备选 pin：`fleetent platform node pin --agent-id <id> --node-id local-node`（CLI 直写管理库）。

### 6. 起 node（reconcile 物化 + 拉起 agent + forwarder）

```bash
make node                            # node 每 ~10s reconcile：拉 desired-state → 物化 agent home → spawn agent
```

node 会把 chatbot 物化到 `tenants/default/agents/chatbot/`（agent.yaml + .env + data/），并 spawn agent 进程（随机 loopback 口）+ 起 forwarder（8767）。等到 `pgrep -f "fleetent agent run chatbot"` 命中即 OK。

> agent 的 `FLEETENT_MODEL_PRIMARY_API_KEY`：node materialize 写的 `.env` 里该项为空占位（值在 vault 才会写实值），agent boot 时 `load_dotenv(override=False)` 不覆盖**从 node 进程继承**的真值——所以**起 node 的 shell 必须有 `FLEETENT_MODEL_PRIMARY_API_KEY`**。

### 7. 验证 + 使用

```bash
# 命令行验证完整链路（platform → forwarder → agent → Anthropic）
TOK=$(curl -s -X POST http://127.0.0.1:8765/admin/login -H 'content-type: application/json' \
  -d '{"email":"admin","password":"fleetent-dev"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
curl -sN -X POST http://127.0.0.1:8765/admin/agents/chatbot/chat \
  -H "Authorization: Session $TOK" -H 'content-type: application/json' \
  -d '{"message":"你好"}' --max-time 60
```

浏览器：**http://127.0.0.1:8765/admin/ui**（`admin` / `fleetent-dev`）→ chat 页面选 **chatbot** 对话。

## 停止

```bash
pkill -f "platform serve"; pkill -f "fleetent node start"; pkill -f "fleetent agent run"; pkill -f "fleetent kb worker"
```

## 踩坑速查

| 现象 | 原因 / 修法 |
|---|---|
| `make node-provision` 报 `'admin' is not a recognized command` | dev 脚本用了退役的 admin CLI 命名空间（已改走 `fleetent platform`，见 `scripts/dev_node_provision.py`） |
| admin UI 看不到 agent / 聊不了 | 该 agent 是 `agent init` 的 standalone home，不在管理库；必须经平台建 + pin + enable |
| enable 返回 409 `agent not bound to a node` | enable 前必须先 pin |
| agent boot 崩 `embedding target ... unsupported protocol 'openai_chat'` | 别给 embedding/vision 配 chat 路由；删掉它们，靠 deterministic 回落 |
| 对话 401 / 无 key | 起 node 的 shell 没有 `FLEETENT_MODEL_PRIMARY_API_KEY`（agent 继承不到） |
| 首次 admin 登录被拒改密 | 内置 admin `must_reset`，先 `POST /admin/change-password` |

## 目录结构（栈跑起来后）

见 [`docs/architecture/agent-home-layout.md`](../architecture/agent-home-layout.md)（tenant-first 完整树 + 每路径生成职责）。简版：

```
.fleetent-dev/
├── management.db            控制面权威（根）
├── node/.env                node 身份
└── tenants/default/
    ├── kb.db                租户级 KB（跨 agent 共享）
    └── agents/chatbot/
        ├── agent.yaml .env .fleetent.pid
        └── data/{agent_state.db, agent_memory.db, logs/}
```

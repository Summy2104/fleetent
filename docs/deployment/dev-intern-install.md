# dev-intern Agent 部署安装教程

按 **dev-intern 现网部署方式**复刻一个 standalone agent（不依赖 platform 控制面）。
现网形态：`fleetent v0.2.0`，systemd user service 跑在 `:8766`，`FLEETENT_HOME=~/.fleetent`，
经 `scripts/install-agent.sh` 安装。

> 约定：下文 `$U` = 运行用户，`$HOME` = 其家目录（现网是 `ec2-user` / `/home/ec2-user`）。
> agent home = `$FLEETENT_HOME/agents/dev-intern/`。

---

## 1. 系统依赖

| 依赖 | 用途 | 备注 |
|------|------|------|
| **uv** | 安装/运行 fleetent，提供 Python ≥3.12 | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| **Docker** | 沙箱代码执行（`features.code_execution: true`） | `$U` 须在 `docker` 组 |
| **Node ≥20 + npx** | stdio MCP（jira/confluence/bitbucket/google-drive/playwright/email/slack） | 现网 v24 |
| **Playwright chromium** | `common-web-capture` | `npx -y playwright install chromium` |

```bash
# PATH 需含 ~/.local/bin（uv tool 安装目标）
uv python find ">=3.12"     # 确认 uv 能提供 3.12（install-agent.sh 的前置检查）
```

## 2. 取代码 + 安装 fleetent（install-agent.sh 路径）

```bash
git clone <fleetent 仓库> ~/src/fleetent     # 或拷贝源码
cd ~/src/fleetent

# 方式 A：官方脚本（推荐，等价于现网做法）
scripts/install-agent.sh dev-intern
#   它依次做：uv python 检查 → `uv tool install --force --from . fleetent`
#            → 持久化 FLEETENT_HOME 到 shell rc → `fleetent agent init dev-intern`
#            → docker 预检 → 打印后续步骤

# 方式 B：手工等价
uv tool install --force --from . fleetent
export FLEETENT_HOME="$HOME/.fleetent"        # 建议写入 ~/.bashrc
fleetent agent init dev-intern                # 脚手架 agents/dev-intern/{agent.yaml,.env}
```

> PyPI 索引可能超时：若 `uv tool install` 卡在拉依赖，改用离线 `--find-links <wheels 目录>`，
> 或在联网机器构建 wheel 后拷贝。

## 3. 外部运行时（脚本不覆盖，需手动）

```bash
# 3.1 沙箱镜像（agent.yaml 的 sandbox.docker.image: fleetent-sandbox:0.1.0）
cd ~/src/fleetent && docker build -t fleetent-sandbox:0.1.0 docker/sandbox/

# 3.2 Playwright 浏览器；记下 chromium-<rev>（现网 chromium-1226）
npx -y playwright install chromium
ls ~/.cache/ms-playwright/
```

## 4. agent 配置

`fleetent agent init` 只生成最小模板。要复刻 dev-intern 的全部能力，用现网成品配置覆盖：

```
$FLEETENT_HOME/agents/dev-intern/
├── agent.yaml                                  # 模型 + skills + 10 个 MCP + im.slack + 沙箱 + 审批门
├── .env                                        # 全部密钥（见 §6）
├── skills/                                     # 业务 skill（与 repo skills/ 一致）
└── config/email/mcp_email_server/config.toml   # 邮箱 IMAP/SMTP
```

`agent.yaml` 关键段（照现网）：
- `models.targets`：primary(claude-sonnet-4-6) / vision / image-gen / embedding，均 `api_key_env: LLM_API_KEY`
- `skills_dir: skills`、`allowed_skills: []`（加载全部）
- `mcp_servers`：`jira` `confluence` `bitbucket`（npx，Atlassian）、`knowledge-bridge`(http,Bearer)、
  `armada`(http,Bearer)、`google-drive`(npx)、`playwright`(npx)、`email`(uvx)、
  `slack`(npx korotovsky，`SLACK_MCP_XOXP_TOKEN`)、`middle`(http，`headers: X-API-Key`)
- `im.slack`：`bot_token_env`/`app_token_env` + `access.allow_groups`/`allow_users`（改成新部署的频道/用户）
- `features.code_execution: true`、`sandbox.docker.image`、`sandbox.resources.network: allow_all`
- `permission_gate_enabled: true`、`approval.by_risk`（medium/high→requester）、
  `action_gate_medium_mode: sandbox`、`action_gate_high_mode: approval`

### ‼️ 改掉写死的本机路径（新机用户/家目录/chromium 版本不同时必改）
`agent.yaml` 内硬编码 `/home/ec2-user`：
- `playwright`：`--executable-path .../ms-playwright/chromium-1226/chrome-linux64/chrome`、`--output-dir`、`XDG_DATA_HOME`
- `email`：`command: .../.local/bin/uvx`（用 `which uvx` 修正）、`MCP_EMAIL_SERVER_CONFIG_PATH`

```bash
# 批量替换家目录（示例；chromium 版本另行核对）
sed -i "s#/home/ec2-user#$HOME#g" $FLEETENT_HOME/agents/dev-intern/agent.yaml
```

## 5. skills 同步

```bash
mkdir -p $FLEETENT_HOME/agents/dev-intern/skills
cp -r ~/src/fleetent/skills/* $FLEETENT_HOME/agents/dev-intern/skills/
# getting-started 是 builtin（src/fleetent/builtin_skills/），自动加载，无需拷
```

## 6. 密钥 `.env`（18 项；填好后 `chmod 600`）

```
LLM_API_KEY
SLACK_BOT_TOKEN  SLACK_APP_TOKEN  SLACK_USER_TOKEN
JIRA_ATLASSIAN_API_TOKEN  CONFLUENCE_ATLASSIAN_API_TOKEN  BITBUCKET_ATLASSIAN_API_TOKEN
KNOWLEDGE_BRIDGE_TOKEN  ARMADA_API_KEY  MIDDLE_MCP_API_KEY
GOOGLE_DRIVE_MCP_ACCESS_TOKEN  GOOGLE_DRIVE_MCP_REFRESH_TOKEN
GOOGLE_DRIVE_MCP_CLIENT_ID  GOOGLE_DRIVE_MCP_CLIENT_SECRET
GOOGLE_CLIENT_ID  GOOGLE_CLIENT_SECRET
FLEETENT_TUI_TOKEN
```
邮箱账号/密码在 `config/email/.../config.toml`（`[emails.incoming]`/`[emails.outgoing]`，Gmail IMAP 993 / SMTP 465）。

Slack token scope：bot 需 `channels:history` 且在目标频道；`SLACK_USER_TOKEN`(xoxp) 需
`channels:history,groups:history,search:read,users:read`（解锁 slack-digest 搜索模式）。

## 7. systemd user service + 开机自启

```bash
mkdir -p ~/.config/systemd/user
cat > ~/.config/systemd/user/fleetent-dev-intern.service <<EOF
[Unit]
Description=Fleetent dev-intern Agent
After=network.target
[Service]
Type=simple
Environment=FLEETENT_HOME=$HOME/.fleetent
ExecStart=$HOME/.local/bin/fleetent agent run dev-intern --port 8766
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal
[Install]
WantedBy=default.target
EOF

sudo loginctl enable-linger $USER          # 关键：无登录会话也开机自启
systemctl --user daemon-reload
systemctl --user enable --now fleetent-dev-intern
systemctl --user status fleetent-dev-intern
```

## 8. 验证

```bash
journalctl --user -u fleetent-dev-intern -f         # 启动 + MCP 注册
# 应用日志：~/.fleetent/agents/dev-intern/data/logs/<date>.log
```
- Slack 频道 @bot 发一句 → 有回复（IM 网关连通）。
- 逐 MCP 冒烟：armada(查业务线)、knowledge-bridge(列知识库；agent_id 固定 `bs-intern`)、
  middle(查中台账户)、email(看收件箱)、playwright(网页截图)、google-drive(列邮件模版)。

## 9. 升级 / 重新部署

```bash
cd ~/src/fleetent && git pull
uv tool install --force --from . fleetent
systemctl --user restart fleetent-dev-intern
```

---

## ‼️ 跨机部署必读坑

1. **Slack Socket Mode 单实例**：`SLACK_APP_TOKEN`(xapp) 走 Socket Mode，**同一 Slack App 在两台机同时跑会抢/重复投递消息**。新机要独立服务就**新建一个 Slack App**（独立 xoxb/xapp/xoxp）；否则视为替换、停掉旧机。
2. **内网 MCP 可达 + IP 白名单**：`armada`(ns-mcp.nsdigital.io)、`knowledge-bridge`(knowledge.antalpha.com)、`middle`(middle-mcp.antalpha-mo.com) 是内网/受 IP 白名单服务——新服务器必须能访问且 **IP 在其白名单内**，否则相关 skill 全挂。先 `curl` 测可达。
3. **Docker 必备**：缺 Docker → run_code / 画图 / 文件生成 / 办公文档类 skill 失效。
4. **沙箱出网**：现网 `network: allow_all`（沙箱可出公网），按安全策略决定是否收紧为 `none`。
5. **路径硬编码**：见 §4，新机用户/家目录/chromium 版本不同时务必改 `agent.yaml`。
6. **MCP 长连接**：内网 http MCP（knowledge-bridge/middle）若启动早于网络就绪，会话可能失效——表现为工具空报错；`systemctl --user restart` 重连即可。

## Context

`node/config.py::load_config()` 只从裸 env 读 `FLEETENT_NODE_*`,无文件约定。agent 侧早有范式:`agent_app.py:381-385`——
```python
env_path = home_dir / ".env"
if env_path.exists():
    from dotenv import load_dotenv
    load_dotenv(env_path, override=False)
```
node 照抄即可。`$FLEETENT_HOME/node/` 目录已存在(provider 的 `desired-state-cache.json`、reconcile 的 `applied-config-hashes.json` 都在那)。

## Goals / Non-Goals

**Goals:** node 从 `$FLEETENT_HOME/node/.env` 加载配置(进程 env 优先);加模板;修正 spec 过时措辞。

**Non-Goals:** 不改 `load_config()` 签名/返回;不把 `FLEETENT_HOME` 放进 node `.env`(鸡生蛋);不碰 desired-state/secret 注入;不动 install 脚本(node 部署当前不经 install 脚本)。

## Decisions

### D1:加载顺序——FLEETENT_HOME 先,再 node `.env`,再读 NODE_*

`load_config()` 内顺序:
1. `home_dir = FLEETENT_HOME(进程 env) or ~/.fleetent` —— 必须先于 `.env`,因为要用它定位文件。
2. `load_dotenv(home_dir / "node" / ".env", override=False)` —— 文件存在才加载;`override=False` 保证 systemd/shell/Docker 注入的进程 env 优先。
3. 读 `FLEETENT_NODE_PLATFORM_URL/ID/SERVICE_KEY/INTERVAL_SECONDS`(此时可能来自 `.env`)。

`FLEETENT_HOME` 故意不可经 node `.env` 设置(它是定位 `.env` 的前提),与全局 `FLEETENT_HOME` 语义一致。

### D2:override=False(进程 env 优先)

对齐 agent home `.env`:容器/systemd 经 `EnvironmentFile`/`--env-file` 注入的值优先于文件,文件是"未注入时的默认"。这样同一份 `.env` 既能本地直接用,也能被部署编排覆盖。

### D3:专属文件、不并进主 `.env.example`

模板独立为 `config/node.env.example`(不塞进仓库根 `.env.example`)——强化"node 配置是 agent 宿主本地、独立归属"的边界,避免与 platform/agent 配置混淆。

### D4:缺失静默跳过

`.env` 不存在时不报错(纯进程 env 部署仍可用);必需变量缺失时仍由现有 `_require_env` 抛 `ConfigError`(行为不变)。

## Risks / Trade-offs

- **[service key 落盘]** node `.env` 含明文 service key。→ 与 agent home `.env` 含密钥同等性质;文件权限由部署方保证(0600)。比散落 shell history 更可控。模板里注明权限建议。
- **[加载顺序误解]** 有人想把 `FLEETENT_HOME` 写进 node `.env`。→ design/模板注明 `FLEETENT_HOME` 须经进程 env。

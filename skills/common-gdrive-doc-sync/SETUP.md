# common-gdrive-doc-sync SETUP

## 目标

完成 Google Drive 同步所需依赖配置（MCP-only）：
1. `google-drive` MCP server 已挂载到 agent（工具名 `google-drive__*`）
2. Google OAuth 授权已完成
3. `pandoc`（用于可转换类型）

> V1 执行策略为 `MCP-only`：不支持 `rclone`/`gdrive` CLI/手动上传回退。

## 0. 重要说明（先看）

### 授权初始化

挂载 `google-drive` MCP server 只下发 server 定义，**不会自动完成 Google OAuth 授权初始化**。

`google-drive-mcp` 需要 OAuth 凭据文件路径。即使 server 已配置，也必须确认其
`env.GOOGLE_DRIVE_OAUTH_CREDENTIALS` 指向有效的凭据文件（**绝对路径**）。

> 注意：不要写 `~` 或 `$HOME`，该路径不会自动展开。

完成首次 OAuth 授权后，server 才能正常工作；否则 skill 会在运行时表现为
`DRIVE_MCP_UNAVAILABLE` 或权限错误。

### 路径说明（fleetent）

fleetent 下文件全程使用 workspace 相对路径（如 `media/inbound/file.docx`），`google-drive` MCP 工具的
`localPath` 直接传该相对路径，**无需** `/workspace`→宿主机路径的转换。详见 `PATH-MAPPING.md`。

## 1. 安装与检查 pandoc

```bash
pandoc --version
# 若未安装：
# Debian/Ubuntu
sudo apt-get update && sudo apt-get install -y pandoc
# RHEL/CentOS
sudo yum install -y pandoc
```

## 2. Google OAuth 准备

在 Google Cloud Console：
1. 创建项目
2. 启用 Google Drive API
3. 配置 OAuth consent screen
4. 创建 OAuth Client（Desktop App）
5. 获取 client id / client secret

建议 scopes：
- `https://www.googleapis.com/auth/drive.file`
- `https://www.googleapis.com/auth/drive`

## 3. 接入 Google Drive MCP

推荐：`piotr-agier/google-drive-mcp`
- https://github.com/piotr-agier/google-drive-mcp

### 3.1 挂载 `google-drive` MCP server

在 agent.yaml 的 MCP server 配置中挂载 `google-drive`，以 `npx` 启动 server，并通过环境变量注入
OAuth 凭据文件绝对路径（`GOOGLE_DRIVE_OAUTH_CREDENTIALS`）。挂载后工具以 `google-drive__<tool>` 形式可调用。

### 3.2 完成授权（必做）

#### 方式 A：默认授权（推荐）

不手动配置 `client_id/client_secret`，直接走 `google-drive-mcp` 默认 OAuth 流程：

```bash
env GOOGLE_DRIVE_OAUTH_CREDENTIALS=/absolute/path/to/credentials.json \
  npx -y @piotr-agier/google-drive-mcp auth
```

#### 方式 B：自定义 OAuth 凭据（企业/团队统一应用）

当你需要使用自建 GCP OAuth App：
1. 在 Google Cloud Console 创建 OAuth Client（Desktop App）
2. 下载 `credentials.json`
3. 通过环境变量注入给 `google-drive` server（`GOOGLE_DRIVE_OAUTH_CREDENTIALS`）
4. 重新授权（运行上面的 `auth` 命令）

授权完成后应存在 token 文件：

```bash
ls -l ~/.config/google-drive-mcp/tokens.json
```

### 3.3 服务器环境（无 GUI）授权（SSH 隧道）

`google-drive-mcp` 使用本地回调（`localhost:3000-3004`）。在服务器环境统一使用 SSH 本地端口转发：

```bash
# 在本地机器执行
ssh -L 3000:localhost:3000 -L 3001:localhost:3001 -L 3002:localhost:3002 -L 3003:localhost:3003 -L 3004:localhost:3004 <user>@<server>
```

保持隧道会话后，在服务器执行 3.2 的授权命令。

## 4. 运行前验收（必须）

1. 确认 `google-drive` MCP server 已挂载（agent 能列出 `google-drive__*` 工具）
2. 调用一次只读工具（如 `google-drive__listFolder`）确认 server 可达且授权有效
3. 转换能力（可选）：`pandoc --version`

若 server 不可用或授权失效，skill 执行应返回 `DRIVE_MCP_UNAVAILABLE`。

## 5. 常见故障与排查顺序

1. `DRIVE_MCP_UNAVAILABLE`
- 检查 `google-drive` MCP server 是否已挂载、工具是否可列出
- 检查 OAuth 授权状态（token 文件是否存在）
- 若服务器无 GUI：按 3.3 使用 SSH 隧道完成 OAuth 回调

2. `TARGET_FOLDER_UNRESOLVABLE`
- 检查目录链接是否是 folder 页面，或直接传 `folderId`

3. `DRIVE_PERMISSION_DENIED`
- 当前 OAuth 用户对目标目录无写权限

4. `PANDOC_NOT_INSTALLED`
- 安装 `pandoc`

5. `PANDOC_CONVERT_FAILED` / `CONVERTED_FILE_EMPTY`
- 检查源文件编码与内容完整性

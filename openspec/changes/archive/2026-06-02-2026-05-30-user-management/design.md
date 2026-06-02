# Design — User & IM User Management

## 身份模型

一个**内部 User（UUID）**统一承载 web 身份与 IM 身份：

- web 身份：`email` + `password_hash` + `role` + `status`，0~N 把 API key（`api_keys` 表）。
- IM 身份：0~N 条 `(platform, platform_user_id)` 映射（`im_users` 表）到同一个 User UUID。

拉黑、配额作用在 **User 维度**（级联所有 web + IM 身份）；IM 加黑也可只作用单个 IM 身份。

## 角色与内置 admin

`role ∈ {built_in_admin, admin, viewer}`，取代 `agent-admin-api` 的布尔 `is_admin`（兼容：`is_admin == role in {admin, built_in_admin}`）。

- **内置 admin**：首次启动种子化，用户名固定（如 `admin`），生成临时初始密码写启动日志，`must_reset=1`。首登强制改密才能进后台。不可删除、不可改名、不可降级；只能本人改自己密码。普通 admin 不可拉黑/降级内置 admin。
- 守卫：`/admin/*` 要求 `role in {admin, built_in_admin}`；写操作 viewer 一律 403；高危操作额外要求 2FA 通过。

## 认证

- 密码：哈希存储（倾向标准库 `hashlib.scrypt`，避免新依赖；最终选型 PR 定）。绝不存明文。
- 登录会话：服务端会话令牌 + 空闲超时（超时自动登出）。与 `/chat` 的 Bearer API key 是两套——后台用登录会话，程序化调用用 API key。
- 2FA：TOTP（倾向标准库实现 HOTP/TOTP）；仅高危操作（删用户、拉黑、改角色、撤销 key）要求当次 2FA 校验。
- 无公网自助注册：不存在 `/register`；访问返回 404 或显式提示联系管理员。

## API key（多 key + scope）

`api_keys` 表：`id`、`user_id`、`key_hash`（存哈希，不存明文）、`prefix`（`ma-` + 前若干位，供列表识别）、`scope`（JSON agent 白名单，`["*"]` 表示全部）、`note`、`expires_at`(nullable)、`revoked_at`(nullable)、`created_at`、`last_used_at`、`last_ip`、`last_ua`、`call_count`。

- 签发：明文只展示一次；库里存 `key_hash`。
- `get_by_api_key`：按哈希查；若 `revoked_at` / 过期 / 所属 User 为 blocked → 视为无效（401）。
- scope 校验：`/chat` 路由到目标 agent 后，用 `agent_policy` 同款 fnmatch 比对 key.scope；不在白名单 → 403。
- 使用情况：每次成功认证更新 `last_used_at` / `last_ip` / `last_ua` / `call_count`（轻量 UPDATE）。
- 过期提醒：每日定时任务（复用 scheduling）扫 `expires_at` 临近的 key 发邮件 + UI 标记；一键续期改 `expires_at`。

## 建账与邀请

- 手动建账：admin 填邮箱/姓名 +（初始密码 or 勾"首登自设"→`must_reset`）；账号即刻可用。
- 邀请链接：`invites` 表存一次性 token（hash + `expires_at` + `used_at`）；用户点链接设密码激活，token 用后/过期立即失效，签发首把 key。
- CSV 批量导入：解析邮箱/姓名，逐行建账，失败行汇总报告。

## 拉黑级联

一键拉黑（必填原因）：`status=blocked` → 撤销该 User 全部 `api_keys`（`revoked_at`）→ 关联 `im_users` 置 `allowed=0` → `email` 与（如有）OAuth subject 进 `blocked_registrations` → 写审计。解封：`status=active`，但已撤销 key 不自动复活、IM 需重新审批。批量拉黑：按邮箱域 / IP / 时间窗匹配，逐条审计 + 关联批次 ID。

## IM 用户默认放行（翻转）

- `im_user_store.get_or_create` 新建默认 `allowed=1`（准入交给 `im-channel-allowlist`，见 im-gateway-management change）。
- 工作台：列出活跃/被加黑 IM 用户，单条或批量加黑/恢复（填原因，写审计），仅 `admin`/`built_in_admin` 可操作，viewer 只读。
- 多平台账号合并：按 `user_id` 聚合展示同一 User 的 Slack + Telegram + WhatsApp 身份。
- CLI `block-user` 收回：返回 deprecated 提示，不改状态（加黑改后台）。

## 配额

`quotas` 表：作用域（`global` 或 `user:{id}`）、`token_limit`、`call_limit`、窗口（如按月/总量，PR 定）。`/chat` 入口检查：超限返回 429 并发"超限"事件；系统内部调用（压缩等）可豁免。

## 审计

`audit_log` 表：`id`、`actor_user_id`、`action`、`target_type`、`target_id`、`detail`(JSON)、`created_at`。所有管理写操作落一条；UI 可按 actor/action/target/时间检索与导出。高危动作（删用户/撤销 key/批量封禁）要求二次确认（2FA）后才执行并落审计。

## 测试隔离（遵循 CLAUDE.md）

- 所有新 store 复用 `user_store._conn` + 可 monkeypatch `DB_PATH`；测试 monkeypatch 到 `tmp_path`。
- 密码哈希/2FA：单测验证 hash 往返与 TOTP 校验，不依赖外部服务。
- 邮件发送（邀请/提醒）：mock 发送器，断言被调用与收件人，不发真实邮件。
- LLM/`/chat` 配额：构造请求，monkeypatch 配额表，断言 429 与放行；不发真实模型调用。
- 登录会话与 2FA 守卫：用 FastAPI TestClient（注意：导入 server 链路需 3.12，见仓库 Python 版本约定）。

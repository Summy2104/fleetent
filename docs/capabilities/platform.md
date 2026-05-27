# platform

> 写作提醒：功能描述只写可观察的行为，不写内部实现细节。验收标准只写端到端可验证的行为。

## 概述

多用户管理、API 认证和管理员操作。是 fleetent 作为多租户平台的基础层。

**调用关系**：
- 依赖：user_store、im_user_store、agent_store、config
- 被依赖：server.py（认证）、normalizer（用户查找）、admin CLI

## 现状

- ✅ **Bearer token 认证**：Authorization: Bearer ma-\<64hex\>
  - ma- 前缀区分服务 key 与模型 API key
  - get_by_api_key() 查 SQLite，无外部 IdP

- ✅ **用户管理 CLI**：
  - create-user --name：创建用户，生成 API key
  - list-users：列出所有用户
  - rotate-key --user-id：重置 API key

- ✅ **IM 用户管理 CLI**：
  - approve-user --im-user-id：审批 IM 用户
  - block-user --im-user-id：封禁 IM 用户
  - list-pending：列出待审批用户

- ✅ **Agent 管理 CLI**：
  - assign-channel --platform --channel-id --agent-name：绑定 channel
  - unassign-channel --platform --channel-id：解绑 channel
  - set-default-agent --agent-name：设置默认 agent

## 规划中（v1.0）

目前管理操作仅靠 CLI，规划中新增一套**面向管理员的可视化后台**（账号、用户、Agent、配额、审计、健康监控），并开放**终端用户自助注册**通道。

**设计哲学：开放注册 + 事后管控**——普通用户可自主完成注册，管理员通过拉黑机制阻止恶意账号，而不是把入口卡死在 CLI。

### 管理员账户与登录

- [ ] **管理员独立登录体系**：管理员账号与认证不依赖 Bearer token，独立的邮箱 + 密码（或对接 SSO / OAuth）登录后台

- [ ] **管理员角色分级**：admin（全权）、operator（用户与审批）、viewer（只读）三类，不同角色可见菜单与可操作按钮自动区分

- [ ] **二次验证 / 会话超时**：高敏感操作可强制二次验证，登录会话有空闲超时自动登出

### 终端用户自助注册

- [ ] **Web 自助注册**：普通用户可在 web 注册页填邮箱与密码完成注册，激活后自动签发首把 API key，无需管理员介入

- [ ] **邮箱验证激活**：注册后需点击邮件链接激活，未激活账号无法调用 /chat

- [ ] **第三方 OAuth 登录**：支持 Google / GitHub 等公共 IdP，用户首次通过 OAuth 登录即自动创建账号并签发 key

- [ ] **企业 SSO 接入**：普通用户可通过企业 SSO（OIDC / SAML）登录并自动建号，账号归属对应企业 / 组织

- [ ] **邀请码 / 邀请链接注册**：管理员可生成一次性或定数邀请码，启用邀请制后无邀请的注册请求被拒

- [ ] **注册来源可见**：用户详情显示注册渠道（自助 / OAuth / SSO / 邀请码 / 管理员创建），辅助审计与风险评估

- [ ] **注册速率限制 / 防滥用**：同 IP、同邮箱域、同时段的注册次数有上限，超限请求自动拒绝并记入可疑事件

### 用户管理控制台

- [ ] **用户列表与搜索**：支持按名称、邮箱、状态、创建时间、最近活跃排序与筛选

- [ ] **用户详情与全生命周期 CRUD**：单页查看基本信息 / 关联 IM 账号 / 用量 / 历史会话，可创建 / 编辑 / 禁用 / 删除用户

- [ ] **API key 多 key 管理**：一个用户可拥有多把 key，每把可设有效期、scope（endpoint / agent 维度）、备注，UI 内一键轮换或撤销

- [ ] **一键拉黑**：管理员可一键拉黑用户，被拉黑账号的所有 API key 立即失效，关联的 IM 账号同步封禁，同邮箱 / 同 OAuth subject 后续无法再次注册

- [ ] **拉黑原因与解封流程**：拉黑必须填写原因写入审计日志；可在后台解除拉黑，账号恢复后已失效的 key 不自动恢复（需重新生成）

- [ ] **批量拉黑**：可按邮箱域、IP、注册时间窗等条件批量拉黑，用于应对滥注或撞库攻击

### IM 用户审批工作台

- [ ] **待审批工作流**：实时展示 pending IM 用户列表，支持单条或批量审批 / 拒绝 / 封禁

- [ ] **多 IM 账号合并视图**：同一内部用户绑定的多个 IM 账号（Slack + Telegram + WhatsApp）在 UI 中合并展示，方便统一管理

- [ ] **审批通知推送**：新申请可通过 IM / 邮件 / Webhook 实时通知值班管理员

### Agent 与绑定管理

- [ ] **Agent 可视化 CRUD**：UI 内创建 / 编辑 agent，支持 system_prompt 富文本编辑、allowed_tools 多选、模型路由选择

- [ ] **Channel 绑定矩阵**：以 platform × channel × agent 的矩阵展示绑定关系，支持拖拽 / 点选改绑

- [ ] **默认 agent 与回退策略**：UI 内设置全局默认 agent 与回退顺序（channel → user → default → 裸跑）

- [ ] **管理端试聊沙箱**：管理员可在后台直接和某个 agent 对话验证效果，不影响线上 session

### 配额与权限

- [ ] **用量仪表盘**：per-user、per-agent、全局的 token 用量、调用次数、活跃 session 数趋势图

- [ ] **配额设置与超限告警**：可对单用户、单 agent 设置 token / 调用次数上限，超限时自动拒绝并通知

- [ ] **API key scope**：每把 key 可限制访问哪些 endpoint 或哪些 agent（只读 key 用于监控，读写 key 用于对话）

### 操作审计

- [ ] **审计日志**：所有管理操作（建删用户、轮换 key、改 agent、审批 IM 用户）记录"谁、何时、对什么资源、做了什么"，UI 内可检索与导出

- [ ] **高危操作二次确认**：删除用户 / 撤销 key / 批量封禁等高危动作要求二次确认或上级审批

### 接入点配置

- [ ] **IM 平台凭据可视化录入**：在 UI 内填入 Slack / Telegram / WhatsApp 等平台 token，不必修改 .env 或 yaml，凭据加密落盘

- [ ] **凭据健康展示**：每个已配置平台显示连接状态、最近错误、最近一次成功收发时间

- [ ] **频道目录管理**：UI 可浏览 bot 已加入的所有频道 / DM，支持手动刷新与按名字搜索

### 会话与排错

- [ ] **历史会话浏览**：按用户 / channel / 时间 / 关键词检索历史对话，单条会话可展开完整 transcript

- [ ] **单会话调用 trace**：展示该会话中每一轮的工具调用、permission_gate 决策、模型路由、memory 命中

- [ ] **Eval 日志可视化**：把 traces.jsonl 渲染成可筛选、可下钻的事件流

### 系统健康仪表盘

- [ ] **首页总览**：各 IM 平台连接状态、API 错误率与延迟、活跃 session 数、permission_gate 待审批积压、定时任务执行情况一屏可见

- [ ] **实时事件流**：新用户申请、审批通过、超限告警、平台断线等关键事件按时间倒序滚动

## 验收标准

**场景 1：API key 认证**
- Given：有效的 Bearer token
- When：POST /chat
- Then：请求通过认证，正常处理

**场景 2：无效 token**
- Given：错误或过期的 Bearer token
- When：POST /chat
- Then：返回 401

**场景 3：创建用户**
- Given：管理员执行 create-user --name "Alice"
- When：命令执行成功
- Then：输出 API key，Alice 可立即用该 key 调用 /chat

**场景 4：IM 用户审批流程**
- Given：新 Slack 用户发消息（allowed=0）
- When：管理员执行 approve-user --im-user-id {id}
- Then：该用户后续消息正常进入 agent_loop

**场景 5：管理员邮箱登录**
- Given：已创建的管理员账号
- When：在后台登录页输入邮箱与密码
- Then：进入后台首页；未登录访问其他页面会被跳回登录页

**场景 6：角色分级可见性**
- Given：viewer 角色管理员已登录
- When：访问"删除用户"等写操作入口
- Then：相关按钮 / 菜单不可见或返回无权限，请求不会落库

**场景 7：高危操作二次验证**
- Given：admin 已登录但未通过 2FA
- When：尝试删除一个用户
- Then：UI 弹出二次验证；通过后才执行，否则操作被拒

**场景 8：用户列表搜索**
- Given：系统中有多个用户
- When：在搜索框输入 "Alice"
- Then：列表仅显示名称含 Alice 的用户

**场景 9：禁用用户后 key 失效**
- Given：管理员在 UI 内禁用了 Alice
- When：Alice 用原 API key 调用 /chat
- Then：返回 401 / 403，请求不进入 agent_loop

**场景 10：多 API key 独立轮换**
- Given：Alice 拥有两把 key A、B
- When：在 UI 内仅轮换 A
- Then：A 旧值立即失效，B 仍可正常调用 /chat

**场景 11：API key scope 限制**
- Given：一把 scope=readonly 的 key
- When：使用该 key POST /chat
- Then：返回 403，提示 scope 不足

**场景 12：IM 用户批量审批**
- Given：有 N 个 pending IM 用户
- When：全选并点"批量审批"
- Then：所有用户状态变为 allowed，下次发消息直接进入 agent_loop

**场景 13：多 IM 账号合并展示**
- Given：内部用户 Alice 绑定了 Slack 与 Telegram 两个 IM 账号
- When：打开 Alice 用户详情
- Then：两个 IM 账号在同一卡片下并列展示，可独立审批 / 封禁

**场景 14：新 IM 申请实时通知**
- Given：已配置通知 channel
- When：新 IM 用户发消息触发待审批
- Then：通知 channel 收到含申请人信息与跳转链接的消息

**场景 15：Agent UI 编辑即时生效**
- Given：agent "ops-bot" 已绑定到 channel #ops
- When：管理员在 UI 修改其 system_prompt
- Then：#ops 内的下一条用户消息使用更新后的 system_prompt

**场景 16：Channel 绑定矩阵改绑**
- Given：channel #qa 当前绑定 agent X
- When：管理员在矩阵 UI 把 #qa 改绑为 agent Y
- Then：#qa 内下一条用户消息进入 agent Y 处理

**场景 17：默认 agent 兜底**
- Given：设置 agent Z 为全局默认
- When：用户在没有绑定关系的 channel 发消息
- Then：进入 agent Z 处理，而不是裸跑

**场景 18：试聊沙箱不影响线上**
- Given：管理员在沙箱内与 agent X 对话
- When：沙箱会话结束
- Then：该对话不出现在普通用户的 session 历史中，也不计入用量

**场景 19：用量仪表盘更新**
- Given：用户 Alice 刚结束一段对话
- When：刷新用量仪表盘
- Then：Alice 的 token 用量与调用次数在分钟级延迟内可见更新

**场景 20：配额超限被拒**
- Given：Alice 设置了 10k token 配额且已用满
- When：Alice 再次调用 /chat
- Then：返回 429，告知超限；UI 收到超限事件

**场景 21：审计日志可检索**
- Given：管理员 admin1 刚轮换了 Alice 的 key
- When：在审计日志按"操作=轮换 key"筛选
- Then：找到该条记录，含 admin1、时间戳、目标用户、操作类型

**场景 22：高危操作二次确认**
- Given：admin 点击"删除用户 Alice"
- When：系统弹出二次确认对话框
- Then：未确认则不执行；确认后才落库并记入审计日志

**场景 23：UI 录入凭据后生效**
- Given：在 UI 录入新的 Slack bot token 并保存
- When：IM adapter 自动 reload 或重启
- Then：Slack 适配器使用新 token 成功连接，无需手动改 .env

**场景 24：凭据健康状态展示**
- Given：已配置的 Telegram bot token 已失效
- When：查看接入点配置页
- Then：Telegram 显示为 fatal，并展示最近错误原因

**场景 25：频道目录刷新**
- Given：bot 新加入一个频道
- When：在频道目录页点击"刷新"
- Then：新频道出现在列表中，可按名字搜索

**场景 26：历史会话检索**
- Given：Alice 在最近 30 天内有多段会话
- When：按"用户=Alice"+ 日期范围筛选
- Then：列表显示该用户的所有会话，单条可展开完整 transcript

**场景 27：单会话 trace 可见**
- Given：一段含工具调用与审批的会话
- When：打开该会话的 trace 视图
- Then：按时间序展示模型输出、工具入参 / 出参、permission_gate 决策、memory 命中

**场景 28：Eval 日志按类型筛选**
- Given：traces.jsonl 含 model_call / tool_call / approval 等多种事件
- When：在 UI 按事件类型筛选
- Then：仅显示对应类型事件，可下钻到原始 JSON

**场景 29：仪表盘总览**
- Given：多平台运行中，其中一个平台已断线
- When：打开后台首页
- Then：一屏看到各平台连接状态（含断线项）、API 错误率、活跃 session 数、待审批积压数

**场景 30：实时事件流**
- Given：管理员停留在首页
- When：新 IM 用户发消息触发待审批
- Then：实时事件流出现一条"新申请"事件，附跳转链接

**场景 31：Web 自助注册**
- Given：未注册用户访问注册页
- When：填写邮箱与密码并提交
- Then：系统创建账号、发送激活邮件；激活后用户获得首把 API key 可立即调用 /chat，无需管理员介入

**场景 32：未激活账号不可调用**
- Given：用户已注册但未点击激活链接
- When：尝试用已签发的 key 调用 /chat
- Then：返回 403 并提示"账号未激活"

**场景 33：OAuth 注册**
- Given：用户在注册页点击"使用 Google 登录"
- When：完成 OAuth 授权回调
- Then：系统按 Google 账号创建账号并签发 key，再次登录可复用该账号

**场景 34：企业 SSO 接入**
- Given：已配置企业 OIDC IdP
- When：用户通过企业 SSO 登录
- Then：系统按 SSO subject 自动建账号并归属对应企业 / 组织

**场景 35：邀请码注册**
- Given：系统已切换到邀请制
- When：无邀请码的访客提交注册表单
- Then：注册被拒并提示"需要邀请码"；持有效邀请码者注册成功，该邀请码消耗 1 次

**场景 36：注册速率限制**
- Given：同一 IP 在 5 分钟内已注册多次达上限
- When：再次提交注册
- Then：注册被拒并记入可疑事件，安全告警面板可见

**场景 37：注册渠道可见**
- Given：Alice 通过 Google OAuth 注册
- When：打开 Alice 用户详情
- Then：渠道字段显示"OAuth · Google"

**场景 38：一键拉黑级联生效**
- Given：用户 Alice 处于活跃状态，持有 2 把 API key、绑定 Slack 与 Telegram 两个 IM 账号
- When：管理员一键拉黑 Alice 并填写原因
- Then：两把 key 立即失效；两个 IM 账号同步封禁；同邮箱再次注册被拒；操作进入审计日志

**场景 39：解封流程**
- Given：Alice 已被拉黑
- When：管理员在后台解除拉黑
- Then：账号本身恢复可登录，已失效的 key 不自动恢复；IM 账号需重新审批；解封动作记入审计

**场景 40：批量拉黑**
- Given：检测到来自同一邮箱域的 N 个滥注账号
- When：管理员按"邮箱域=evil.com"批量拉黑
- Then：所有匹配账号被拉黑，操作以一条聚合审计记录入库

## 待决问题

- [ ] API key scope 的粒度设计（endpoint 级 vs agent 级）（负责人：待认领）

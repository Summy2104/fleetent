# platform

> 写作提醒：功能描述只写可观察的行为，不写内部实现细节。验收标准只写端到端可验证的行为。

## 概述

多用户管理、API 认证和管理员操作。是 fleetent 作为多租户平台的基础层。

**调用关系**：
- 依赖：user_store、im_user_store、agent_store、config
- 被依赖：server.py（认证）、normalizer（用户查找）、admin CLI

## 现状

- ✅ **Bearer token 认证**：`Authorization: Bearer ma-<64hex>`，`ma-` 前缀区分服务 key 与模型 API key
  - get_by_api_key() 查 SQLite，无外部 IdP

- ✅ **用户管理 CLI**：create-user、list-users、rotate-key

- ✅ **IM 用户管理 CLI**：approve-user、block-user、list-pending

- ✅ **Agent 管理 CLI**：assign-channel、unassign-channel、set-default-agent

## 规划中（v1.0）

目前所有管理操作仅靠 CLI，规划新增**面向管理员的可视化后台**与**终端用户自助注册**通道。设计哲学：开放注册 + 事后管控——普通用户自主完成注册，管理员通过拉黑机制阻止恶意账号，而不是把入口卡死在 CLI。

- [ ] **管理员独立登录**：邮箱 + 密码或 SSO / OAuth，admin / operator / viewer 三级角色按可见菜单与操作按钮自动区分，高敏感操作支持 2FA，登录会话空闲超时自动登出

- [ ] **终端用户自助注册**：Web 邮箱注册 + 激活邮件、第三方 OAuth、企业 SSO（OIDC / SAML）、邀请码注册可切换，注册渠道写入用户详情

- [ ] **注册防滥用**：同 IP、同邮箱域、同时间窗的注册次数有上限，超限请求自动拒绝并记入可疑事件

- [ ] **用户列表与生命周期**：按名称 / 邮箱 / 状态 / 创建时间 / 最近活跃排序与筛选，单页查看基本信息、关联 IM 账号、用量、历史会话，可创建 / 编辑 / 禁用 / 删除

- [ ] **多 API key 管理**：一个用户可拥有多把 key，每把可设有效期、scope（endpoint / agent 级）、备注，独立轮换与撤销

- [ ] **一键拉黑与解封**：拉黑后所有 key 立即失效、关联 IM 账号同步封禁、同邮箱 / OAuth subject 后续注册被拒；拉黑必须填写原因写入审计；解封后账号可登录但已失效的 key 不自动恢复

- [ ] **批量拉黑**：按邮箱域、IP、注册时间窗批量拉黑，用于应对滥注或撞库攻击

- [ ] **IM 用户审批工作台**：实时 pending 列表，支持单条或批量审批 / 拒绝 / 封禁；同一内部用户的多 IM 账号（Slack + Telegram + WhatsApp）合并展示；新申请可通过 IM / 邮件 / Webhook 通知值班

- [ ] **Agent 可视化 CRUD**：UI 内编辑 system_prompt、allowed_tools、模型路由；platform × channel × agent 矩阵展示绑定关系；可设全局默认 agent 与回退顺序；后台试聊沙箱不影响线上 session 与用量

- [ ] **用量与配额**：per-user、per-agent、全局的 token 用量、调用次数、活跃 session 数仪表盘；可设单用户 / 单 agent 上限，超限自动拒绝并通知

- [ ] **审计日志**：所有管理操作（建删用户、轮换 key、改 agent、审批 IM 用户）记录"谁、何时、对什么资源、做了什么"，UI 内可检索与导出；删除用户 / 撤销 key / 批量封禁等高危动作要求二次确认

- [ ] **接入点配置**：UI 内录入并加密落盘 Slack / Telegram / WhatsApp 等平台凭据，无需修改 .env；展示连接状态、最近错误、最近一次成功收发时间；可浏览 bot 已加入的频道目录

- [ ] **会话与 trace 浏览**：按用户 / channel / 时间 / 关键词检索历史对话，单会话展开完整 transcript 与逐轮工具调用、permission_gate 决策、模型路由、memory 命中；traces.jsonl 渲染为可筛选、可下钻的事件流

- [ ] **系统健康仪表盘**：首页一屏可见各 IM 平台连接状态、API 错误率与延迟、活跃 session 数、permission_gate 待审批积压、定时任务执行情况；新申请、超限告警、平台断线等关键事件按时间倒序滚动

## 验收标准

**场景 1：API key 认证**
- Given：有效或无效的 Bearer token
- When：POST /chat
- Then：有效 token 正常处理，无效或过期 token 返回 401

**场景 2：CLI 创建用户**
- Given：管理员执行 `create-user --name "Alice"`
- When：命令执行成功
- Then：输出 API key，Alice 可立即用该 key 调用 /chat

**场景 3：IM 用户审批**
- Given：新 Slack 用户发消息（allowed=0）
- When：管理员执行 `approve-user --im-user-id {id}`
- Then：该用户后续消息正常进入 agent_loop

**场景 4：管理员角色分级（v1.0）**
- Given：viewer 角色管理员已登录
- When：访问"删除用户"等写操作入口
- Then：相关按钮 / 菜单不可见或返回无权限，请求不落库

**场景 5：高危操作二次验证（v1.0）**
- Given：admin 已登录但未通过 2FA
- When：尝试删除一个用户
- Then：UI 弹出二次验证；通过后才执行，否则操作被拒并记入审计

**场景 6：Web 自助注册（v1.0）**
- Given：未注册用户访问注册页
- When：填写邮箱与密码并完成激活邮件点击
- Then：账号激活并签发首把 API key 可立即调用 /chat；未激活账号调用返回 403

**场景 7：OAuth / SSO 注册（v1.0）**
- Given：用户通过 Google OAuth 或企业 SSO 登录
- When：完成授权回调
- Then：系统按 subject 自动建账号并签发 key，用户详情渠道字段显示来源

**场景 8：邀请码注册（v1.0）**
- Given：系统已切换到邀请制
- When：无邀请码访客提交注册表单
- Then：注册被拒并提示"需要邀请码"；持有效邀请码注册成功，该邀请码消耗 1 次

**场景 9：注册速率限制（v1.0）**
- Given：同 IP 在 5 分钟内注册次数已达上限
- When：再次提交注册
- Then：注册被拒并记入可疑事件，安全告警面板可见

**场景 10：多 API key 独立轮换（v1.0）**
- Given：Alice 拥有两把 key A、B
- When：在 UI 内仅轮换 A
- Then：A 旧值立即失效，B 仍可正常调用 /chat

**场景 11：API key scope 限制（v1.0）**
- Given：一把 scope=readonly 的 key
- When：使用该 key POST /chat
- Then：返回 403，提示 scope 不足

**场景 12：一键拉黑级联生效（v1.0）**
- Given：Alice 持有 2 把 API key、绑定 Slack 与 Telegram 两个 IM 账号
- When：管理员一键拉黑 Alice 并填写原因
- Then：两把 key 立即失效；两个 IM 账号同步封禁；同邮箱再次注册被拒；操作进入审计日志

**场景 13：解封后 key 不复活（v1.0）**
- Given：Alice 已被拉黑
- When：管理员在后台解除拉黑
- Then：账号本身恢复可登录，已失效的 key 不自动恢复；IM 账号需重新审批

**场景 14：批量拉黑（v1.0）**
- Given：检测到来自同一邮箱域的 N 个滥注账号
- When：管理员按"邮箱域=evil.com"批量拉黑
- Then：所有匹配账号被拉黑，操作以一条聚合审计记录入库

**场景 15：IM 用户批量审批（v1.0）**
- Given：有 N 个 pending IM 用户
- When：全选并点"批量审批"
- Then：所有用户状态变为 allowed，下次发消息直接进入 agent_loop

**场景 16：Agent UI 编辑即时生效（v1.0）**
- Given：agent "ops-bot" 已绑定到 channel #ops
- When：管理员在 UI 修改其 system_prompt
- Then：#ops 内的下一条用户消息使用更新后的 system_prompt

**场景 17：试聊沙箱不影响线上（v1.0）**
- Given：管理员在沙箱内与 agent X 对话
- When：沙箱会话结束
- Then：该对话不出现在普通用户的 session 历史中，也不计入用量

**场景 18：配额超限被拒（v1.0）**
- Given：Alice 设置了 10k token 配额且已用满
- When：Alice 再次调用 /chat
- Then：返回 429，告知超限；UI 收到超限事件

**场景 19：审计日志可检索（v1.0）**
- Given：管理员 admin1 刚轮换了 Alice 的 key
- When：在审计日志按"操作=轮换 key"筛选
- Then：找到该条记录，含 admin1、时间戳、目标用户、操作类型

**场景 20：UI 录入凭据后生效（v1.0）**
- Given：在 UI 录入新的 Slack bot token 并保存
- When：IM adapter 自动 reload 或重启
- Then：Slack 适配器使用新 token 成功连接，无需手动改 .env

**场景 21：凭据健康状态展示（v1.0）**
- Given：已配置的 Telegram bot token 已失效
- When：查看接入点配置页
- Then：Telegram 显示为 fatal，并展示最近错误原因

**场景 22：单会话 trace 可见（v1.0）**
- Given：一段含工具调用与审批的会话
- When：打开该会话的 trace 视图
- Then：按时间序展示模型输出、工具入参 / 出参、permission_gate 决策、memory 命中

**场景 23：仪表盘总览（v1.0）**
- Given：多平台运行中，其中一个平台已断线
- When：打开后台首页
- Then：一屏看到各平台连接状态（含断线项）、API 错误率、活跃 session 数、待审批积压数

## 待决问题

- [ ] API key scope 的粒度设计（endpoint 级 vs agent 级）（负责人：待认领）
- [ ] 管理员认证体系是内置邮箱密码还是强制对接 SSO（负责人：待认领）
- [ ] 默认是开放注册还是邀请制（负责人：待认领）

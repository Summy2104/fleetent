---
name: bs-customer-drafting
description: NS 客户管理（写操作）：通过 armada MCP 完成客户的「创建 / 修改」。触发词：创建/新建/新增/录入客户、修改/更新/编辑/变更客户、client onboard、create/update/edit customer。
status: active
metadata:
  author: RD Team
  version: 1.0.3
---

# NS 客户管理（写操作）

调用 Armada Admin 的客户写操作接口。

## armada 两步交互（所有 NS API 调用通用）

NS API 调用走 **armada 两步交互**：

1. `bash_exec` 跑 `bash $SKILLS_DIR/bs-customer-drafting/scripts/ns-call.sh "$UID" <method> <path> [kv...]`，拿到一行 `ARMADA_CALL armada__armada_<method> path=... <kv...> _meta={...}`（wrapper 只做 uid 格式校验 + 构造 `_meta.slackUserId`，不直接访问 NS）。
2. agent 据此发起对应的 `armada__armada_<method>`（`armada__armada_get` / `armada__armada_post` / `armada__armada_put` / `armada__armada_delete`）工具调用，参数即 ARMADA_CALL 行里的 `path=` + 各 kv（`query_params` / `path_params` / `body`）+ `_meta`，拿到 NS 返回的 JSON。
3. 如需对 JSON 做查重/字段映射/裁剪，用 `run_code`（python）加工。

`$UID` 来源：fleetent ToolContext 的 `slackUserId`（发起对话的用户）；鉴权由 wrapper 统一注入 `_meta`，skill 不碰 token。

## 端点清单

| 动作 | armada 工具 | 端点 | 对外暴露 |
|------|------|------|---------|
| 创建客户 | `armada__armada_post` | `POST /v1/customers` | ✅ |
| 修改客户 | `armada__armada_put` | `PUT /v1/customers/{id}` | ✅ |
| 创建后自动 close（用户侧称草稿态） | `armada__armada_post` | `POST /v1/customers/{id}/close` | ❌ 仅内部 |

> 查询类动作按域委托：
> - 业务线 keyword、客户/主体字典等跨域 ID 映射 → 父 skill `common-ns-system-query` 的 `references/common-id-mapping.md`
> - 客户详情、业务线详情列表 → 子 skill `common-ns-masterdata`
> - NS API 调用统一走上方「armada 两步交互」（`scripts/ns-call.sh "$UID" <method> <path>` → `armada__armada_<method>`），鉴权由脚本统一注入
> 本 skill 不重复定义查询端点。
>
> **启用/禁用客户**不在本 skill 端点白名单内。用户要求启用/禁用时，直接走两步交互调用对应端点即可（`POST /v1/customers/{id}/enable` 或 `POST /v1/customers/{id}/disable`，body `{}`），不走本 skill 的预览/确认流程；失败原样透传错误。

```bash
bash_exec: bash $SKILLS_DIR/bs-customer-drafting/scripts/ns-call.sh "$UID" \
  post "/v1/customers/{id}/enable" \
  'path_params={"id":"{客户 ID}"}' \
  'body={}'
```

## 强制护栏

1. **枚举值不得猜测**：`type` / `kyc` / `nda` 等映射以 `references/customer-api.md` 为准。
2. **写操作前强制预览 + 显式确认**：发起 `armada__armada_post` / `armada__armada_put` 前必须发**预览 `.tsv` 附件**并等用户回复「确认 / 好 / ok / go」。信息齐全也不得跳过。
3. **创建后自动调用 `/close` 是必做步骤**（NS 无原生草稿，用 close 实现「草稿」效果）：**对用户话术禁止使用「关户」「关闭客户」**；成功回显见 Step 7（固定话术「已置为草稿态（启用后正常使用）」）。close 成功时不再单独发一条只汇报 close 的进度消息。失败时告知客户 ID，并提示草稿置位失败、需在管理端处理（见 Step 6）。
4. **错误原样透传**：任何写操作后必须**显式检测失败**，失败原文透传给用户，不隐藏、不推断、不自动重试。
   - **失败判定（任一命中即失败）**：HTTP 4xx/5xx **或** HTTP 200 但响应 body 含非空 `error_code` 字段（NS 后端部分业务错误走此模式，典型 `ErrCustomerLastBizLine`——未传 `biz_lines` 时触发）
   - **成功判定**：HTTP 2xx **且** body 无 `error_code`。仅此情况才能回显「创建/修改成功」
5. **敏感字段保留**：邮箱、手机号等原样保存，不脱敏。
6. **字段格式前置校验**：进入预览前必须过「字段前置校验规则」，任何一项不合法都停下让用户改，不得把垃圾塞进预览或 body。
7. **大整数 ID 一律字符串**：NS 是 19 位雪花 ID（超 2^53-1），`biz_lines[]` / path 里的 `{id}` / 响应里的 `id` 全部按字符串处理。**禁止 parseInt / 去引号**。枚举才用整数，不要混。

## 模糊匹配规范

维度数据查询（业务线、客户等）统一遵循以下规则：

**匹配优先级（高→低）**：精确匹配（trim + 大小写不敏感完全相等）> 前缀匹配（用户输入是候选名称的开头）> 子串匹配（候选名称包含用户输入）

**命中处理**：
- 唯一命中 → 自动采用，无需额外确认
- 多条命中（≤ 10 条）→ 展示编号候选列表
- 多条命中（> 10 条）→ 展示前 10 条 + 提示"命中 {N} 条，超出展示上限，以下为前 10 条；如目标不在列表中请回复 N 取消并补充关键词重新发起"
- 零命中 → 提示用户重新输入，不猜测、不跳过

## 字段前置校验规则

调 API 前逐项检查，**任何一项不通过都要停下让用户改**，不得进入预览：

| 字段 | 规则 |
|------|------|
| `name` | 非空、去空白后长度 ≥ 1 |
| `email[]` / `contacts[].email` | 必须匹配 `^[^\s@]+@[^\s@]+\.[^\s@]+$`（含 `@`，`@` 后必须有 `.`，`.` 后至少 1 字符，整体无空格）。**弱判断如「含 `@` 就通过」必须拒绝**，例如 `"邮箱邮箱"` 要拒 |
| `contacts[].phone` | 至少 1 个数字；允许 `+` `-` 空格 括号 |
| `memo` | 长度 ≤ 500 字 |
| `kyc` / `nda` / 其他枚举 | 必须是 references 里允许的整数值 |

拒绝时用 bullet list 在聊天里列出每个错误项，格式 `- 字段「xxx」值「xxx」：原因`，末尾提示"请改正或回复『不传』跳过"。

## 回复风格（硬约束）

**Step 之间默认静默执行**。只在下列时刻才向用户发消息：

1. **需要用户输入**：Step 1 的 verbatim 模板、业务线/客户多条命中时让用户选
2. **异常**：业务线未命中、查重命中同名、API 失败、创建后 close（草稿置位）失败
3. **最终产出**：Step 4 预览附件（`.tsv`）、Step 7 创建完成回显、动作 B Step 5 修改完成回显（均需附 `https://admin.nsdigital.io/sensitive/detail/{id}` Web 链接）

**禁止出现的内容**（常见冗余，一条也别说）：

- 开场白：`好的`、`收到`、`明白了`、`我来为您...`、`让我帮您...`
- 流水账：`让我先读取 skill 流程`、`首先我需要 xxx`、`现在进行 xxx`、`接下来我要 xxx`
- 工具切换细节：`armada 不可用，让我改用 xxx`、`正在调用 armada__armada_get`
- 中间成功播报：`业务线「xxx」已找到，ID 为 xxx`、`查重通过，无重名客户`、`已查到客户详情`

**举例**：用户说"创建客户 示例科技，业务线 NS-量化" 后，bot 的**下一条消息应当直接是 Step 4 预览附件 + 一行摘要**（假设业务线命中、查重通过），中间的业务线查询、查重等过程不播报。

## 输出格式

- 结构化表格用 **TSV 附件**发送，不在聊天里重复内容（依赖 `common-file-output`）
- 附件命名 `{主题}-{YYYYMMDD-HHmm}.tsv`，UTF-8，首行表头，`\t` 分隔
- 聊天正文只发 1-2 行摘要 + 下一步指引
- 短交互（字段询问、候选选择、校验错误、完成回显）不走附件，用 `- ` / `1) ` 列表

**候选列表（业务线 / 客户等多条命中）格式 — 硬约束：**

1. **选项标签必须与可解析规则一致**：每条候选用 **阿拉伯数字序号** 展示，例如 `1.` `名称（id: …）`、`2.` …；**禁止**只用 `a.` `b.` `c.` 当选项标签却又要求用户输入「1–N」，会造成选 `d` 被拒。
2. **文末固定提示语**：`请回复序号 1–{N}，或回复完整名称（与上表名称一字不差）。`（`{N}` 为候选条数）
3. **解析用户回复**： trim 后接受① `1`–`{N}` 的数字序号；② 与列表完全一致的完整名称。**可选兼容**：若用户误发单字母 `a`–`z`（大小写不敏感），按 `a`=1、`b`=2 … 映射到第几项（防御旧会话或复制误差）。

## Web 链接生成

创建/修改成功回显时必须附客户详情 Web 链接，域名固定为 `https://admin.nsdigital.io`，拼接格式：`https://admin.nsdigital.io/sensitive/detail/{客户 ID}`

- **客户 ID 原样字符串拼接**（19 位雪花 ID），不得 parseInt、不得去引号

## 端点与字段

> **主动加载**：进入本 skill 时，必须立即执行 exec 读取 references 文档，获取字段表与枚举映射。
>
> ```bash
> bash_exec: cat $SKILLS_DIR/bs-customer-drafting/references/customer-api.md
> ```

## 工作流

### 动作 A：创建客户

#### Step 1 — 收集信息

##### 向用户发起提问（必做）

**下面三个短横线之间是给用户的原文模板，一字不改作为一条消息发出去**（包括 `- ` 符号）。不要改措辞、不要省略枚举值、不要加"收到"这类开场白、**不要改成 Markdown 表格或 TSV**。

---

请提供以下信息（★ 必填）：

**必填：**

- ★ 客户名称（`name`）：客户的正式全称
- ★ 业务线（`biz_lines`）：说名称即可，多个用逗号分隔，我会一次批量查 ID

**可选**（留空走默认值或不传）：

- 客户简称（`short_name`）
- 客户编码（`customer_code`）
- 客户邮箱（`email`）：可多个
- 注册地址（`register_address`）
- 认证状态（`kyc`）：1=未完成 / 2=已完成 / 3=已关户；**默认 1 未完成**
- NDA 状态（`nda`）：1=未签署 / 2=已签署；**默认 1 未签署**
- 备注（`memo`）：≤500 字
- 联系人（`contacts`）：每人可填 姓名 / 邮箱 / 联系方式 / 角色 / 备注

**示例：**

- 客户名称：示例科技
- 业务线：NS-量化，NS-Trading
- 邮箱：a@x.com
- KYC：已完成

---

##### Agent 内部规则（不展示给用户）

- `kyc` / `nda` 未指定 → 用默认值 `1`，预览表标注"默认值"
- **`type` 字段：不传**。用户说"员工客户/供应商客户"也不加进 body、不进预览、不追问
- 输入残缺（如只说"帮我建个客户"）→ 重发 Step 1 verbatim 模板
- 进入 Step 3 前必须跑「字段前置校验规则」

#### Step 2 — 业务线 ID 映射

委托父 skill `common-ns-system-query` 的 `references/common-id-mapping.md`（业务线字典是跨域字典接口）批量查 `GET /v1/biz_lines/keyword`（`name` 参数是数组，一次调用搞定，**禁止串行单查**）：

```bash
bash_exec: bash $SKILLS_DIR/bs-customer-drafting/scripts/ns-call.sh "$UID" \
  get "/v1/biz_lines/keyword" \
  'query_params={"name": ["NS-量化", "NS-Trading"]}'
```

从 `list[]` 按「模糊匹配规范」优先级（精确 > 前缀 > 子串）匹配 `id`，按用户输入顺序填入 `biz_lines`：
- 唯一命中 → 自动采用
- 多条命中（≤ 10 条）→ 列候选让用户选（遵守「候选列表格式」：数字序号 + 固定提示语）
- 多条命中（> 10 条）→ 展示前 10 条 + 提示"命中 {N} 条，超出展示上限，以下为前 10 条；如目标不在列表中请回复 N 取消并补充关键词重新发起"，不得自动取第一条
- 零命中 → 停下问用户，不得猜测或跳过
- `id` 按字符串保留（见护栏第 7 条）
- **同时保留 `id → name` 映射**：预览附件的业务线列**显示名称**（如 `NS-量化, NS-Trading`），API body 里的 `biz_lines` 才传 ID 字符串数组。用户要看名称，不要 ID。

#### Step 3 — 查重

用 `name` 模糊搜索现有客户：

```bash
bash_exec: bash $SKILLS_DIR/bs-customer-drafting/scripts/ns-call.sh "$UID" \
  get "/v1/customers" \
  'query_params={"name": "示例科技", "page_size": 5}'
```

**分级处理**：
- **精确同名命中**（大小写无关、去空格后完全相等）→ 直接告知用户"已存在"并给出现有客户 ID，**不进入预览**
- **相似命中**（模糊包含）→ 列出来问用户是否仍要继续创建
- 未命中 → 直接进入下一步

#### Step 4 — 预览字段并等待确认

**上传附件 `客户创建预览-{客户名}-{YYYYMMDD-HHmm}.tsv`**，三列（`字段 / 值 / 来源`），展示全部字段（包括未填的）。`来源` 取值：`用户输入` / `默认值` / `固定值` / `空`。用户未填且无默认值的字段，`值` 列显式写 `空`，**禁止折叠**成"其他字段未填"。

示例内容（用户只给了 name 和 biz_lines = NS-量化, NS-Trading）：

```tsv
字段	值	来源
客户名称（name）	示例科技有限公司	用户输入
客户简称（short_name）	空	空
客户编码（customer_code）	空	空
客户邮箱（email）	空	空
业务线（biz_lines）	NS-量化, NS-Trading	用户输入
注册地址（register_address）	空	空
认证状态（kyc）	1 = 未完成	默认值
NDA 状态（nda）	1 = 未签署	默认值
备注（memo）	空	空
联系人（contacts）	空	空
```

> 注意：业务线列展示**名称**（人类可读），API body 里 `biz_lines` 仍传 ID 字符串数组。

聊天正文只发一行：「已发送创建预览附件（共 10 字段），确认无误请回复『确认』，我将提交创建。」

#### Step 5 — 执行创建

用户确认后：

```bash
bash_exec: bash $SKILLS_DIR/bs-customer-drafting/scripts/ns-call.sh "$UID" \
  post "/v1/customers" \
  'body={"name":"示例科技有限公司","short_name":"示例科技","biz_lines":["2046554312949643264","2046555212949643264"],"email":["contact@example.com"],"kyc":2,"nda":2,"memo":"2026-Q1 新开户"}'
```

#### Step 6 — 自动 close（必做；对用户称「草稿态」）

NS 客户无独立草稿接口、创建后默认可用，为合规在创建成功后**立即**调用 `POST /v1/customers/{id}/close`（实现上的「草稿」效果）：

```bash
bash_exec: bash $SKILLS_DIR/bs-customer-drafting/scripts/ns-call.sh "$UID" \
  post "/v1/customers/{id}/close" \
  'path_params={"id":"{新客户 ID}"}' \
  'body={}'
```

- 自动执行，不再向用户确认；**不要**在聊天里单独播报「已调用 close」类技术细节
- 失败 → 用户可见文案须避免「关户」：例如「客户 `{name}`（ID=`{id}`）已创建，但未能完成草稿置位：{错误}。请到管理端处理或稍后重试。」
- close 失败**不得回滚创建**（后端无 rollback）

#### Step 7 — 回显与后续建议

- 展示：新客户 ID、**已置为草稿态（启用后正常使用）**、**客户详情 Web 链接**
- 链接固定拼接：`https://admin.nsdigital.io/sensitive/detail/{新客户 ID}`
- 建议：补充 KYC / 内部审批；**正式使用前需启用**（`POST /v1/customers/{id}/enable`，见端点清单上方示例）。可顺带询问是否需协助发起启用

回显示例：

```
✅ 客户「示例科技有限公司」创建成功
- 客户 ID：2046949669067378688
- 状态：已置为草稿态（启用后正常使用）
- Web链接：https://admin.nsdigital.io/sensitive/detail/2046949669067378688
```

---

### 动作 B：修改客户

> **完整 PUT 模式**：body 带上所有可改字段的**最终值**（未改字段用从详情拉回的原值回填）。`biz_lines` 从详情的 `biz_type[*].id` 映射回填，**必传**——后端不支持未传保持原值，缺失会触发 `ErrCustomerLastBizLine` 业务错误（HTTP 200 + body.error_code 形式）。

#### Step 1 — 定位客户 ID

委托父 skill `common-ns-system-query` 的 `references/common-id-mapping.md`（客户字典是跨域字典接口）查 `/v1/customers/keyword`：

```bash
bash_exec: bash $SKILLS_DIR/bs-customer-drafting/scripts/ns-call.sh "$UID" \
  get "/v1/customers/keyword" \
  'query_params={"name": "示例科技"}'
```

按「模糊匹配规范」优先级（精确 > 前缀 > 子串）匹配：
- 唯一命中 → 自动采用
- 多条命中（≤ 10 条）→ 列 **数字** 序号 + ID + 名称 + 编码 + 状态
- 多条命中（> 10 条）→ 展示前 10 条 + 提示"命中 {N} 条，超出展示上限，以下为前 10 条；如目标不在列表中请回复 N 取消并补充关键词重新发起"，不得自行假设
- 零命中 → 停下，提示用户确认客户名称

#### Step 1.5 — 拉详情做 baseline（必做，静默执行）

用户选定客户后**立即**拉一次详情，作为 PUT 的基线值：

```bash
bash_exec: bash $SKILLS_DIR/bs-customer-drafting/scripts/ns-call.sh "$UID" \
  get "/v1/customers/{id}" \
  'path_params={"id":"<customer_id>"}'
```

把响应里所有可改字段原值存进 baseline：`short_name` / `customer_code` / `email` / `register_address` / `kyc` / `nda` / `memo` / `contacts` / `biz_lines`。

`biz_lines` 字段映射：详情接口以 `biz_type` 返回业务线，结构 `[{id, name}]`。**从 `biz_type[*].id` 提取字符串数组存入 `baseline.biz_lines`**；同时保留 `biz_type[*].name` 供预览表展示。baseline 必须始终持有 `biz_lines` —— Step 4 PUT 时此字段必传，不允许「未返回 → 不传」。

`contacts` 回填规则：GET 响应的 `contacts[*]` 附带后端元数据。**存入 baseline 时保留 `id` + 5 个用户字段**（`name` / `email` / `phone` / `role` / `memo`），剥离 `created_at` / `created_by` / `updated_at` / `updated_by` / `customer_id`。`id` 在 Step 4 构造 `contacts.update[]` 和 `contacts.delete[]` 时必须用到，不可丢弃。

#### Step 2 — 询问要改的字段

##### 向用户发起提问（必做）

**下面三个短横线之间的内容是给用户的原文模板**，把 `{name}` 和 `{id}` 替换成 Step 1 选定的客户名和 ID，**其余内容一字不改**作为一条消息发出去。不要折叠表格、不要改措辞、不要加"收到"这类客套开场白。

---

选定：**客户 `{name}`（ID=`{id}`）**。

要改哪些字段？告诉我字段和新值即可（可多个）。

**可改字段白名单：**

- 客户简称（`short_name`）
- 客户编码（`customer_code`）
- 业务线（`biz_lines`）：说名称即可，多个用逗号分隔，我会一次批量查 ID
- 客户邮箱（`email`）：可多个
- 注册地址（`register_address`）
- 认证状态（`kyc`）：1=未完成 / 2=已完成 / 3=已关户
- NDA 状态（`nda`）：1=未签署 / 2=已签署
- 备注（`memo`）：≤500 字
- 联系人（`contacts`）：**diff 模式**（非整体替换）。skill 会对比 baseline 和用户意图自动生成 `add` / `delete` / `update` 三组。每人可填 姓名 / 邮箱 / 联系方式 / 角色 / 备注

**不支持修改**：`name`（客户名）、`type`（客户类型）、`status`（走启用/禁用 skill）、`source_*`（后端自管）。

示例：

- KYC 改已完成
- 备注改"2026-Q2 续签"
- 业务线加一个 NS-DeFi

---

##### Agent 内部规则（不展示给用户）

- 白名单外字段（`name` / `type` / `status`）→ 直接告知"不支持修改"
- `biz_lines` 改动 → 复用创建 Step 2 的批量 keyword 查询规则
- `contacts` 走 **diff 模式**（非整体替换）。用户说"加一个联系人" → 仅进 `add[]`（不带 id）；"删掉张三" → 仅进 `delete[]`（用 baseline 的 id）；"改张三的邮箱" → 进 `update[]`（带 baseline 的 id + 完整 5 字段）；未改动的 contact 不进任何组。PUT body 的 contacts 形如 `{"add":[],"delete":[],"update":[...]}`
- 进入 Step 3 前必须跑「字段前置校验规则」
- 用户可"清空字段"（如"邮箱清空"）→ 新值用 `[]` 或 `""`，预览标注"（清空）"等确认

#### Step 3 — 预览（旧值 / 新值对比）

**上传附件 `客户修改预览-{客户名}-{YYYYMMDD-HHmm}.tsv`**，三列（`字段 / 旧值 / 新值`），展示全部可改字段（不论是否改动）。

- 旧值 = Step 1.5 baseline
- 新值：改了 → 用户新值；没改 → 值尾加「（未改动）」
- **业务线列旧/新值都展示名称**（旧值 name 来自 `baseline.biz_type[*].name`，新值 name 来自 Step 2 keyword 查询），不展示 ID
- **联系人列展示成易读的列表**（每人一行或用 `;` 分隔，格式 `姓名（邮箱）`），**不展示 diff 对象**。新值里用标记表示变化：新增标 `[+新加]`、删除标 `[-删除]`、修改标 `[改]`、未变不加标记——用户看的是「谁被改了」，不是 API 结构。diff 对象 `{add, delete, update}` 是 Step 4 提交前 skill 内部转换的产物，**不进入预览**

示例内容（用户只改了 `short_name` 和 `email`）：

```tsv
字段	旧值	新值
客户简称（short_name）	示例	AI 客户02（用户输入）
客户编码（customer_code）	C1102	C1102（未改动）
业务线（biz_lines）	NS-量化	NS-量化（未改动）
客户邮箱（email）	["old@x.com"]	["a@x.com","b@x.com"]（用户输入）
注册地址（register_address）	上海	上海（未改动）
认证状态（kyc）	1 = 未完成	1 = 未完成（未改动）
NDA 状态（nda）	1 = 未签署	1 = 未签署（未改动）
备注（memo）	旧备注	旧备注（未改动）
联系人（contacts）	张三（zhangsan@x.com）; 李四（lisi@x.com）	张三（zhangsan@x.com）; 李四（lisi@x.com）[改：memo]; [+新加] 王五（wangwu@x.com）
```

聊天正文只发一行：「已发送修改预览附件，确认无误请回复『确认』，我将提交修改。」

#### Step 4 — 确认后提交

PUT body 带上所有可改字段的最终值（改动用新值，未改用 baseline 原值）。**`biz_lines` 必传**（从 `baseline.biz_type[*].id` 映射回填），后端不支持未传保持原值——缺失会触发 `ErrCustomerLastBizLine` 业务错误（HTTP 200 + body.error_code）。修改完成后**不自动调用 close**（修改不是新建）。

```bash
bash_exec: bash $SKILLS_DIR/bs-customer-drafting/scripts/ns-call.sh "$UID" \
  put "/v1/customers/{id}" \
  'path_params={"id":"<customer_id>"}' \
  'body={"short_name":"<short_name>","customer_code":"<customer_code>","biz_lines":["<biz_line_id>"],"email":["<email>"],"register_address":"<register_address>","kyc":<kyc>,"nda":<nda>,"memo":"<memo>","contacts":{"add":[],"delete":[],"update":[{"id":"<contact_id>","name":"<name>","email":"<email>","phone":"<phone>","role":"<role>","memo":"<memo>"}]}}'
```

#### Step 5 — 回显

修改成功后展示：客户 ID + **客户详情 Web 链接**。链接固定拼接：`https://admin.nsdigital.io/sensitive/detail/{客户 ID}`。

回显示例：

```
✅ 客户「示例科技有限公司」修改成功
- 客户 ID：2046949669067378688
- Web链接：https://admin.nsdigital.io/sensitive/detail/2046949669067378688
```

## 禁止事项

- **路径白名单**：只允许端点清单里的 3 个端点（`POST /v1/customers`、`PUT /v1/customers/{id}`、`POST /v1/customers/{id}/close`），禁止扩展到其他 `/v1/customers/*` 路径。

**写接口失败时**（HTTP 非 2xx，**或** HTTP 200 但 body 含非空 `error_code`）：

1. 禁止改用户确认过的 body 后重试（包括给 `name` 加后缀、截断 `memo`、降级 `kyc`、删 `contacts` 等任何字段变动）
2. 禁止自行重试——必须原文透传错误并停下等用户
3. 禁止事后补"已改用 XX 创建成功"之类话术；任何重试都要用户重新发起并走完预览确认

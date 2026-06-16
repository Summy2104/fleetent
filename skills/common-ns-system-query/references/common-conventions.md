# 公共规范（号码识别 / 字段展示 / wrapper 语法）

> **⚠️ 鉴权契约**：本文档所有示例中的 `"$UID"` 是占位符，agent 在实际用 bash_exec/run_code 运行 wrapper 时须替换为 Step 0 从 incoming JSON 提取的 `sender_id`。`_meta={"slackUserId":"..."}` 由 wrapper 内部自动注入。**严禁绕过 wrapper 直接调用 `armada__armada_get` / `armada__armada_post` 工具**。规则见 `SKILL.md §调用模式`。

本文档是父 skill 与所有子 skill 共用的规范底层。SKILL.md 已摘要引用；这里是完整定义。

## 1. 号码识别

### 流程编号
- **格式**：`年月日 + 三位序号`，共 11 位数字，如 `20260410035`
- **识别**：用户输入中出现 11 位纯数字且以 `2026/2025/...` 年份开头的自动识别
- **转换**：先通过 `GET /v2/bpmn/process_instance/number/{process_number}` 转换为 `instance_id`，再做后续查询
- **归属**：涉及流程/资金详情/审批历史 → `common-ns-process`

### 项目号
- **格式**：`大写字母前缀（可含连字符或括号）+ 数字序号`，后可跟 `-描述文字`，无固定长度
- **示例**：`TR03642` / `Pay-OTC05809` / `(D)BM2026041202` / `LH050-Xcoin`
- **查询**：通过 `GET /v1/projects` 的 `no` 参数，**支持模糊匹配**（如 `TR036` 可匹配所有 `TR036xx`）
- **归属**：`common-ns-masterdata`

### 项目号 × 业务线强关联（展示级规则）
- 展示任何项目号必须同时标注业务线，格式 `项目号（业务线名称）`，如 `TR03642（NS-Trading）`
- 缺失业务线时必须先 `GET /v1/biz_lines` 补查
- **严禁跨业务线混用**：用户指定业务线上下文时只能用该业务线的项目号；其它业务线项目必须过滤不展示

## 2. 字段展示规范

- **字段名用中文**：按当前 reference 中的字段注释，英文字段名→中文
- **无中文注释的字段**：跳过不输出
- **字段值原样输出**：严禁拆分/解析/翻译/推断/二次加工；API 返回什么就展示什么
- **禁止创造新列或新属性**：不得输出 references 未定义的列
- **输出结构严格按 references 文档**：列名/列数/行数必须一一对应
- 嵌套对象与数组逐层套用以上所有规则

## 3. wrapper 调用语法

**【唯一合法入口】** 所有 armada 调用必须通过 wrapper：

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh \
     "$UID" <get|post> <path> [kv 参数...]
```

子 skill 全部通过绝对路径引用同一 wrapper（wrapper 单例，不复制）。`"$UID"` 在文档示例中是**占位符**，agent 在实际 exec 时必须替换为 Step 0 从 incoming JSON 提取的 `sender_id`（格式 `^U[A-Z0-9]{8,}$`）。

### 支持的 method
- ✅ `get` / `post`
- ❌ `put` / `patch` / `delete`（wrapper 当前不支持；写端点推迟到独立 PR，见 `wrapper-caveats.md`）

### 参数约定
- 位置参数 1：uid（slackUserId，`U` 开头格式）
- 位置参数 2：method（`get`|`post`）
- 位置参数 3：path（含 `{placeholder}` 可用路径参数替换）
- 其余 kv 参数原样透传给 armada 工具调用：`path_params` / `query_params` / `body`

### 示例

```bash
# 简单 GET
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v1/countries"

# 带查询参数
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v1/customers" \
  'query_params={"status": 3, "page": 1, "page_size": 20}'

# 带路径参数
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v1/accounts/bank/{id}" \
  'path_params={"id": "123"}'

# 路径参数 + 查询参数
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v1/accounts/fiat/company/account/{id}/account_numbers" \
  'path_params={"id": "456"}' \
  'query_params={"currency": "USD", "page": 1, "page_size": 10}'

# POST
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  post "/v1/accounts/digital_coin" \
  'body={"platform": "bitget"}'
```

### 特殊参数格式
- 数组：`"biz_line_ids": [1, 2, 3]`
- 日期：`"start_date": "2024-01-01"`
- 时间戳：`"transfer_time_start": "2024-01-01T00:00:00Z"`

## 4. 分页

- 每次请求 `page_size` 最大建议 `100`（单页上限，非总量上限）
- 用户要求"全部"/"所有"/"total" 时，自动连续翻页直到取完，**不得中途询问用户是否继续**
- 翻页直到响应 `page_info.has_next=false` 或 `list` 为空

## 5. 端点路径约定

- **严禁凭经验猜测 API 路径**；所有路径必须从对应子 skill 的端点索引中取用
- 典型易错：
  - `/v1/biz_lines`（非 `/v1/business_line`）
  - `/v1/department/list`（非 `/v1/departments`）
  - `/v1/contract/list`（非 `/v1/contracts`）
  - `/v1/monitor/fund_price_diff/data`（非 `/v1/monitor/bi_report/fund_diff`）
  - `/v1/biz_transactions/stat`（非 `/v1/monitor/bi_report/biz_line_fund_summary`）
- `keyword` / `label` 结尾接口返回全量 id+name，不支持过滤，只用于 ID→名称映射（详见 `common-id-mapping.md`）

## 6. MCP server / 工具名权威声明

- ✅ server_id `armada`，工具 `armada__armada_get` / `armada__armada_post`（`{server_id}__{tool_name}` 双下划线）
- ❌ `ns-mcp` / `armada-v2-mcp`（历史别名/旧 runtime 写法，所有下游 skill 应改写为 fleetent 工具名；在 blockquote 反例中提及可保留）

## 7. 时间展示规范

**所有响应字段中的时间值（包括 `*_at`、`*_time`、`*_date` 等所有时间字段），展示时必须转为北京时间（UTC+8）**。

- **格式**：`YYYY-MM-DD HH:MM:SS`（如 `2026-04-09 16:21:15`）
- **Slack 防 emoji 转义**：**输出时间值必须用反引号包裹**（如 `` `2026-04-09 16:21:15` ``），否则 Slack 会把 `:21:` 等片段误识别为 emoji 短代码
- **纯日期字段**（格式本身为 `YYYY-MM-DD`，不含时分秒）：无时区偏移，原样展示，无需转换
- **查询参数（请求入参）中的时间字段**：传输时仍使用 UTC，不受此规范约束
- 各 reference 中的响应时间字段描述标注 `（UTC，展示转 UTC+8）` 作为提醒

---
name: common-crypto-news-digest-hermes
description: 加密货币市场新闻摘要。每日自动获取影响市场行情的主要新闻、政策报道，提供主流货币趋势分析和市场情绪研判。触发词：今日加密货币新闻、市场行情分析、币圈重大新闻、crypto market news
status: active
metadata:
  author: RD Team
  version: 2.0.0
  platform: fleetent
---

# 加密货币市场新闻摘要（curl 取数版）

> **本文件用 `bash_exec` 运行 `curl` 直接抓 RSS/API 取数**（不走 `web_fetch`），工具 API、数据获取方式与 `web_fetch` 版不同，请勿混用。

## 核心目标

每日自动获取加密货币市场相关的关键资讯，聚焦于：

1. **影响行情波动的重大新闻** — 政策监管、机构动向、市场事件
2. **主流货币行情分析** — BTC、ETH、SOL 等主流币种的价格趋势和技术面
3. **市场情绪研判** — 基于新闻整体倾向判断市场看涨/看跌/中性情绪

## 触发场景

- "今日加密货币新闻"
- "市场行情分析"
- "币圈重大新闻"
- "主流币行情"
- "crypto market news"
- cron 定时触发（platform: cron）

## ⛔ 执行禁令

以下行为**严格禁止**，不可因任何理由绕过：

1. **禁止写入执行日志到 memory**：任务完成后不得记录执行日志、消息 ID、数据获取统计等一次性临时信息。
2. **禁止调用 send_im_message**：不得主动调用 `send_im_message` 发送任何内容，投递由 cron deliver 机制负责。
3. **禁止使用 web_fetch 工具**：本版固定走 `curl` 取数路径，不使用 `web_fetch`。RSS 和 API 均通过 `bash_exec` 运行 `curl` 获取。
4. **禁止将报告写入文件后停止**：必须按 Step 5 格式直接输出报告内容，不得以"写文件"代替。

## 数据源

4 个加密货币新闻网站，全部通过 `bash_exec` 运行 `curl` 获取：

| 源 | 域名 | 获取方式 | 聚焦内容 |
|---|-----|---------|----------|
| 吴说区块链 | `wublock123.com` | `curl` POST API | 深度市场分析、行情影响因素 |
| PANews | `panewslab.com` | `curl` RSS 订阅 | 政策监管、重大事件 |
| The Block | `theblock.co` | `curl` RSS 订阅 | 机构动向、市场趋势 |
| CoinDesk | `coindesk.com` | `curl` RSS 订阅 | 全球市场、主流币行情 |

**⚠️ 强制限制**：
- **只能**从以上 4 个数据源获取新闻
- **禁止**添加任何其他网站或数据源
- **禁止**使用 web_search 进行通用搜索
- **必须**通过 `bash_exec` 运行 `curl` 命令获取数据

---

## 工作流程

### Step 1: 并行获取四个数据源的新闻（全部用 `bash_exec` 运行 curl）

**重点关注**：
- ✅ 政策监管动态（SEC、各国政府政策）
- ✅ 机构/巨鲸动向（买入、卖出、持仓变化）
- ✅ 主流币种价格异动及技术面分析
- ✅ 重大市场事件（交易所、项目方、安全事件）
- ❌ 过滤：纯技术开发、小币种炒作、行业八卦

**时间范围计算**（用 `run_code` 执行 Python）：
```python
import os, time
hours = int(os.environ.get('CRYPTO_NEWS_HOURS', '24'))
cutoff = int(time.time()) - hours * 3600
print(cutoff)
```
将返回值保存为 `cutoffTimestamp`（Unix 整数秒）。

---

#### 1.1 吴说区块链 - `bash_exec` 运行 curl POST

```bash
curl -s 'https://api.wublock123.com/api/site/getLatestArticleList' \
  -X POST \
  -H 'Content-Type: application/x-www-form-urlencoded; charset=UTF-8' \
  -H 'Origin: https://www.wublock123.com' \
  -H 'Referer: https://www.wublock123.com/' \
  --data 'pageIndex=1&pageSize=10' \
  --max-time 15
```

返回 JSON 格式：
```json
{
  "code": 1,
  "success": true,
  "data": [{"title": "...", "description": "...", "url": "...", "inputtime": 1772623818}]
}
```

解析：过滤 `inputtime >= cutoffTimestamp` 的文章。

---

#### 1.2 PANews - `bash_exec` 运行 curl RSS

```bash
curl -s 'https://www.panewslab.com/rss.xml?lang=zh' \
  -H 'User-Agent: Mozilla/5.0' \
  --max-time 15
```

备选（RSS 失败时）：
```bash
curl -s 'https://www.panewslab.com/zh' \
  -H 'User-Agent: Mozilla/5.0' \
  --max-time 15
```

解析（用 `run_code` 运行 Python）：把 curl 输出的 XML/HTML 字符串传入 Python，用 `xml.etree.ElementTree` 解析 RSS 的 `<item>` 节点，提取 `<title>`、`<link>`、`<pubDate>`（转 Unix timestamp）、`<description>`，过滤 `pubDate >= cutoffTimestamp` 的条目。HTML 备选同理，用字符串匹配提取新闻列表。

---

#### 1.3 The Block - `bash_exec` 运行 curl RSS

```bash
curl -s 'https://www.theblock.co/rss.xml' \
  -H 'User-Agent: Mozilla/5.0' \
  --max-time 15
```

备选：
```bash
curl -s 'https://www.theblock.co' \
  -H 'User-Agent: Mozilla/5.0' \
  --max-time 15
```

解析（用 `run_code` 运行 Python）：同 1.2，`xml.etree.ElementTree` 解析 RSS `<item>`，提取 `title`、`link`、`pubDate`、`description`，过滤时间范围。

---

#### 1.4 CoinDesk - `bash_exec` 运行 curl RSS

```bash
curl -s 'https://www.coindesk.com/arc/outboundfeeds/rss' \
  -H 'User-Agent: Mozilla/5.0' \
  --max-time 15
```

备选：
```bash
curl -s 'https://www.coindesk.com' \
  -H 'User-Agent: Mozilla/5.0' \
  --max-time 15
```

解析（用 `run_code` 运行 Python）：同 1.2，`xml.etree.ElementTree` 解析 RSS `<item>`，提取 `title`、`link`、`pubDate`、`description`，过滤时间范围。

---

**容错处理**：
- 任一数据源 `curl` 失败（非零退出码、空返回、超时）不影响其他源
- 单个源无数据时返回空数组，继续处理
- 所有源都失败时返回错误提示

### Step 2: 合并、标准化和智能筛选

将四个数据源获取的数据合并为统一格式（在内存中处理），字段：
```
title / url / source / time(Unix timestamp) / summary
```

**智能筛选**，优先保留：
1. 影响市场行情的重大事件（政策、监管、机构动向）
2. 主流币种（BTC/ETH/SOL/BNB）的价格异动和趋势分析
3. 交易所、DeFi 协议等重大安全事件或系统升级
4. 宏观经济、美联储政策等对加密市场的影响

**过滤掉**：小市值币种炒作、纯技术更新（除非影响市值前 20 项目）、行业八卦、重复新闻（保留最详细的）

**容错**：
- 单个源无数据 → 记录提示，继续处理其他源
- 所有源都无数据 → 后续 Step 5 发送："📭 该时间段暂无新闻"

### Step 3: 深度分析与研判

对筛选后的新闻进行多维度智能分析（在 LLM 上下文内完成）：

**3.1 新闻重要性分级**
- `⚡ 重大影响` — 政策监管重大变化、机构大额买入/卖出、交易所重大事件
- `📊 市场影响` — 主流币价格异动、技术面突破/破位、宏观经济数据
- `📰 常规资讯` — 行业动态、项目更新、市场观点

**3.2 主流币种动态** — BTC、ETH、SOL、BNB（价格趋势、消息面、资金流向、市场情绪）

**3.3 行情影响因素** — 政策监管 / 机构动向 / 宏观经济 / 市场事件

**3.4 市场情绪研判** — bullish / bearish / neutral（统计数量比例及置信度）

**3.5 市场观点与风险提示** — 短期关注 / 风险警示 / 机会方向

### Step 4: 格式化输出

生成完整报告（Markdown 格式），结构：
- 标题、日期、数据源、新闻总数
- 市场情绪研判
- 主流币种动态
- 重大新闻（按重要性分级）
- 行情影响因素
- 市场观点与风险提示
- 免责声明

**语言规范（Step 4.1）** — 加密货币/机构首次出现用「中文全称（英文缩写）」，金额用「美元」不用「$」，日期用中文格式，避免中英文混排。

### Step 4.1: 语言和格式规范

**🔒 核心原则**：除新闻原文内容外，AI 生成的所有分析和描述必须避免中英文混排。

**加密货币名称**：首次出现用「中文全称（英文缩写）」，后续可直接用缩写。
- 比特币（BTC）、以太坊（ETH）、索拉纳（SOL）、币安币（BNB）

**机构和组织名称**：首次出现用「中文全称（英文缩写）」，后续可用缩写。交易所/品牌名保留英文原名（Binance、Coinbase 等）。

**技术术语**：首次出现用「中文翻译（英文原文）」后续可用缩写。
- 去中心化金融（DeFi）、总锁仓量（TVL）、不可替代代币（NFT）

**金额**：统一用「美元」，不用「$」。百分比保留 % 符号。
- ✅ 67,000 美元　❌ $67,000
- ✅ 1,000 亿美元　❌ $100B

**日期时间**：用中文格式（2026年3月30日、今日、昨日）。

**市场术语**：看涨/看跌/多头/空头/巨鲸，不用 Bullish/Bearish/Whale。

**不修改的内容**：新闻原文标题、摘要、链接 URL、来源标注保持原样。

### Step 5: 输出报告

不调用任何消息工具，直接将以下格式内容作为最终回复输出，由 cron deliver 机制负责投递到目标频道和 thread：

```
<「输出格式 — 主频道摘要」模板内容>

===THREAD===

<「输出格式 — Thread 详情」模板内容>
```

- `===THREAD===` 是固定分隔符，上方内容投递到主频道，下方内容投递到 thread
- 不得在此之外追加任何说明、确认或完成提示

---

## 输出格式

### 主频道摘要（主频道）

```
# 📈 加密货币市场摘要 [YYYY-MM-DD]

**数据源**: 吴说区块链 / PANews / The Block / CoinDesk
**新闻总数**: [N] 条 | **数据时效**: 过去 [24] 小时

---

## 📊 市场情绪研判

**整体情绪**: [🟢 看涨情绪占优 / 🔴 看跌情绪为主 / ⚪ 中性观望]
**置信度**: [高 / 中 / 低]

- 🟢 看涨: [N] 条 ([X]%)
- 🔴 看跌: [N] 条 ([X]%)
- ⚪ 中性: [N] 条 ([X]%)

**情绪解读**: [2-3 句话总结当前市场情绪特征和形成原因]

---

## 💎 主流币种动态

### 比特币（BTC）

**价格动向**: [涨/跌幅，关键价位]
**消息面**: [1-2 句总结 BTC 相关重要新闻]
**市场情绪**: [看涨/看跌/中性]

### 以太坊（ETH）

**价格动向**: [涨/跌幅，关键价位]
**消息面**: [1-2 句总结 ETH 相关重要新闻]
**市场情绪**: [看涨/看跌/中性]

### 索拉纳（SOL）

**价格动向**: [涨/跌幅，关键价位]
**消息面**: [1-2 句总结 SOL 相关重要新闻]
**市场情绪**: [看涨/看跌/中性]

> 📌 仅展示有重要新闻或显著价格波动的币种。

💬 _详细分析见 thread_
```

---

### Thread 详情（Thread）

```
## ⚡ 重大新闻（按重要性分级）

### 🔴 重大影响

- **⚡ [新闻标题]** - [来源] | [时间]
  > [新闻摘要及市场影响分析]
  🔗 [详情]([URL])

### 🟡 市场影响

- **📊 [新闻标题]** - [来源] | [时间]
  > [新闻摘要]
  🔗 [详情]([URL])

### 🟢 常规资讯

- **📰 [新闻标题]** - [来源] | [时间]
  > [新闻摘要]
  🔗 [详情]([URL])

---

## 🎯 行情影响因素

### 政策监管
[列举当日重要的政策监管动态]

### 机构动向
[列举机构/巨鲸的重要买卖动作]

### 宏观经济
[列举影响加密市场的宏观经济因素]

### 市场事件
[列举交易所、DeFi 等重要事件]

---

## 💡 市场观点与风险提示

### 短期关注（未来 1-3 天）
- [需要重点关注的事件/数据]

### 风险警示
- [当前市场面临的主要风险]

### 机会方向
- [基于新闻分析的潜在交易机会]

---

**⚠️ 免责声明**: 本报告内容仅供参考，不构成任何投资建议。加密货币投资存在极高风险，可能导致本金全部损失。请根据自身风险承受能力谨慎决策。

_📅 报告生成时间: [YYYY-MM-DD HH:MM:SS]_
```

## 异常处理

| 情况 | 处理方式 |
|------|----------|
| 尝试获取指定 4 个源以外的数据 | **严格禁止**，拒绝执行并返回错误 |
| wublock123 API curl 失败 | 跳过该源，继续处理其他源，报告中标注 "⚠️ 吴说区块链 API 暂时无法访问" |
| PANews RSS curl 失败 | 降级到 HTML 爬取首页，如仍失败则跳过，报告 "⚠️ PANews 数据获取异常" |
| The Block RSS curl 失败 | 降级到 HTML 爬取，如仍失败则跳过，报告 "⚠️ The Block 数据获取异常" |
| CoinDesk RSS curl 失败 | 降级到 HTML 爬取，如仍失败则跳过，报告 "⚠️ CoinDesk 数据获取异常" |
| 所有数据源都失败 | 在最终回复输出："📭 所有数据源暂时无法访问，建议稍后重试" |
| 时间范围内无新闻 | 在最终回复输出："📭 该时间段暂无符合条件的新闻" |

## 后续交互

| 用户说 | 动作 |
|--------|------|
| "展开第 X 条新闻" | 用 `bash_exec` 运行 curl 获取该新闻完整内容 |
| "只看市场动态" | 过滤输出，只展示市场动态类别 |
| "只看 BTC 相关" | 过滤输出，只展示提及 BTC 的新闻 |
| "更详细的分析" | 对重点新闻执行深度分析 |

## 输出语言

中文为主，保留英文专有名词（BTC、ETH、DeFi 等）和原始链接。

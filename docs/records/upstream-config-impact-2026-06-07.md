# 上游变更影响记录：2026-06-07

## 背景

当前主分支最近合并了 Telegram 按 Agent 化的改动（PR #175，提交 `6fc93a4`），将 Telegram 从平台级连接器改为 per-agent 连接器。

我们此前的配置/ENV 方案是：

- 平台侧：`.env` + `platform.yaml`
- Agent 侧：`agents/<id>/agent.yaml` + `agents/<id>/.env`

该改动与该方向是一致的（同样是 per-agent 化、与 Agent 生命周期绑定）。

## 影响评估

### 影响大小：中等偏低（可控）

- 改动未回退平台/Agent 配置文件与 env 分离的核心逻辑。
- 主要影响是：
  - Telegram 从平台配置入口迁移到 `agent.yaml`
  - Terraform/部署脚本若仍写平台级 Telegram 配置，会失效
- 其它已合入功能（如 IM 连接、会话/路由/模型）对本问题影响较小。

## 当前可选策略

### 方案 A：先不改（建议短期先推进）

可行条件：

- 当前未启用 Telegram，或暂不允许新建 Telegram 通道
- 团队愿意接受一段时间内“历史配置与新实现不完全兼容”

行动：

1. 在任务看板上新增“Telegram 上游兼容清单”
2. 禁止再新增平台级 Telegram 凭据
3. 新需求统一按 Agent 级配置推进

### 方案 B：立即改

- 影响开发节奏更大；需要同步修改所有部署/初始化与运维文档
- 可减少后续临近上线时的迁移突发

## 推荐

先按方案 A 推进其它事项：

- 不阻塞当前开发节奏
- 在部署脚本与环境注入阶段保留一个明确待办项
- 等你们集中处理 “配置重构收尾” 时，再一次性补齐 Telegram 的 Agent 化。

## 待办（建议 1 个 sprint 内）

1. 统一列出 `agent.yaml` 需要新增的字段（`connectors.telegram.bot_token_env`）
2. 在 `agents/<id>/.env` 与运行注入链路加上 Telegram 的 env 注入样例
3. 补一个最小回归用例：
   - 平台配置无 Telegram 凭据
   - Agent 有 Telegram connector env 引用
   - 运行时成功加载 Telegram
4. 更新 `docs/deployment/secrets.md` 与 `docs/capabilities/im-gateway.md`

## 结论

- 这是**可延后**的问题，不会破坏既定配置架构。
- 是否当前处理，取决于项目当前是否已在用 Telegram；若未用，可先并行推进其他事项。

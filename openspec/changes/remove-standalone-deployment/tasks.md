## 1. AGENTS.md 不可逾越规则改措辞（人工确认后提交,非 agent 直接提交）

- [ ] 1.1 [实现] 改 AGENTS.md「Agent / Platform 解耦」段:"agent 必须能在没有 platform 的环境下独立运行" → "部署上 platform 始终在场;`fleetent agent run` 是 node 拉起 agent 的原语 + dev/test,不是 standalone 部署模式"。**解耦契约段(单向依赖、护栏)原样保留**。
- [ ] 1.2 [验证] 人工 review 措辞:解耦契约未被弱化,只退役 standalone 部署

## 2. agent-runtime-cli reframe（命令不变）

- [ ] 2.1 [测试] `tests/unit/test_main_subcommands.py`(或等价):确认 `fleetent agent run`/`agent init` 仍存在、行为不变(reframe 不应改命令)→ 绿(回归保护)
- [ ] 2.2 [实现] agent-runtime-cli 相关代码注释/docstring 中"standalone 部署"叙述改为"node 原语 + dev/test"(不改命令逻辑)
- [ ] 2.3 [验证] `fleetent agent run`/`agent init` 行为零变化;node 经 subprocess 调它仍正常

## 3. install-agent.sh repurpose 为 agent-host installer

- [ ] 3.1 [测试] `tests/integration/test_install_agent_script.py`:改断言为"装 runtime+node、教程引导配 node/.env + `fleetent node start`、agent run/init 仅 dev 提及" → 红
- [ ] 3.2 [实现] 改 `scripts/install-agent.sh`:装 node、引导写 `$FLEETENT_HOME/node/.env` + `fleetent node start`;移除"standalone agent installer(no platform)"框架
- [ ] 3.3 [验证] `uv run pytest tests/integration/test_install_agent_script.py -x -q` → 绿

## 4. 单机 managed 拓扑成文 + 文档同步

- [ ] 4.1 [实现] `docs/` 部署相关(deployment / capabilities/agent-management / config-management / connectors / observability / glossary)中 standalone 描述改为"已退役部署模式;agent host 跑 node 接入 platform";单机 = platform+node+agent 同机成文
- [ ] 4.2 [实现] target-architecture §12 去掉"现状仍 standalone"过渡注记(改为已退役)
- [ ] 4.3 [验证] `git grep -n "standalone\|无 platform\|without.*platform 独立部署" -- docs/ ':!docs/archive'` 复查无遗留"standalone 作受支持部署"的表述

## 5. 收尾验证

- [ ] 5.1 [验证] `make test-pr` 全绿;《相关集成测试命令》(本 change 触碰的:test_install_agent_script + 改动文档测试)无新增失败
- [ ] 5.2 [验证] `make test-unit-ci` 覆盖率 ≥ 76%
- [ ] 5.3 [验证] `test_module_dependency_guardrails` 绿——**解耦契约未动**
- [ ] 5.4 [验证] 单机 managed 路径手验:platform + `fleetent node start` + node 拉起 agent 端到端跑通(确保"整套机制正常运转")
- [ ] 5.5 [验证] `openspec validate remove-standalone-deployment`;archive 后 `opsx:verify`

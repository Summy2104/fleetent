## 1. 移除隐式 YAML connector 发现

- [ ] 1.1 写 integration 测试:注入 store-sourced settings 时,connector 列举/查找只反映注入内容(见红)
- [ ] 1.2 写 integration 测试:未注入 settings 调用 connector operation 时不回落 YAML —— 行为为要求显式来源/明确错误,而非返回 YAML 定义(见红)
- [ ] 1.3 grep 全仓库 `list_configured_connectors` / `get_connector_config` / `check_connector` / `run_connector_sync` / `get_connector_status` 的无参或 `settings=None` 调用点,列清单
- [ ] 1.4 改 `operations` connector 入口:移除 `_kb_config(None)` 的 YAML 回落分支,要求显式注入 settings;跑 1.1–1.2 见绿
- [ ] 1.5 改 1.3 清单中的所有调用点为显式注入 store-sourced settings(platform 路径)或本地来源(CLI 路径)

## 2. 单机 / CLI 注入路径

- [ ] 2.1 写 integration 测试:无 platform 时 ingest CLI 从本地来源注入 settings,connector 列举/同步可用(见红)
- [ ] 2.2 实现/接线 CLI 显式注入路径;跑 2.1 见绿
- [ ] 2.3 确认 `knowledge_base` ✗→ `platform` 护栏与 module-boundaries 检查通过

## 3. 收尾验证

- [ ] 3.1 跑 `make test-pr` 与 `make test-integration-ci`,两者全绿(无新增失败)
- [ ] 3.2 ruff format/check 改动文件;`openspec validate kb-connector-config-single-source` 通过
- [ ] 3.3 更新 `docs/capabilities/knowledge-base.md`:connector 配置单一真相源为 `kb_connectors`,移除 YAML 双源描述(非代码产物,人工确认后再 commit)

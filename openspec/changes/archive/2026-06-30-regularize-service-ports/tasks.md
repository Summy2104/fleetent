## 1. node forwarder 8786 → 8767

- [x] 1.1 测试先行:断言 `DEFAULT_FORWARDER_PORT == 8767` + forwarder 寻址 URL(`node_addressing` http/ws)用 8767。`uv run pytest <file>::<test> -x -q` 见红
- [x] 1.2 改 `node/forwarder_contract.py` `DEFAULT_FORWARDER_PORT = 8767`(node bind/app、reconcile loopback、platform node_addressing 全走此常量,改一处生效)。见绿
- [x] 1.3 `docker-compose.yml` node 端口映射 `8786:8786 → 8767:8767`

## 2. kb-serve 8787 → 8768

- [x] 2.1 测试先行:断言 kb-serve 默认 port == 8768(`serve.py` 默认 + `KBServiceSection.port` 默认)。见红
- [x] 2.2 改 `knowledge_base/serve.py`(默认 + argparse default)+ `knowledge_base/service_config.py` `KBServiceSection.port = 8768`。见绿
- [x] 2.3 `kb-service.yaml.example` `service.port: 8787 → 8768`

## 3. agent 内部容器口 18765 → 8766

- [x] 3.1 测试先行:断言 `NodeConfig.agent_internal_port` 默认 == 8766 + `FLEETENT_NODE_AGENT_INTERNAL_PORT` 未设时取 8766。见红
- [x] 3.2 改 `node/config.py`(dataclass 默认 + env 默认 `"8766"`)。见绿(`node/backend.py` 经 `self._config.agent_internal_port` 自动跟随)

## 4. embedding 默认端点收口

- [x] 4.1 `kb-service.yaml.example` `embedding.endpoint: http://127.0.0.1:9000/v1/embeddings → http://127.0.0.1:11434/v1/embeddings`(对齐 `agent_config.py` 现有默认);若有断言 9000 的测试一并改

## 5. spec 同步 + 文档

- [x] 5.1 `container-deployment` spec delta(本 change specs/):node forwarder 8767、新增"规范服务端口约定"、顺带把残留的 `kb-service/kb-service.yaml`+`tenants/<tenant>/kb/` 同步为 `kb-service/<tenant>/{kb-service.yaml,.env,data/}`
- [x] 5.2 docs 端口同步:`docs/deployment/compose.md`(8786→8767、kb-serve 端口)、`AGENTS.md` gotcha(platform→node 转发寻址提到的 8786)、`docs/architecture*.md`(若列端口)
- [x] 5.3 Makefile 注释/默认若提及旧端口一并同步(`AGENT_PORT` 不变;无 node/kb 端口硬编码则免)

## 6. 收尾门禁

- [x] 6.1 `openspec validate regularize-service-ports --strict`
- [x] 6.2 `make test-pr` + `make test-integration-ci`(零新增失败;更新所有断言旧端口的测试)
- [x] 6.3 `PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py`
- [x] 6.4 grep 确认无残留旧端口:`grep -rnE "8786|8787|18765|:9000/v1/embeddings" src tests Makefile docker-compose.yml docs`(仅历史 archive 可留)
- [x] 6.5 所有 tasks.md checkbox 标 `[x]`
